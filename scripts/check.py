#!/usr/bin/env python3
"""Editorial checks for Roko Journal articles. Every article must pass before it is published.

  python3 scripts/check.py content/articles/<slug>.json     check one article (prints PASS or the problems)

check_article() is also used by write.py with the article's MATERIAL, so that every number and every quote
can be matched against what was actually read.
"""
import json, re, sys
from pathlib import Path

BANNED_CHARS = {"—": "em dash", "–": "en dash", "…": "ellipsis character", "→": "arrow", "✦": "star symbol",
                "•": "bullet symbol", "★": "star", "“": "curly quote", "”": "curly quote", "‘": "curly quote", "’": "curly apostrophe"}
EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
BANNED = [
    r"\bdelv(e|es|ed|ing)\b", r"\btapestry\b", r"\brealm\b", r"\btestament\b", r"\blandscape of\b", r"\bwedding landscape\b",
    r"\bnavigat(e|es|ed|ing) (the|your|this|these|through)\b", r"\b(planning|wedding) journey\b", r"\bembark", r"\belevat(e|es|ed|ing)\b",
    r"\bseamless(ly)?\b", r"\bunforgettable\b", r"\bmagical\b", r"\bbreathtaking\b", r"\bnestled\b", r"\bboasts?\b", r"\bdream wedding\b",
    r"\bspecial day\b", r"\bgame[- ]chang", r"\bunlock(s|ed|ing)?\b", r"\bunleash", r"\bharness(es|ed|ing)?\b", r"\bleverag(e|es|ed|ing)\b",
    r"\brobust\b", r"\bvibrant\b", r"\bbustling\b", r"\bpivotal\b", r"\bmeticulous(ly)?\b", r"\bwhimsical\b", r"look no further",
    r"in today's world", r"ever-evolving", r"it's worth noting", r"it is worth noting", r"it is important to note", r"in conclusion",
    r"to sum up", r"let's dive in", r"at the end of the day", r"whether you're [^.]{1,60} or ", r"isn't just [^.]{1,60}, it's",
    r"is not just [^.]{1,60}, it is", r"\bnot just [^.]{1,40} but\b", r"\bsay yes to\b", r"key takeaways", r"final thoughts",
]
LIMITED = {r"\bstunning\b": 1, r"\bcurated\b": 1, r"\btimeless\b": 1, r"\bbig day\b": 1, r"\bcrucial\b": 1, r"\btie the knot\b": 1}
OPENERS = re.compile(r"^(planning a wedding|your wedding day|when it comes to|imagine|are you|have you ever|in the world of|"
                     r"weddings are|every couple|there's nothing|there is nothing|whether you)", re.I)
BAD_HEADINGS = re.compile(r"^#{2,3}\s*(conclusion|final thoughts|key takeaways|in summary|summary|wrapping up|the bottom line)\s*$", re.I | re.M)
FIRST_PERSON = re.compile(r"\b(I|I'm|I've|I'd|me|my|mine|we|We|we're|We're|we've|We've|our|Our|ours|us)\b")
WORDS = {"cornerstone": (2200, 4200), "guide": (1100, 2600), "inspiration": (900, 2200), "feature": (800, 2000),
         "research": (800, 2400), "report": (2400, 5500)}
MIN_SECTIONS = {"cornerstone": 6, "guide": 4, "inspiration": 4, "feature": 3, "research": 3, "report": 6}
TYPES = set(WORDS)


def norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[\"'`*_]", "", s.lower())).strip()


def strip_quotes(text):
    """Prose with quotations removed (quoted words may use I/we and other phrasing)."""
    text = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith(">"))
    return re.sub(r'"[^"\n]{1,600}"', '""', text)


def prose_of(body):
    b = re.sub(r"\]\([^)]*\)", "]", body)
    b = re.sub(r"^\|.*\|\s*$", "", b, flags=re.M)        # tables are data, not prose
    return b


def numbers_in(text):
    """Numeric facts in text: money, percentages and numbers that are not list markers or tiny counts."""
    out = []
    for m in re.finditer(r"(?<![\w/.-])([£$€]|AED |USD |GBP |EUR )?(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)(\s?(?:%|per cent|percent|k\b|m\b|bn\b|million|billion))?", text):
        cur, num, suf = m.group(1), m.group(2), m.group(3)
        line_start = text.rfind("\n", 0, m.start()) + 1
        if re.fullmatch(r"\s*", text[line_start:m.start()]) and text[m.end():m.end() + 1] == ".":
            continue                                   # "1." numbered list marker
        val = float(num.replace(",", ""))
        if not cur and not suf and val <= 12:
            continue                                   # small counts ("3 questions") are not statistics
        if not cur and not suf and 1900 <= val <= 2100 and "." not in num:
            continue                                   # years are checked by the date rules, not here
        out.append((m.group(0).strip(), num.replace(",", "")))
    return out


def number_in_material(num, material_norm_nums):
    return num in material_norm_nums


def material_numbers(material_text):
    return set(n.replace(",", "") for n in re.findall(r"\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?", material_text))


def check_article(a, material_text=None, journal_links_available=0, require_images=False):
    errs = []
    for k in ("slug", "title", "dek", "body", "type", "cluster", "date"):
        if not a.get(k):
            errs.append(f"missing field: {k}")
    if errs:
        return errs
    if a["type"] not in TYPES:
        errs.append(f"type must be one of {', '.join(sorted(TYPES))}")
        return errs
    body = a["body"]
    faq = " ".join(f"{x.get('q', '')} {x.get('a', '')}" for x in a.get("faq") or [])
    everything = "\n".join([a["title"], a.get("seo_title", ""), a["dek"], body, faq])
    for ch, name in BANNED_CHARS.items():
        if ch in everything:
            errs.append(f"{name} found {everything.count(ch)}x")
    if EMOJI_RE.search(everything):
        errs.append("emoji or decorative symbol found")
    prose = strip_quotes(prose_of("\n".join([a["title"], a["dek"], body, faq])))
    for pat in BANNED:
        m = re.search(pat, prose, re.I)
        if m:
            errs.append(f"banned phrase: '{m.group(0)}'")
    for pat, mx in LIMITED.items():
        n = len(re.findall(pat, prose, re.I))
        if n > mx:
            errs.append(f"'{pat.strip(chr(92) + 'b')}' used {n} times (max {mx})")
    fp = FIRST_PERSON.findall(prose.replace("US$", "").replace(" US ", " ").replace("the US", "the States"))
    fp = [w for w in fp if w != "US"]
    if fp:
        errs.append(f"first person in Roko's voice ({', '.join(sorted(set(fp))[:5])}): write as Roko, not I or we")
    first_para = next((p.strip() for p in body.split("\n\n") if p.strip() and not p.strip().startswith(("#", ">", "-", "|", "!"))), "")
    if OPENERS.match(first_para):
        errs.append("generic opening: start with something specific")
    if BAD_HEADINGS.search(body):
        errs.append("no 'Conclusion' / 'Final thoughts' / 'Key takeaways' headings")
    words = len(re.findall(r"[A-Za-z0-9'%£$€]+", prose_of(body)))
    lo, hi = WORDS[a["type"]]
    if not lo <= words <= hi:
        errs.append(f"body is {words} words (want {lo} to {hi} for a {a['type']})")
    sections = len(re.findall(r"^## ", body, re.M))
    if sections < MIN_SECTIONS[a["type"]]:
        errs.append(f"need at least {MIN_SECTIONS[a['type']]} '## ' sections (has {sections})")
    if len(a["title"]) > 80:
        errs.append(f"title is {len(a['title'])} characters (max 80)")
    if len(a.get("seo_title") or a["title"]) > 65:
        errs.append("seo_title over 65 characters")
    if len(a["dek"]) > 230:
        errs.append(f"dek is {len(a['dek'])} characters (max 220)")
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", a["slug"]) or len(a["slug"]) > 80:
        errs.append("slug must be lowercase-hyphenated")
    if a["type"] not in ("feature",) and not a.get("sources"):
        errs.append("needs at least one source")
    if journal_links_available:
        jl = len(set(re.findall(r"\]\((/journal/[a-z0-9-]+)\)", body)))
        need = min(2, journal_links_available)
        if jl < need:
            errs.append(f"link to at least {need} other Journal article(s) from the LINKS list (has {jl})")
    if material_text is not None:
        mnums = material_numbers(material_text)
        bad = [shown for shown, num in numbers_in(prose_of(body) + "\n" + faq) if num not in mnums]
        if bad:
            errs.append("figures not found in the material (remove them or use only sourced figures): " + ", ".join(sorted(set(bad))[:8]))
        mn = norm(material_text)
        quotes = re.findall(r'"([^"\n]{20,600})"', body) + [l.lstrip("> ").strip() for l in body.splitlines()
                                                              if l.lstrip().startswith(">") and not l.lstrip("> ").startswith("**")]
        for q in quotes:
            q = q.strip().strip('"')
            if len(q.split()) >= 6 and norm(q)[:120] not in mn:
                errs.append(f"quote not found word for word in the material: \"{q[:60]}...\"")
                break
    if require_images:
        imgs = a.get("images") or []
        if not imgs or not str(imgs[0].get("url", "")).startswith("https://"):
            errs.append("needs a cover image")
        for im in imgs:
            if not im.get("credit"):
                errs.append("every image needs a credit")
                break
    return errs


def check_prose(text, material_text=None):
    """Checks for one section of an article: characters, banned phrases, first person, figures and quotes."""
    errs = []
    for ch, name in BANNED_CHARS.items():
        if ch in text:
            errs.append(f"{name} found")
    if EMOJI_RE.search(text):
        errs.append("emoji found")
    prose = strip_quotes(prose_of(text))
    for pat in BANNED:
        m = re.search(pat, prose, re.I)
        if m:
            errs.append(f"banned phrase: '{m.group(0)}'")
    fp = [w for w in FIRST_PERSON.findall(prose) if w != "US"]
    if fp:
        errs.append(f"first person ({', '.join(sorted(set(fp))[:5])}): write as Roko or address the reader as 'you', never I, me, my, we, us or our")
    if material_text is not None:
        mnums = material_numbers(material_text)
        bad = [shown for shown, num in numbers_in(prose_of(text)) if num not in mnums]
        if bad:
            errs.append("figures not in the material (remove them, or write the advice without numbers): " + ", ".join(sorted(set(bad))[:8]))
        mn = norm(material_text)
        quotes = re.findall(r'"([^"\n]{20,600})"', text) + [l.lstrip("> ").strip() for l in text.splitlines() if l.lstrip().startswith(">") and not l.lstrip("> ").startswith("**")]
        for q in quotes:
            q = q.strip().strip('"')
            if len(q.split()) >= 6 and norm(q)[:120] not in mn:
                errs.append(f"quote not found word for word in the material: \"{q[:60]}...\" (paraphrase it instead)")
                break
    return errs


def fix_links(body, internal_ok, external_ok):
    """Unwrap any link whose target is not allowed (invented paths, external pages that were not read)."""
    def repl(m):
        text, url = m.group(1), m.group(2).strip()
        u = url.split("#")[0]
        if u.startswith("/"):
            return m.group(0) if u.rstrip("/") in internal_ok else text
        if u in external_ok or u.rstrip("/") in external_ok:
            return m.group(0)
        return text
    return re.sub(r"(?<!!)\[([^\]]+)\]\(([^)\s]+)\)", repl, body)


if __name__ == "__main__" and len(sys.argv) == 2:
    a = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    e = check_article(a, require_images=True)
    if e:
        print("FAIL " + sys.argv[1]); [print("  - " + x) for x in e]; sys.exit(1)
    print("PASS " + sys.argv[1])
