#!/usr/bin/env python3
"""Decide what is due, research it and write it with Gemini (free tier). Uses no Claude credits.

Publishing rhythm (content/WRITING_GUIDE.md has the editorial rules): one new article a day, written at about 02:00
UK time. Each day's article is, in order of priority:
  - 1 vendor interview or business feature ("Meet the Makers") every fortnight, written only from a business's own
    answers sent through its Roko dashboard and approved in Roko's admin. No answers, no feature.
  - 1 original research feature a month (from the 8th), from Roko's anonymised data and cited industry research.
  - 1 flagship report a year (from 12 January): The State of Weddings <year>.
  - Time-sensitive guides are refreshed when they are 6 months old (at most one a week).
Features, research and reports are held for approval in Roko (Admin > Journal) before they appear.

At most one article is written per run. The article is saved without images; images.py adds them and only then
does build.py publish it.

  python3 scripts/write.py                 normal run (writes what is due, if anything)
  TASK=next python3 scripts/write.py       write the next roadmap article now
  TASK=26 python3 scripts/write.py         write roadmap article #26 now (or TASK=<slug>)
  TASK=feature|research|report python3 scripts/write.py
  TASK=refresh:<slug> python3 scripts/write.py
  python3 scripts/write.py --plan          only print what is due
"""
import datetime, json, os, re, sys
from pathlib import Path
from common import (blocked_url, scrub, ARTICLES, CONTENT, RESEARCH, clean, directory, gemini, gemini_json, load_json, log, now, readable, roadmap,
                    save_json, slugify, sources, articles, ROKO_KEY, roko)
from check import check_article, fix_links

GUIDE = (CONTENT / "WRITING_GUIDE.md").read_text(encoding="utf-8")
TASK = (os.environ.get("TASK") or "").strip()
PLAN_ONLY = "--plan" in sys.argv
EDITORIAL = ("guide", "cornerstone", "inspiration")
REVIEW_TYPES = ("feature", "research", "report")
SYSTEM = ("You are the editor of the Roko Journal and write every article for it. Follow this editorial guide exactly; "
          "it overrides your defaults.\n\n" + GUIDE)


# ------------------------------------------------------------------ what is due

def week_start(d):
    return (d - datetime.timedelta(days=d.weekday())).date()


def pub_date(a):
    return datetime.datetime.fromisoformat(a["date"]).replace(tzinfo=now().tzinfo)


def plan():
    t = now()
    arts = articles()
    rm = roadmap()
    done = {a.get("roadmap") for a in arts if a.get("roadmap")} | {a["slug"] for a in arts}
    failed = load_json(CONTENT / "attempts.json", {})
    queue = [i for i in sorted(rm["items"], key=lambda i: (i["priority"] or 999, i["n"]))
             if i["type"] in EDITORIAL and i["n"] not in done and i["slug"] not in done
             and failed.get(i["slug"], {}).get("count", 0) < 3]           # three failed attempts: skipped until the team looks at it
    if TASK:
        if TASK in ("next",):
            return ("roadmap", queue[0]) if queue else (None, "roadmap finished")
        if TASK in ("feature", "research", "report"):
            return (TASK, None)
        if TASK.startswith("refresh:"):
            a = next((x for x in arts if x["slug"] == TASK.split(":", 1)[1]), None)
            return ("refresh", a) if a else (None, "no such article")
        it = next((i for i in rm["items"] if str(i["n"]) == TASK or i["slug"] == TASK), None)
        if it:
            return ("roadmap", it)
        return (None, f"unknown TASK {TASK!r}")

    ws = week_start(t)
    today = [a for a in arts if pub_date(a).date() == t.date()]
    # One new article a day, written in the early hours (the 02:07 run; the 05:07 run is a backup if that one failed).
    if not today:
        year = t.year
        if t.month == 1 and t.day >= 12 and not any(a["type"] == "report" and str(year) in a["title"] for a in arts):
            return ("report", None)                                        # yearly flagship report (January)
        if t.day >= 8 and not any(a["type"] == "research" and pub_date(a).strftime("%Y-%m") == t.strftime("%Y-%m") for a in arts) and research_has_material():
            return ("research", None)                                      # monthly research
        last_feature = max([pub_date(a) for a in arts if a["type"] == "feature"], default=None)
        if (not last_feature or (t - last_feature).days >= 13) and unused_interviews():
            return ("feature", None)                                       # fortnightly business feature
        if queue:
            return ("roadmap", queue[0])                                   # otherwise the next article from the roadmap
    # Saturdays, once the day's article exists: refresh one time-sensitive guide that is six months old.
    stale = [a for a in arts if a.get("time_sensitive") and a["type"] in EDITORIAL
             and (t - datetime.datetime.fromisoformat(a.get("updated") or a["date"]).replace(tzinfo=t.tzinfo)).days >= 180]
    if today and stale and t.weekday() == 5 and not any(a.get("updated", "")[:10] >= ws.isoformat() and a.get("updated") != a["date"] for a in arts):
        return ("refresh", sorted(stale, key=lambda a: a.get("updated") or a["date"])[0])
    return (None, "nothing due")


_DATA = None


def roko_data():
    global _DATA
    if _DATA is None:
        _DATA = load_json(RESEARCH / "roko_latest.json", {}) or {}
        if ROKO_KEY and not _DATA:
            try:
                _DATA = roko("/api/journal/data", private=True)
            except Exception as e:
                log(f"Roko data unavailable: {e}")
                _DATA = {}
    return _DATA


def used_contributions():
    return {a.get("contribution_id") for a in articles() if a.get("contribution_id")}


def unused_interviews():
    used = used_contributions()
    return [c for c in roko_data().get("contributions", []) if c.get("kind") == "interview" and c.get("id") not in used]


def research_has_material():
    d = load_json(RESEARCH / "digest.json", {})
    return bool(d.get("feed_items") or d.get("roko", {}).get("stats"))


# ------------------------------------------------------------------ material

def ref_material(keys):
    out = []
    refs = sources().get("references", {})
    for k in keys:
        r = refs.get(k)
        if not r:
            continue
        try:
            final, title, text, _ = readable(r["url"])
        except Exception as e:
            log(f"reference {k} unavailable: {str(e)[:80]}")
            continue
        text = scrub(text)
        if len(text) < 300 or blocked_url(final):
            continue
        out.append({"kind": "reference", "title": r["title"], "url": final, "publisher": r["publisher"], "text": text})
    return out


def words_of(s):
    return set(w for w in re.findall(r"[a-z]{4,}", s.lower()) if w not in {"wedding", "weddings", "with", "your", "from", "that", "this", "guide", "ideas", "what", "when", "complete"})


def feed_material(topic, n=4):
    d = load_json(RESEARCH / "digest.json", {})
    kw = words_of(topic)
    scored = []
    for it in d.get("feed_items", []):
        if blocked_url(it["url"]):
            continue
        s = len(kw & words_of(it["title"] + " " + it["summary"]))
        if s:
            scored.append((s, it["date"], it))
    out = []
    for _, _, it in sorted(scored, key=lambda x: (-x[0], x[1]), reverse=False)[: n * 2]:
        if len(out) >= n:
            break
        try:
            final, title, text, _ = readable(it["url"], limit=6000)
        except Exception:
            continue
        text = scrub(text)
        if len(text) > 400 and not blocked_url(final):
            out.append({"kind": "publication", "title": it["title"], "url": final, "publisher": it["publisher"], "text": text})
    return out


def expert_material(cluster):
    out = []
    for c in roko_data().get("contributions", []):
        if c.get("kind") != "expert" or (c.get("cluster") and c["cluster"] != cluster):
            continue
        qa = "\n".join(f"Q: {x.get('q', '')}\nA: {x.get('a', '')}" for x in c.get("answers", []))
        out.append({"kind": "expert", "title": f"{c.get('name', '')}, {c.get('business', '')} (answers given to Roko, may be quoted)",
                    "url": "", "vendor_url": c.get("vendor_url", ""), "publisher": c.get("business", ""), "text": qa})
    return out[:4]


def directory_material(cats):
    """What the Roko Directory actually holds for these categories (only the listings' own words)."""
    d = directory()
    vend = [v for v in d.get("vendors", []) if set(v.get("categories", [])) & set(cats)][:8]
    if not vend:
        return [], []
    lines = [f"- {v['name']} ({v.get('category_name', '')}, {v.get('city', '')}, {v.get('country', '')}): {v.get('summary', '')[:300]} [profile: {v['url']}]" for v in vend]
    return [{"kind": "directory", "title": "Businesses listed on the Roko Directory in these categories (their own listing text)",
             "url": "", "publisher": "Roko Directory", "text": "\n".join(lines)}], vend


def links_for(item_cluster, cats, self_slug, vendors):
    rm = roadmap()
    arts = [a for a in articles() if a["slug"] != self_slug and a.get("images")]
    corner_n = rm["clusters"].get(item_cluster, {}).get("cornerstone")
    corner = next((a for a in arts if a.get("roadmap") == corner_n), None)
    same = [a for a in arts if a["cluster"] == item_cluster]
    other = [a for a in arts if a["cluster"] != item_cluster]
    jl = (([corner] if corner else []) + [a for a in same if a is not corner] + other)[:14]
    d = directory()
    pages = d.get("pages", {})
    catlinks = [(p, pages[p]) for p in ["/" + c for c in cats] if p in pages]
    for p, label in pages.items():
        if len(catlinks) >= 8:
            break
        if p.count("/") == 1 and any(c in p for c in cats) and (p, label) not in catlinks:
            catlinks.append((p, label))
    lines = ["Journal articles (use 2 to 4 that genuinely help):"]
    lines += [f"- /journal/{a['slug']} : {a['title']}" + (" (CORNERSTONE for this topic: link to it)" if a is corner else "") for a in jl] or ["- (none published yet)"]
    lines += ["Roko Directory pages (businesses are listed on these):"] + ([f"- {p} : {l}" for p, l in catlinks] or ["- /wedding-vendors : All event and wedding businesses"])
    if vendors:
        lines += ["Business profiles (link only where relevant):"] + [f"- {v['url']} : {v['name']}" for v in vendors]
    internal_ok = {"/journal/" + a["slug"] for a in jl} | {p for p, _ in catlinks} | {v["url"] for v in vendors} | {"/wedding-vendors", "/list-your-business", "/journal", "/reports"}
    return "\n".join(lines), internal_ok, len(jl), corner


def material_block(mat):
    return "\n\n".join(f"[{i}] {m['title']} | {m.get('publisher', '')} | {m.get('url') or 'no link'}\n{scrub(m['text'])}" for i, m in enumerate(mat))


# ------------------------------------------------------------------ writing

TARGET_WORDS = {"cornerstone": 3000, "guide": 1700, "inspiration": 1400, "feature": 1200, "research": 1400, "report": 3600}
SECTIONS = {"cornerstone": (7, 10), "guide": (5, 7), "inspiration": (5, 8), "feature": (4, 6), "research": (4, 6), "report": (7, 10)}


def write(kind, brief, mat, links, internal_ok, n_links, typ, extra_rules=""):
    """Plan, then write section by section (long articles come out complete and on length), then check everything."""
    from check import check_prose
    mat_text = "\n".join(m["text"] for m in mat)
    external_ok = {m["url"] for m in mat if m.get("url")}
    target = TARGET_WORDS[typ]
    lo, hi = SECTIONS[typ]
    context = (f"BRIEF\n{brief}\n\nLINKS (the only internal paths you may link to)\n{links}\n\n"
               f"MATERIAL (the only source of facts, figures, quotes and business details)\n{material_block(mat)}\n\n{extra_rules}")
    # 1. the plan
    plan = None
    for attempt in range(3):
        try:
            plan = gemini_json(context + f"\nPLAN the article first. It will be about {target} words in total, in {lo} to {hi} sections. Reply with ONE JSON object only:\n"
                               '{"title": "...", "seo_title": "...", "dek": "...", "intro": "the opening paragraph(s), 2 to 4 sentences, no heading", '
                               '"sections": [{"heading": "sentence-case heading", "covers": "what this section answers and which material numbers it draws on", "words": 300}], '
                               '"faq": [{"q": "...", "a": "..."}], "keywords": ["..."], "tags": ["4 to 8 short topic tags readers would browse by, e.g. Venues, Budget, Destination weddings"], "image_subjects": ["3 to 6 concrete photo subjects"], '
                               '"time_sensitive": true, "used_material": [0, 1]}\n'
                               'If the material is not enough for an accurate, genuinely useful article, reply {"skip": "reason"}.', SYSTEM, temperature=0.6, tokens=8192)
            break
        except Exception as e:
            log(f"plan attempt {attempt + 1}: {str(e)[:120]}")
    if not plan:
        return None, ["the writer did not return a plan"]
    if plan.get("skip"):
        return None, ["writer skipped: " + str(plan["skip"])]
    secs = [x for x in plan.get("sections") or [] if isinstance(x, dict) and x.get("heading")][:hi]
    if len(secs) < lo - 1:
        return None, [f"plan had only {len(secs)} sections"]
    # 2. each section
    out_secs = []
    for i, sec in enumerate(secs):
        words = max(150, int(sec.get("words") or target / len(secs)))
        done = [x["heading"] for x in secs[:i]]
        later = [x["heading"] for x in secs[i + 1:]]
        text, errs = "", []
        for attempt in range(3):
            fix = "" if not errs else ("\n\nYOUR LAST VERSION OF THIS SECTION FAILED THESE CHECKS, fix every one:\n- " + "\n- ".join(errs) + "\n\nLAST VERSION:\n" + text)
            try:
                d = gemini(context + f"\nARTICLE: {plan['title']}\nINTRO ALREADY WRITTEN: {plan.get('intro', '')}\nSECTIONS BEFORE THIS ONE: {'; '.join(done) or 'none'}\n"
                                f"SECTIONS AFTER THIS ONE: {'; '.join(later) or 'none'}\n\nWrite ONLY the section '## {sec['heading']}' ({sec.get('covers', '')}), about {words} words, "
                                "in Markdown, starting with that '## ' heading line. ### sub-headings, lists and tables are fine where they help. Don't repeat what other "
                                "sections cover, don't summarise the article, and don't write a conclusion. Never write I, me, my, we, us or our: write as Roko or to 'you'. "
                                "Any number, price or quote must be in the MATERIAL. Link to internal paths from LINKS only where it genuinely helps. "
                                "Reply with the section's Markdown only: no JSON, no code fences, no notes." + fix, SYSTEM, temperature=0.65 if attempt == 0 else 0.4, tokens=8192, json_mode=False)
                text = clean(re.sub(r"^```(?:markdown|md)?\s*|\s*```$", "", d.strip()))
            except Exception as e:
                errs = [f"no usable reply ({str(e)[:60]})"]
                continue
            if not text.lstrip().startswith("## "):
                text = f"## {sec['heading']}\n\n" + text
            text = fix_links(text, internal_ok, external_ok)
            errs = check_prose(text, mat_text)
            if len(re.findall(r"[A-Za-z0-9'%£$€]+", text)) < words * 0.6:
                errs.append(f"too short: write about {words} words")
            if not errs:
                break
            log(f"section {i + 1} attempt {attempt + 1}: {errs}")
        if errs:
            log(f"section '{sec['heading']}' dropped: {errs}")
            continue
        out_secs.append(text.strip())
    intro = clean(str(plan.get("intro", "")))
    intro_errs = check_prose(intro, mat_text)
    if intro_errs:
        return None, ["intro: " + e for e in intro_errs]
    d = {k: plan.get(k) for k in ("title", "seo_title", "dek", "keywords", "tags", "image_subjects", "time_sensitive", "used_material")}
    for k in ("title", "seo_title", "dek"):
        d[k] = clean(str(d.get(k) or ""))
    d["body"] = fix_links(intro + "\n\n" + "\n\n".join(out_secs), internal_ok, external_ok)
    d["faq"] = []
    for x in plan.get("faq") or []:
        if isinstance(x, dict):
            q, a = clean(str(x.get("q", ""))), clean(str(x.get("a", "")))
            if q and a and not check_prose(q + "\n" + a, mat_text):
                d["faq"].append({"q": q, "a": a})
    test = dict(d, slug="x", type=typ, cluster="x", date="2000-01-01T00:00", sources=[1])
    errs = check_article(test, material_text=mat_text, journal_links_available=n_links if typ != "feature" else 0)
    if errs and all(e.startswith("link to at least") for e in errs):
        # Too few links to other Journal articles: add a short related-reading line from the LINKS list.
        have = set(re.findall(r"\]\((/journal/[a-z0-9-]+)\)", d["body"]))
        extra = [(m.group(2), m.group(1)) for m in re.finditer(r"^- (/journal/[a-z0-9-]+) : (.+?)(?: \(CORNERSTONE.*\))?$", links, re.M) if m.group(1) not in have][:max(0, 2 - len(have))]
        if extra:
            d["body"] += "\n\nMore from the Roko Journal: " + " and ".join(f"[{t}]({u})" for t, u in extra) + "."
            test["body"] = d["body"]
            errs = check_article(test, material_text=mat_text, journal_links_available=n_links)
    if errs:
        log(f"article checks failed: {errs}")
        return None, errs
    return d, []


def sources_from(d, mat):
    used = [i for i in (d.get("used_material") or []) if isinstance(i, int) and 0 <= i < len(mat)]
    if not used:
        used = list(range(len(mat)))
    out, seen = [], set()
    for i in used:
        m = mat[i]
        if m.get("url") and m["url"] not in seen:
            seen.add(m["url"])
            out.append({"title": m["title"], "url": m["url"], "publisher": m.get("publisher", "")})
    return out


def save_article(d, *, slug, typ, cluster, mat, roadmap_n=None, goal=None, extra=None, existing=None):
    t = now().strftime("%Y-%m-%dT%H:%M")
    a = dict(existing or {})
    a.update({
        "slug": slug, "roadmap": roadmap_n, "title": d["title"], "seo_title": d.get("seo_title") or d["title"][:60],
        "dek": d["dek"], "type": typ, "cluster": cluster, "body": d["body"], "faq": d.get("faq", []),
        "keywords": d.get("keywords", [])[:8], "tags": [clean(str(t))[:40] for t in (d.get("tags") or d.get("keywords") or [])][:8], "image_subjects": d.get("image_subjects", [])[:6],
        "time_sensitive": bool(d.get("time_sensitive")), "sources": sources_from(d, mat),
        "goal": goal or a.get("goal") or {"type": "category", "url": "/wedding-vendors", "label": "Discover businesses on Roko"},
        "review": typ in REVIEW_TYPES, "series": "Reports" if typ in ("research", "report") else "Journal",
    })
    a["date"] = a.get("date") or t
    a["updated"] = t
    a.setdefault("images", [])
    if extra:
        a.update(extra)
    a.pop("_file", None)
    save_json(ARTICLES / f"{slug}.json", a)
    log(f"saved {slug} ({typ}), waiting for images")
    return a


def goal_for(item, internal_ok):
    g = dict(item["goal"])
    if g["type"] == "register":
        return g
    pages = directory().get("pages", {})
    if g["url"] in pages:
        return g
    for c in item["categories"]:
        if "/" + c in pages:
            return {"type": "category", "url": "/" + c, "label": g["label"]}
    return {"type": "category", "url": "/wedding-vendors", "label": "Discover event and wedding businesses on Roko"}


def do_roadmap(item):
    log(f"writing roadmap #{item['n']}: {item['title']}")
    mat = ref_material(item["refs"]) + feed_material(item["title"] + " " + item["keyword"]) + expert_material(item["cluster"])
    dmat, vendors = directory_material(item["categories"])
    mat += dmat
    links, internal_ok, n_links, corner = links_for(item["cluster"], item["categories"], item["slug"], vendors)
    rising = load_json(RESEARCH / "rising.json", {})
    signals = [r["search"] + f" ({gl.upper()})" for gl in sources().get("markets", {"gb": "", "us": ""}) for r in rising.get(gl, []) if words_of(r["search"]) & words_of(item["keyword"])][:20]
    brief = (f"Title to use (you may refine the wording, keep the meaning): {item['title']}\n"
             f"Article type: {item['type']}{' (the CORNERSTONE guide of its cluster: broad, definitive, links out to supporting articles)' if item['cornerstone'] else ''}\n"
             f"Topic cluster: {roadmap()['clusters'][item['cluster']]['name']}\n"
             f"Main keyword (use naturally in the title, dek, first paragraph and one heading): {item['keyword']}\n"
             f"Searches people are making around this topic right now (context only, not facts): {'; '.join(signals) or 'none recorded'}\n"
             f"Conversion goal: the article's natural next step for the reader is '{item['goal']['label']}' ({item['goal']['url']}). "
             "Work one contextual invitation to discover suppliers on Roko into the text, without a sales pitch.\n"
             "Write for readers on any budget; luxury is a standard of quality, not a price tag. Write for a worldwide audience: never assume the UK, "
             "say which country a fact or rule applies to, and use examples from more than one market where the material allows.")
    typ = "cornerstone" if item["cornerstone"] else item["type"]
    d, errs = write("roadmap", brief, mat, links, internal_ok, n_links, typ)
    if not d:
        log_failure(item["slug"], errs)
        return None
    return save_article(d, slug=item["slug"], typ=typ, cluster=item["cluster"], mat=mat, roadmap_n=item["n"], goal=goal_for(item, internal_ok),
                        extra={"categories": item["categories"]})


def do_feature():
    c = (unused_interviews() or [None])[0]
    if not c:
        log("no approved interview answers waiting")
        return None
    qa = "\n\n".join(f"Q: {x.get('q', '')}\nA: {x.get('a', '')}" for x in c.get("answers", []))
    listing = c.get("listing_text", "")
    mat = [{"kind": "interview", "title": f"Interview answers from {c.get('name', '')} of {c.get('business', '')}, given to Roko for publication",
            "url": "", "publisher": c.get("business", ""), "text": qa},
           {"kind": "directory", "title": f"{c.get('business', '')} on the Roko Directory (their own listing)", "url": "", "publisher": "Roko Directory", "text": listing}]
    vendors = [{"url": c["vendor_url"], "name": c.get("business", "")}] if c.get("vendor_url") else []
    cats = c.get("categories", [])
    links, internal_ok, n_links, _ = links_for("suppliers", cats, "", vendors)
    brief = (f"A 'Meet the Makers' feature about {c.get('business', '')} ({c.get('category', '')}, {c.get('city', '')}, {c.get('country', '')}), "
             f"built only from {c.get('name', '')}'s own interview answers and their Roko listing.\n"
             "Tell the business's story and what readers can learn from it. Use several of their answers as direct quotations "
             "(blockquotes or inline quotes) copied word for word; never change or add words inside a quotation. "
             f"Link to their Roko profile ({c.get('vendor_url', '')}) and close with a natural invitation for other businesses to join Roko.\n"
             "Title it 'Meet the Makers: ' followed by a specific line about the business.")
    d, errs = write("feature", brief, mat, links, internal_ok, 0, "feature")
    if not d:
        log_failure("feature-" + str(c.get("id")), errs)
        return None
    slug = slugify("meet-the-makers-" + c.get("business", "business"))
    return save_article(d, slug=slug, typ="feature", cluster="suppliers", mat=mat,
                        goal={"type": "vendor", "url": c.get("vendor_url") or "/list-your-business", "label": f"See {c.get('business', '')} on Roko"},
                        extra={"contribution_id": c.get("id"), "people": [{"name": c.get("name", ""), "business": c.get("business", ""), "vendor_url": c.get("vendor_url", "")}],
                               "vendor_id": c.get("link_id"), "vendor_photos": c.get("photos", [])})


def stats_material(months=1):
    d = roko_data()
    st = d.get("stats", {})
    polls = d.get("polls", [])
    lines = []
    if st:
        lines.append(f"Roko platform data for {st.get('period', 'the period')} (anonymised and aggregated by Roko; sample sizes as stated):")
        for k, v in st.items():
            if k == "period":
                continue
            lines.append(f"- {k.replace('_', ' ')}: {json.dumps(v, ensure_ascii=False)}")
    for p in polls:
        if p.get("responses", 0) >= 30:
            opts = "; ".join(f"{o['label']}: {o['votes']} votes ({o['share']}%)" for o in p.get("options", []))
            lines.append(f"- Roko reader poll '{p['question']}' ({p['responses']} responses, {p.get('from', '')} to {p.get('to', '')}): {opts}")
    if not lines:
        return []
    return [{"kind": "roko", "title": "Roko's own data (searches, enquiries, listings and reader polls on withroko.com)", "url": "", "publisher": "Roko", "text": "\n".join(lines)}]


def digest_material():
    d = load_json(RESEARCH / "digest.json", {})
    lines = []
    rs = d.get("rising_searches", {})
    for gl, name in (rs.get("markets") or {"gb": "the UK", "us": "the US"}).items():
        for r in rs.get(gl, [])[:12]:
            lines.append(f"- New Google search suggestion in {name} (since {rs.get('compared_with')}): {r['search']}")
    for h in d.get("headlines", [])[:40]:
        lines.append(f"- Headline ({h.get('publisher', '')}, {h.get('date', '')[:10]}): {h['headline']}")
    if not lines:
        return []
    return [{"kind": "signals", "title": "Search and news signals gathered by Roko's research monitor (Google search suggestions and Google News headlines)",
             "url": "", "publisher": "Roko research monitor", "text": "\n".join(lines)}]


def do_research():
    t = now()
    month = t.strftime("%B %Y")
    mat = stats_material() + digest_material() + feed_material("wedding trends industry couples venues", n=5) + ref_material(["maps_guests_2026", "ons_marriages_2024_2025", "savills_weddings", "which_wedding_tips"])
    if len(mat) < 3:
        log("not enough research material this month")
        return None
    links, internal_ok, n_links, _ = links_for("suppliers", ["wedding-vendors"], "", [])
    brief = (f"Roko's monthly research feature for {month}. Report what Roko's own data shows (with sample sizes) and what the "
             "industry research and signals in the material say about how couples are planning right now. If Roko's own samples "
             "are small, say so plainly and lean on the cited research. Lead with the single most useful finding. Include at least "
             "one Markdown table of figures from the material. Explain what each finding means for couples and for wedding businesses. "
             "Add a short 'How this research was done' section naming each data source.")
    d, errs = write("research", brief, mat, links, internal_ok, n_links, "research")
    if not d:
        log_failure("research-" + t.strftime("%Y-%m"), errs)
        return None
    slug = slugify(d["title"])[:60] + "-" + t.strftime("%Y-%m")
    return save_article(d, slug=slug, typ="research", cluster="suppliers", mat=mat,
                        goal={"type": "register", "url": "/list-your-business", "label": "List your business on Roko"}, extra={"period": t.strftime("%Y-%m")})


def do_report():
    t = now()
    year = t.year
    snaps = sorted((RESEARCH / "roko").glob(f"{year - 1}-*.json"))
    yearly = [{"kind": "roko", "title": f"Roko platform data, {s.stem}", "url": "", "publisher": "Roko", "text": s.read_text()[:6000]} for s in snaps]
    mat = yearly + stats_material() + digest_material() + ref_material(["maps_guests_2026", "maps_guests_2025", "ons_marriages_2024_2025", "savills_weddings", "which_wedding_tips", "pinterest_wedding_2026"])
    item = next((i for i in roadmap()["items"] if i["type"] == "report"), None)
    links, internal_ok, n_links, _ = links_for("luxury", ["wedding-vendors"], "", [])
    brief = (f"The State of Weddings {year}: Roko's flagship annual report. A reference document that journalists, planners and "
             f"wedding businesses can cite. Cover costs, guest numbers, venues, suppliers, styles and planning behaviour in {year - 1} "
             f"and what to expect in {year}, using only the material. Open with an executive summary of the most important findings as a "
             "short list. Use Markdown tables for figures. Name the source of every figure in the sentence. End with a 'Methodology and "
             "sources' section. Write it so each finding can be quoted on its own.")
    d, errs = write("report", brief, mat, links, internal_ok, n_links, "report")
    if not d:
        log_failure(f"report-{year}", errs)
        return None
    slug = f"state-of-weddings-{year}"
    return save_article(d, slug=slug, typ="report", cluster="luxury", mat=mat, roadmap_n=item["n"] if item and str(year) in item["title"] else None,
                        goal={"type": "register", "url": "/list-your-business", "label": "List your business on Roko"}, extra={"period": str(year)})


def do_refresh(a):
    item = next((i for i in roadmap()["items"] if i["n"] == a.get("roadmap")), None)
    refs = item["refs"] if item else []
    mat = ref_material(refs) + feed_material(a["title"]) + expert_material(a["cluster"])
    dmat, vendors = directory_material(item["categories"] if item else [])
    mat += dmat
    links, internal_ok, n_links, _ = links_for(a["cluster"], item["categories"] if item else [], a["slug"], vendors)
    brief = (f"UPDATE an existing article so every time-sensitive fact is current. Keep its title, structure and voice unless the "
             f"material shows something has changed. Article type: {a['type']}.\n\nEXISTING ARTICLE:\n{a['title']}\n{a['dek']}\n\n{a['body']}")
    d, errs = write("refresh", brief, mat, links, internal_ok, n_links, a["type"])
    if not d:
        log_failure("refresh-" + a["slug"], errs)
        return None
    a = dict(a)
    out = save_article(d, slug=a["slug"], typ=a["type"], cluster=a["cluster"], mat=mat, roadmap_n=a.get("roadmap"), existing=a)
    return out


def log_failure(key, errs):
    f = CONTENT / "attempts.json"
    data = load_json(f, {})
    if any(re.search(r"Gemini unavailable|quota|did not return a plan|no usable reply", str(e), re.I) for e in errs):
        log(f"{key}: Gemini was unavailable; not counted as a failed attempt (it is tried again on the next run)")
        return
    data[key] = {"date": now().isoformat(timespec="minutes"), "errors": errs[:10], "count": data.get(key, {}).get("count", 0) + 1}
    save_json(f, data)
    log(f"could not write {key}: {errs[:5]}")


def main():
    kind, what = plan()
    if PLAN_ONLY or kind is None:
        log(json.dumps({"due": kind, "what": what if isinstance(what, str) else (what or {}).get("title") if what else None}))
        return
    if kind == "roadmap":
        do_roadmap(what)
    elif kind == "feature":
        do_feature()
    elif kind == "research":
        do_research()
    elif kind == "report":
        do_report()
    elif kind == "refresh":
        do_refresh(what)


if __name__ == "__main__":
    main()
