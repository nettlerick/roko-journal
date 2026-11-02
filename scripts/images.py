#!/usr/bin/env python3
"""Real photographs for Roko Journal articles. No stock libraries (Pexels, Unsplash and the like) and no AI images.

Where photos come from, in order of preference:
  1. The live Roko website: photos from the profiles of businesses listed on Roko in the article's categories (only
     listings managed by their owner who have not switched off "Feature my photos in the Roko Journal"; their Terms
     licence covers this). Credited to the business, linking to its Roko profile.
  2. The live websites the article cites: each source page's own lead image, credited to that website with a link.
  3. Real, freely licensed photographs from Wikimedia Commons and Openverse (CC0, public domain, CC BY, CC BY-SA only),
     credited to the photographer with the licence.
Gemini (free tier) looks at every candidate and scores quality and relevance, and rejects anything that looks
AI-generated, illustrated, watermarked or like generic stock. A cover plus up to four images inside the article.

Images are saved as WebP under media/<slug>/ in this repository and served from the jsDelivr CDN at a fixed commit,
so nothing is stored on the website's own server. An article is published only once it has a cover photo.

  python3 scripts/images.py            add images to articles that need them, commit and push
  python3 scripts/images.py --dry-run  list candidates only
"""
import base64, io, json, os, re, subprocess, sys, time, urllib.parse, urllib.request
from common import (ARTICLES, MEDIA, REPO, ROKO_URL, ROOT, articles, directory, gemini_json, log, og_images, page, save_json, text_of)

DRY = "--dry-run" in sys.argv
UA = "RokoJournal/1.0 (https://withroko.com/journal; photo credits are shown with every image)"
STOCK = re.compile(r"pexels|unsplash|pixabay|shutterstock|istockphoto|gettyimages|stock\.adobe|adobestock|freepik|dreamstime|"
                   r"depositphotos|alamy|123rf|canva\.com|vecteezy|rawpixel|bigstock|stocksy", re.I)
REJECT = re.compile(r"\b(logo|logotype|map|flag|diagram|chart|graph|icon|screenshot|coat of arms|seal|emblem|infographic|svg|vector|"
                    r"banner|poster|wordmark|signature|document|placeholder|avatar|favicon|sprite)\b", re.I)
MAX_INLINE = {"cornerstone": 4, "guide": 3, "inspiration": 4, "feature": 4, "research": 1, "report": 2}
COVER = (2000, 1125)
TIME_BUDGET = int(os.environ.get("PHOTO_SECONDS", "900"))
START = time.time()


def get_json(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def download(url, limit=25_000_000):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; RokoJournal/1.0)", "Accept": "image/*"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read(limit)


def ok_licence(name):
    n = " " + (name or "").lower().replace("-", " ") + " "
    if " nc " in n or "noncommercial" in n or " nd " in n or "noderiv" in n or "fair use" in n:
        return False
    return any(k in n for k in ("cc0", "public domain", "pdm", "cc by", "attribution"))


# ------------------------------------------------------------------ candidate sources

def roko_candidates(a):
    out = []
    for ph in a.get("vendor_photos") or []:                                 # a feature's own business
        out.append({"src": "roko", "download": ph, "author": (a.get("people") or [{}])[0].get("business", ""), "page": (a.get("people") or [{}])[0].get("vendor_url", ""), "title": "", "license": "Shared on Roko by the business"})
    cats = set(a.get("categories") or [])
    if not cats and a.get("goal", {}).get("url", "").count("/") == 1:
        cats = {a["goal"]["url"].strip("/")}
    for v in directory().get("vendors", []):
        if not v.get("photos") or not (set(v.get("categories", [])) & cats):
            continue
        for ph in v["photos"][:4]:
            out.append({"src": "roko", "download": ph, "author": v["name"], "page": v["url"], "title": f"{v['name']} ({v.get('category_name', '')})", "license": "Shared on Roko by the business"})
    return out[:16]


def source_candidates(a):
    out = []
    for s in (a.get("sources") or [])[:6]:
        try:
            final, doc = page(s["url"])
        except Exception:
            continue
        for img in og_images(doc, final)[:1]:
            if STOCK.search(img) or REJECT.search(img.rsplit("/", 1)[-1]):
                continue
            alt = " ".join(re.findall(r'(?:og:image:alt|twitter:image:alt)["\'][^>]+content=["\']([^"\']+)', doc))[:200]
            caption = text_of(doc[doc.find("<figcaption"): doc.find("</figcaption>")]) if "<figcaption" in doc else ""
            if STOCK.search(alt + " " + caption):
                continue
            host = urllib.parse.urlparse(final).netloc.replace("www.", "")
            out.append({"src": "website", "download": img, "author": s.get("publisher") or host, "page": final, "title": alt or s["title"], "license": "Image from the cited website"})
    return out


def commons(query, quality=""):
    q = f"{query} filetype:bitmap" + (' incategory:"Quality_images"' if quality == "qi" else "")
    url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode({
        "action": "query", "format": "json", "generator": "search", "gsrnamespace": 6, "gsrlimit": 20, "gsrsearch": q,
        "prop": "imageinfo", "iiprop": "url|size|mime|extmetadata", "iiurlwidth": 2400})
    out = []
    for pg in (get_json(url).get("query", {}).get("pages", {}) or {}).values():
        ii = (pg.get("imageinfo") or [{}])[0]
        meta = ii.get("extmetadata", {})
        g = lambda k: text_of((meta.get(k) or {}).get("value", ""))
        title = pg.get("title", "").replace("File:", "")
        if ii.get("mime") not in ("image/jpeg", "image/png", "image/webp") or ii.get("width", 0) < 1800:
            continue
        lic = g("LicenseShortName")
        if not ok_licence(lic) or REJECT.search(title + " " + g("ImageDescription")[:200]) or re.search(r"\bAI[- ]generated|midjourney|stable diffusion|dall-?e\b", title + g("ImageDescription"), re.I):
            continue
        out.append({"src": "commons", "download": ii.get("thumburl") or ii.get("url"), "thumb": (ii.get("thumburl") or "").replace("/2400px-", "/800px-"),
                    "author": (g("Artist") or g("Credit") or "Unknown")[:120], "page": ii.get("descriptionurl", ""), "title": title,
                    "desc": g("ImageDescription")[:300], "license": lic, "license_url": g("LicenseUrl"), "provider": "Wikimedia Commons"})
    return out


def openverse(query):
    url = "https://api.openverse.org/v1/images/?" + urllib.parse.urlencode({
        "q": query, "license_type": "commercial,modification", "size": "large", "page_size": 20, "mature": "false"})
    out = []
    for r in get_json(url).get("results", []):
        tags = " ".join(t.get("name", "") for t in (r.get("tags") or []))
        if (r.get("width") or 0) < 1800 or REJECT.search((r.get("title") or "") + " " + tags[:200]) or STOCK.search((r.get("foreign_landing_url") or "") + (r.get("url") or "")):
            continue
        code, ver = (r.get("license") or "").lower(), r.get("license_version") or ""
        lic = "CC0" if code == "cc0" else "Public domain" if code == "pdm" else f"CC {code.upper()} {ver}".strip()
        if not ok_licence(lic):
            continue
        prov = (r.get("source") or r.get("provider") or "openverse").replace("_", " ").title()
        out.append({"src": "openverse", "download": r.get("url"), "thumb": r.get("thumbnail") or "", "author": (r.get("creator") or "Unknown")[:120],
                    "page": r.get("foreign_landing_url") or "", "title": r.get("title") or "", "desc": tags[:200],
                    "license": lic, "license_url": r.get("license_url") or "", "provider": f"{prov} via Openverse"})
    return out


def library_candidates(a):
    out, seen = [], set()
    queries = [q for q in (a.get("image_subjects") or []) if isinstance(q, str)][:5] or [a.get("keywords", [a["title"]])[0]]
    for q in queries:
        for fn in (lambda x: commons(x, "qi"), commons, openverse):
            try:
                for c in fn(q):
                    if c["page"] in seen:
                        continue
                    seen.add(c["page"]); c["query"] = q; out.append(c)
            except Exception as e:
                log(f"library search {q!r}: {str(e)[:100]}")
            time.sleep(0.3)
    return out


# ------------------------------------------------------------------ judging

def look(a, c):
    """Gemini looks at the photo. Returns the candidate with quality, relevance, real and alt filled in, or None."""
    try:
        raw = download(c.get("thumb") or c["download"], 15_000_000)
        from PIL import Image
        im = Image.open(io.BytesIO(raw)).convert("RGB")
        c["seen"] = im.size
        im.thumbnail((900, 900)); buf = io.BytesIO(); im.save(buf, "JPEG", quality=85)
        jpeg = base64.b64encode(buf.getvalue()).decode()
    except Exception as e:
        log(f"image unreadable {c['download'][:80]}: {str(e)[:60]}")
        return None
    try:
        d = gemini_json(
            f"Article: {a['title']}\n{a['dek']}\nPhoto source: {c['src']} | {c.get('title', '')[:120]}\n\n"
            "You are the picture editor of a premium wedding and events magazine judging this image for the article.\n"
            "quality (1 to 10): professional photography with deliberate composition, flattering light and clean colour scores high. "
            "Snapshots, clutter, blur, flash, heavy filters, text overlays, collages, watermarks or screenshots score low.\n"
            "relevance (1 to 10): how clearly it shows what the article is about (10 = exactly the subject; 5 = the general world of "
            "weddings or events; 2 = unrelated).\n"
            "real: false if it looks AI-generated, rendered, illustrated or composited; true for a genuine photograph.\n"
            "stock: true if it looks like a generic posed stock photo.\n"
            "people_identifiable: true if a person's face is clearly identifiable and central.\n"
            'Reply with JSON only: {"quality": n, "relevance": n, "real": true, "stock": false, "people_identifiable": false, '
            '"alt": "plain description of the photo for alt text, under 120 characters"}',
            "You judge photographs for a magazine. Be strict.", images=[jpeg], temperature=0.1, tokens=4096)
    except Exception as e:
        log(f"vision unavailable: {str(e)[:80]}")
        return None
    c.update({k: d.get(k) for k in ("quality", "relevance", "real", "stock", "people_identifiable", "alt")})
    return c


def acceptable(c, cover):
    if not c or not c.get("real") or c.get("stock"):
        return False
    q, r = float(c.get("quality") or 0), float(c.get("relevance") or 0)
    w = (c.get("seen") or (0, 0))[0]
    if c["src"] == "roko":
        return q >= 7 and r >= 5
    if c["src"] in ("commons", "openverse") and c.get("people_identifiable"):
        return False                      # identifiable strangers in library photos are left out
    return q >= 7 and r >= (6 if cover else 5)


# ------------------------------------------------------------------ saving

def save_webp(raw, path, cover):
    from PIL import Image, ImageOps
    im = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
    w, h = im.size
    if cover:
        if w < 1200:
            raise ValueError(f"only {w}px wide")
        target = COVER[0] / COVER[1]
        if w / h > target:
            nw = int(h * target); im = im.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
        else:
            nh = int(w / target); top = max(0, int((h - nh) * 0.38)); im = im.crop((0, top, w, top + nh))
        if im.size[0] > COVER[0]:
            im = im.resize(COVER, Image.LANCZOS)
    else:
        if w < 900:
            raise ValueError(f"only {w}px wide")
        if h / w > 1.35:                                    # very tall: crop to 4:5
            nh = int(w * 1.25); top = max(0, int((h - nh) * 0.3)); im = im.crop((0, top, w, top + nh))
        if im.size[0] > 1600:
            im = im.resize((1600, round(im.size[1] * 1600 / im.size[0])), Image.LANCZOS)
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, "WEBP", quality=84, method=6)
    return im.size


def credit_of(c):
    if c["src"] == "roko":
        return {"credit": f"Photo: {c['author']} on Roko", "credit_url": ROKO_URL + c["page"] if c["page"].startswith("/") else c["page"], "license": "Shared on Roko by the business"}
    if c["src"] == "website":
        return {"credit": f"Photo: {c['author']}", "credit_url": c["page"], "license": "Image from the cited website"}
    author = re.sub(r"\s+", " ", c["author"])
    return {"credit": f"Photo: {author}, {c['license']}, via {c.get('provider', '')}", "credit_url": c["page"],
            "license": c["license"], "license_url": c.get("license_url", "")}


def git(*args):
    r = subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip()[:300]}")
    return r.stdout.strip()


def process(a):
    log(f"photos for {a['slug']}")
    cands = roko_candidates(a) + source_candidates(a)
    lib = library_candidates(a)
    chosen, used = [], set()
    want = 1 + MAX_INLINE.get(a["type"], 2)
    for pool in (cands, lib):
        for c in pool:
            if len(chosen) >= want or time.time() - START > TIME_BUDGET:
                break
            if c["download"] in used or STOCK.search(c["download"] + " " + c.get("page", "")):
                continue
            used.add(c["download"])
            c = look(a, c)
            if acceptable(c, cover=not chosen):
                chosen.append(c)
        if len(chosen) >= want:
            break
    if not chosen:
        log(f"no suitable photo yet for {a['slug']}; it waits for the next run")
        return None
    chosen.sort(key=lambda c: -(float(c.get("quality") or 0) + float(c.get("relevance") or 0)))
    saved = []
    for i, c in enumerate(chosen):
        name = "cover.webp" if not saved else f"{len(saved)}.webp"
        path = MEDIA / a["slug"] / name
        try:
            size = save_webp(download(c["download"]), path, cover=not saved)
        except Exception as e:
            log(f"save failed {c['download'][:70]}: {str(e)[:60]}")
            continue
        saved.append(dict(credit_of(c), file=f"media/{a['slug']}/{name}", width=size[0], height=size[1], alt=(c.get("alt") or a["title"])[:150], source=c["src"]))
    return saved or None


def main():
    pending = [a for a in articles() if not a.get("images")]
    if not pending:
        log("no articles waiting for photos"); return
    done = {}
    for a in pending:
        if time.time() - START > TIME_BUDGET:
            break
        if DRY:
            log(json.dumps([c["download"] for c in roko_candidates(a) + source_candidates(a)][:10], indent=1)); continue
        imgs = process(a)
        if imgs:
            done[a["slug"]] = imgs
    if not done or DRY:
        return
    git("add", "media")
    git("commit", "-m", "Journal photos: " + ", ".join(done))
    git("pull", "--rebase", "origin", "main")
    git("push", "origin", "HEAD:main")
    sha = git("rev-parse", "HEAD")
    for a in articles():
        if a["slug"] in done:
            a["images"] = [dict(im, url=f"https://cdn.jsdelivr.net/gh/{REPO}@{sha}/{im['file']}") for im in done[a["slug"]]]
            f = a.pop("_file")
            save_json(f, a)
            log(f"images added to {a['slug']}")


if __name__ == "__main__":
    main()
