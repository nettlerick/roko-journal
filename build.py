#!/usr/bin/env python3
"""Build dist/journal.json, the single file the Roko website reads (Roko > Admin > Journal > Sync).

Only articles that pass the editorial checks and have a cover photo are included. The Markdown body is rendered to
HTML here, so the website only has to display it. Roko keeps its copy in its database, so no files are added to
the web server; photos are served from this repository through the jsDelivr CDN.

  python3 build.py
"""
import datetime, html, json, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))
from common import CONTENT, RESEARCH, ROOT, REPO, articles, load_json, roadmap, save_json, now  # noqa: E402
from check import check_article  # noqa: E402

OUT = ROOT / "dist" / "journal.json"


def inline(s):
    s = html.escape(s, quote=False)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", s)

    def link(m):
        text, url = m.group(1), html.unescape(m.group(2))
        if url.startswith("/"):
            return f'<a href="{html.escape(url)}">{text}</a>'
        return f'<a href="{html.escape(url)}" target="_blank" rel="noopener">{text}</a>'
    return re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", link, s)


def slug_id(t, used):
    b = re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", t.lower())).strip("-")[:60] or "section"
    i, out = 2, b
    while out in used:
        out = f"{b}-{i}"; i += 1
    used.add(out)
    return out


def render(md):
    """Small Markdown renderer: ## and ### headings, paragraphs, lists, tables, blockquotes, bold, italic and links."""
    lines = md.replace("\r", "").split("\n")
    out, toc, used, i = [], [], set(), 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1; continue
        m = re.match(r"^(#{2,3})\s+(.*)$", line)
        if m:
            lvl, text = len(m.group(1)), m.group(2).strip()
            hid = slug_id(text, used)
            if lvl == 2:
                toc.append({"id": hid, "title": text})
            out.append(f'<h{lvl} id="{hid}">{inline(text)}</h{lvl}>'); i += 1; continue
        if line.lstrip().startswith(">"):
            block = []
            while i < len(lines) and lines[i].lstrip().startswith(">"):
                block.append(lines[i].lstrip()[1:].strip()); i += 1
            cite = ""
            if block and re.match(r"^\*\*.+\*\*", block[-1]):
                cite = block.pop()
            body = "".join(f"<p>{inline(b)}</p>" for b in block if b)
            out.append(f'<blockquote>{body}{f"<cite>{inline(cite)}</cite>" if cite else ""}</blockquote>'); continue
        if re.match(r"^\s*\|", line):
            rows = []
            while i < len(lines) and re.match(r"^\s*\|", lines[i]):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")]); i += 1
            rows = [r for r in rows if not all(re.fullmatch(r":?-{2,}:?", c) for c in r)]
            if rows:
                head = "".join(f"<th>{inline(c)}</th>" for c in rows[0])
                body = "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in rows[1:])
                out.append(f'<div class="jr-table"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>')
            continue
        m = re.match(r"^\s*([-*]|\d+\.)\s+", line)
        if m:
            ordered = m.group(1)[0].isdigit()
            items = []
            while i < len(lines) and re.match(r"^\s*([-*]|\d+\.)\s+", lines[i]):
                items.append(re.sub(r"^\s*([-*]|\d+\.)\s+", "", lines[i])); i += 1
                while i < len(lines) and lines[i].startswith("  ") and lines[i].strip() and not re.match(r"^\s*([-*]|\d+\.)\s+", lines[i]):
                    items[-1] += " " + lines[i].strip(); i += 1
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>" + "".join(f"<li>{inline(x)}</li>" for x in items) + f"</{tag}>"); continue
        para = [line.strip()]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(r"^(#{2,3}\s|\s*>|\s*\||\s*([-*]|\d+\.)\s+)", lines[i]):
            para.append(lines[i].strip()); i += 1
        out.append(f"<p>{inline(' '.join(para))}</p>")
    return out, toc


def figure(im, cls):
    cap = f'<a href="{html.escape(im["credit_url"])}" target="_blank" rel="noopener">{html.escape(im["credit"])}</a>' if im.get("credit_url") else html.escape(im["credit"])
    return (f'<figure class="{cls}"><img src="{html.escape(im["url"])}" alt="{html.escape(im.get("alt", ""))}" width="{im.get("width", "")}" '
            f'height="{im.get("height", "")}" loading="lazy" decoding="async"><figcaption>{cap}</figcaption></figure>')


def with_images(blocks, images):
    """Place the inline photos evenly before section headings (never before the first)."""
    heads = [k for k, b in enumerate(blocks) if b.startswith("<h2")]
    inl = images[1:]
    if not inl or len(heads) < 2:
        return "".join(blocks) + "".join(figure(im, "jr-figure") for im in inl[:1])
    step = max(1, (len(heads) - 1) / (len(inl) + 0.5))
    spots = sorted({heads[min(len(heads) - 1, int(1 + n * step))] for n in range(len(inl))})
    out, n = [], 0
    for k, b in enumerate(blocks):
        if k in spots and n < len(inl):
            out.append(figure(inl[n], "jr-figure")); n += 1
        out.append(b)
    return "".join(out)


def words(md):
    return len(re.findall(r"[A-Za-z0-9'%£$€]+", re.sub(r"\]\([^)]*\)", "]", md)))


def main():
    rm = roadmap()
    pub, waiting, problems = [], [], {}
    for a in articles():
        a.pop("_file", None)
        errs = check_article(a, require_images=True)
        if errs:
            (waiting if errs == ["needs a cover image"] or not a.get("images") else []).append(a["slug"])
            problems[a["slug"]] = errs
            continue
        blocks, toc = render(a["body"])
        a["html"] = with_images(blocks, a["images"])
        a["toc"] = toc if a["type"] in ("cornerstone", "report", "guide", "research") and len(toc) >= 4 else []
        a["words"] = words(a["body"])
        a["reading_minutes"] = max(1, round(a["words"] / 230))
        a["faq_html"] = [{"q": html.escape(x["q"]), "a": inline(x["a"])} for x in a.get("faq") or []]
        a["cover"] = a["images"][0]
        pub.append(a)
    pub.sort(key=lambda a: a["date"], reverse=True)
    status = {a.get("roadmap"): "published" for a in pub if a.get("roadmap")}
    for a in articles():
        if a.get("roadmap") and a["slug"] in waiting:
            status.setdefault(a["roadmap"], "waiting for photo")
    attempts = load_json(CONTENT / "attempts.json", {})
    rmap = [dict(n=i["n"], title=i["title"], slug=i["slug"], cluster=i["cluster"], type=i["type"], cornerstone=i["cornerstone"],
                 priority=i["priority"], week=i["week"], why=i["why"], goal=i["goal"],
                 status=status.get(i["n"]) or ("failed " + str(attempts[i["slug"]]["count"]) + "x" if i["slug"] in attempts else "planned"))
            for i in rm["items"]]
    digest = load_json(RESEARCH / "digest.json", {})
    research = {k: digest.get(k) for k in ("generated", "rising_searches", "trending", "page_changes")}
    research["feed_items"] = (digest.get("feed_items") or [])[:60]
    research["headlines"] = (digest.get("headlines") or [])[:60]
    research["pages"] = digest.get("pages") or {}
    data = {"generated": now().isoformat(timespec="seconds"), "repo": REPO, "clusters": rm["clusters"], "roadmap": rmap,
            "articles": pub, "waiting": waiting, "problems": problems, "attempts": attempts, "research": research}
    save_json(OUT, data)
    print(f"built {len(pub)} article(s); {len(waiting)} waiting for photos; {len(problems)} with problems")


if __name__ == "__main__":
    main()
