#!/usr/bin/env python3
"""Research monitor for the Roko Journal. Free sources only, no API keys.

What it watches, and how:
  - Wedding, luxury, travel and hospitality publications, Bridebook, Hitched, The Knot, ONS: their RSS feeds
    (content/sources.json "feeds"), every run. Items are kept for 120 days.
  - What couples search for: Google's public search suggestions for each seed term (UK and US), weekly.
    Suggestions that are new compared with the previous snapshot are the "rising searches".
  - Google Trends: the public daily trending-searches feeds (UK and US), kept when they mention weddings or events.
  - Instagram, TikTok and Pinterest trends: there are no free APIs, so these come from news coverage (Google News RSS
    headlines for content/sources.json "news_queries") plus any links the Roko team adds in Admin > Journal > Research.
  - Market research pages (Bridebook, Hitched, The Knot, Savills, ONS, Pinterest Predicts): checked monthly; a change
    in the page text is recorded so the team can see when a new report lands.
  - Roko's own anonymised data (searches, enquiries, polls, vendor answers): monthly snapshot from the Roko API.

Writes research/digest.json (read by write.py and shown in Roko's admin) and the snapshots under research/.

  python3 scripts/research.py           normal run
  python3 scripts/research.py --diag    report which feeds answer
"""
import datetime, hashlib, html, json, re, sys, time, urllib.parse
from common import (RESEARCH, BROWSER, log, now, load_json, save_json, fetch, parse_feed, readable, roko, sources, text_of, ROKO_KEY)

WEDDING = re.compile(r"\b(wedding|weddings|bride|bridal|groom|engage(d|ment)|marri(age|ed|y)|elope|honeymoon|venue|reception|ceremony|"
                     r"bouquet|florist|caterer|celebration|party|parties|event planner|events industry)\b", re.I)


def feeds(diag=False):
    store = load_json(RESEARCH / "feed_items.json", [])
    known = {x["url"] for x in store}
    since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=120)
    added = 0
    for f in sources().get("feeds", []):
        try:
            _, raw = fetch(f["url"], timeout=20, headers=dict(BROWSER, Accept="application/rss+xml, application/xml, text/xml, */*"))
            items = parse_feed(raw)
        except Exception as e:
            log(f"::warning::feed FAIL {f['url']}: {str(e)[:90]}" if diag else f"feed failed {f['url']}: {str(e)[:90]}")
            continue
        must = re.compile(f["must"], re.I) if f.get("must") else WEDDING
        kept = 0
        for it in items:
            if not it["date"] or it["date"] < since:
                continue
            if not must.search(it["title"] + " " + it["summary"]):
                continue
            kept += 1
            if it["url"] in known:
                continue
            known.add(it["url"]); added += 1
            store.append({"url": it["url"], "title": it["title"], "summary": it["summary"][:400], "date": it["date"].isoformat(),
                          "publisher": f["publisher"], "kind": f.get("kind", "")})
        if diag:
            log(f"::notice::feed OK {len(items)} items, {kept} relevant: {f['url']}")
    for it in bing_news(diag):
        if it["url"] in known or it["date"] < since.isoformat():
            continue
        known.add(it["url"]); added += 1; store.append(it)
    store = [x for x in store if x["date"] >= since.isoformat()]
    store.sort(key=lambda x: x["date"], reverse=True)
    save_json(RESEARCH / "feed_items.json", store[:1500])
    log(f"feeds: {added} new items, {len(store)} kept")
    return store


def bing_news(diag=False):
    """Bing News RSS searches. Each result's link carries the publisher's real article URL (url=...), which is kept."""
    out = []
    for q in sources().get("bing_news", []):
        url = "https://www.bing.com/news/search?" + urllib.parse.urlencode({"q": q, "format": "rss", "setlang": "en-gb", "cc": "GB"})
        try:
            _, raw = fetch(url, timeout=20, headers=dict(BROWSER, Accept="application/rss+xml, application/xml, */*"))
            text = raw.decode("utf-8", "ignore")
        except Exception as e:
            log(f"::warning::bing news FAIL {q}: {str(e)[:80]}" if diag else f"bing news {q!r}: {str(e)[:80]}")
            continue
        n = 0
        for block in re.findall(r"<item>(.*?)</item>", text, re.S):
            g = lambda t: (re.search(rf"<{t}[^>]*>(.*?)</{t}>", block, re.S) or [None, ""])[1]
            link = html.unescape(text_of(g("link")))
            real = urllib.parse.parse_qs(urllib.parse.urlparse(link).query).get("url", [link])[0]
            from common import parse_date
            when = parse_date(text_of(g("pubDate")))
            title = text_of(html.unescape(g("title")))
            if not real.startswith("http") or not when or "bing.com" in urllib.parse.urlparse(real).netloc:
                continue
            n += 1
            out.append({"url": real, "title": title, "summary": text_of(html.unescape(g("description")))[:400], "date": when.isoformat(),
                        "publisher": text_of(g("News:Source")) or urllib.parse.urlparse(real).netloc.replace("www.", ""), "kind": "news", "query": q})
        if diag:
            log(f"::notice::bing news OK {n} items: {q}")
        time.sleep(0.4)
    return out


def suggestions(seed, gl):
    url = "https://suggestqueries.google.com/complete/search?" + urllib.parse.urlencode({"client": "firefox", "hl": "en-" + gl.upper() if gl == "gb" else "en", "gl": gl, "q": seed})
    _, raw = fetch(url, timeout=15)
    data = json.loads(raw.decode("utf-8", "ignore"))
    return [s for s in data[1] if isinstance(s, str)]


def searches():
    """Weekly snapshot of Google's search suggestions for each seed. New suggestions = rising searches."""
    snaps = sorted((RESEARCH / "searches").glob("*.json"))
    last = load_json(snaps[-1], {}) if snaps else {}
    if snaps and (now().date() - datetime.date.fromisoformat(snaps[-1].stem)).days < 7:
        return load_json(RESEARCH / "rising.json", {})
    snap = {}
    for gl in ("gb", "us"):
        for seed in sources().get("search_seeds", []):
            out = set()
            for q in (seed, seed + " ", seed + " for", seed + " ideas" if "ideas" not in seed else seed + " 2027"):
                try:
                    out.update(suggestions(q, gl))
                except Exception as e:
                    log(f"suggestions {gl} {q!r}: {str(e)[:80]}")
                time.sleep(0.4)
            snap[f"{gl}:{seed}"] = sorted(out)
    save_json(RESEARCH / "searches" / f"{now().date().isoformat()}.json", snap)
    rising = {"date": now().date().isoformat(), "compared_with": snaps[-1].stem if snaps else None, "gb": [], "us": []}
    for key, vals in snap.items():
        gl, seed = key.split(":", 1)
        before = set(last.get(key, []))
        if not before:
            continue
        for v in vals:
            if v not in before:
                rising[gl].append({"seed": seed, "search": v})
    save_json(RESEARCH / "rising.json", rising)
    log(f"searches: {sum(len(v) for v in snap.values())} suggestions, rising gb={len(rising['gb'])} us={len(rising['us'])}")
    return rising


def trends():
    out = []
    for geo in ("GB", "US"):
        try:
            _, raw = fetch(f"https://trends.google.com/trending/rss?geo={geo}", timeout=15)
            for it in parse_feed(raw):
                if WEDDING.search(it["title"] + " " + it["summary"]):
                    out.append({"geo": geo, "search": it["title"], "date": it["date"].isoformat() if it["date"] else "", "context": it["summary"][:200]})
        except Exception as e:
            log(f"trends {geo}: {str(e)[:80]}")
    store = load_json(RESEARCH / "trends.json", [])
    seen = {(x["geo"], x["search"]) for x in store}
    store = [x for x in out if (x["geo"], x["search"]) not in seen] + store
    save_json(RESEARCH / "trends.json", store[:300])
    return store


def news():
    out = []
    for q in sources().get("news_queries", []):
        url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": q + " when:30d", "hl": "en-GB", "gl": "GB", "ceid": "GB:en"})
        try:
            _, raw = fetch(url, timeout=15)
            for it in parse_feed(raw)[:12]:
                pub = it["title"].rsplit(" - ", 1)[-1] if " - " in it["title"] else ""
                out.append({"query": q, "headline": it["title"].rsplit(" - ", 1)[0], "publisher": pub,
                            "date": it["date"].isoformat() if it["date"] else ""})
        except Exception as e:
            log(f"news {q!r}: {str(e)[:80]}")
        time.sleep(0.3)
    save_json(RESEARCH / "headlines.json", out)
    return out


def pages():
    """Monthly check of market research pages; records when their text changes."""
    state = load_json(RESEARCH / "pages.json", {})
    changes = load_json(RESEARCH / "page_changes.json", [])
    for key, ref in sources().get("references", {}).items():
        st = state.get(key, {})
        if st.get("checked") and (now() - datetime.datetime.fromisoformat(st["checked"])).days < 28:
            continue
        try:
            final, title, text, _ = readable(ref["url"])
        except Exception as e:
            state[key] = dict(st, checked=now().isoformat(), error=str(e)[:120])
            continue
        h = hashlib.sha1(re.sub(r"\d{1,2}:\d{2}|\s+", " ", text).encode()).hexdigest()
        if st.get("hash") and st["hash"] != h:
            changes.insert(0, {"key": key, "title": ref["title"], "url": final, "date": now().date().isoformat(), "excerpt": text[:900]})
        state[key] = {"checked": now().isoformat(), "hash": h, "title": title, "chars": len(text), "error": ""}
        time.sleep(0.5)
    save_json(RESEARCH / "pages.json", state)
    save_json(RESEARCH / "page_changes.json", changes[:100])
    return state, changes


def roko_data():
    if not ROKO_KEY:
        return load_json(RESEARCH / "roko_latest.json", {})
    try:
        d = roko("/api/journal/data", private=True)
    except Exception as e:
        log(f"Roko data unavailable: {e}")
        return load_json(RESEARCH / "roko_latest.json", {})
    save_json(RESEARCH / "roko_latest.json", d)
    month = now().strftime("%Y-%m")
    save_json(RESEARCH / "roko" / f"{month}.json", d.get("stats", {}))
    return d


def main():
    if "--diag" in sys.argv:
        feeds(diag=True)
        return
    items = feeds()
    rising = searches()
    tr = trends()
    hl = news()
    state, changes = pages()
    rd = roko_data()
    digest = {
        "generated": now().isoformat(timespec="minutes"),
        "feed_items": items[:200],
        "rising_searches": rising,
        "trending": tr[:40],
        "headlines": hl[:120],
        "page_changes": changes[:20],
        "pages": state,
        "team_notes": rd.get("notes", []),
        "roko": {"stats": rd.get("stats", {}), "polls": rd.get("polls", [])},
    }
    save_json(RESEARCH / "digest.json", digest)
    log("digest written")


if __name__ == "__main__":
    main()
