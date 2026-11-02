"""Shared helpers for the Roko Journal pipeline (Gemini, fetching pages and feeds, the Roko API)."""
import datetime, email.utils, html, json, os, re, time, urllib.error, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content"
ARTICLES = CONTENT / "articles"
RESEARCH = ROOT / "research"
MEDIA = ROOT / "media"
TZ = ZoneInfo("Europe/London")
REPO = os.environ.get("GITHUB_REPOSITORY") or "nettlerick/roko-journal"
ROKO_URL = (os.environ.get("ROKO_URL") or "https://withroko.com").rstrip("/")
ROKO_KEY = os.environ.get("ROKO_JOURNAL_KEY", "")
KEY = os.environ.get("GEMINI_API_KEY", "")
MODELS = [m for m in [os.environ.get("GEMINI_TEXT_MODEL"), "gemini-3-flash-preview", "gemini-flash-latest",
                      "gemini-3.5-flash", "gemini-flash-lite-latest", "gemini-3.5-flash-lite"] if m]
UA = "Mozilla/5.0 (compatible; RokoJournal/1.0; +https://withroko.com/journal)"
BROWSER = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
           "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "Accept-Language": "en-GB,en;q=0.9"}


def log(*a):
    print(*a, flush=True)


def now():
    return datetime.datetime.now(TZ)


def load_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def slugify(s):
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", s.lower())).strip("-")[:70].strip("-")


def text_of(s):
    s = html.unescape(re.sub(r"<[^>]+>", " ", s or ""))
    return re.sub(r"\s+", " ", s).strip()


def clean(s):
    """Typographic tidy-up: no dashes, curly quotes or ellipsis characters (they read as machine-written)."""
    if not isinstance(s, str):
        return s
    s = re.sub(r"\s*[—]\s*", ", ", s)
    s = re.sub(r"(\d)\s*[–]\s*(\d)", r"\1 to \2", s)
    s = re.sub(r"\s*[–]\s*", ", ", s)
    s = s.replace("…", "...").replace("‘", "'").replace("’", "'").replace("“", '"').replace("”", '"')
    s = s.replace(" ", " ")
    return re.sub(r" ,", ",", s)


# ------------------------------------------------------------------ Gemini

def gemini(prompt, system, temperature=0.6, tokens=16384, json_mode=True, images=None):
    """Gemini (free tier). Tries each model; a busy model moves on quickly. Returns text."""
    if not KEY:
        raise RuntimeError("GEMINI_API_KEY is not set")
    parts = [{"inline_data": {"mime_type": "image/jpeg", "data": b}} for b in (images or [])] + [{"text": prompt}]
    cfg = {"temperature": temperature, "maxOutputTokens": tokens}
    if json_mode:
        cfg["responseMimeType"] = "application/json"
    body = {"systemInstruction": {"parts": [{"text": system}]}, "contents": [{"role": "user", "parts": parts}], "generationConfig": cfg}
    last = None
    for rnd in range(3):
        for model in MODELS:
            req = urllib.request.Request(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                                         data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "x-goog-api-key": KEY})
            try:
                with urllib.request.urlopen(req, timeout=240) as r:
                    data = json.load(r)
                cand = (data.get("candidates") or [{}])[0]
                text = "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", []) if not p.get("thought"))
                if text.strip():
                    return text
                last = f"{model}: empty response ({cand.get('finishReason')})"
            except urllib.error.HTTPError as e:
                last = f"{model} HTTP {e.code}: {e.read().decode(errors='ignore')[:200]}"
            except Exception as e:
                last = f"{model}: {e}"
            log(last)
        time.sleep(30 * (rnd + 1))
    raise RuntimeError("Gemini unavailable: " + str(last))


def parse_json(text):
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    m = re.search(r"\{.*\}", t, re.S)
    if not m:
        raise ValueError("no JSON object in model output")
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return json.loads(m.group(0), strict=False)     # raw newlines inside strings


def gemini_json(prompt, system, **kw):
    return parse_json(gemini(prompt, system, **kw))


# ------------------------------------------------------------------ fetching

_PAGES = {}


def fetch(url, timeout=25, limit=4_000_000, headers=None):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.geturl(), r.read(limit)


def page(url):
    """A web page as a browser would see it (cached per run). Returns (final_url, html)."""
    if url in _PAGES:
        if isinstance(_PAGES[url], Exception):
            raise _PAGES[url]
        return _PAGES[url]
    try:
        final, raw = fetch(url, headers=BROWSER)
        _PAGES[url] = (final, raw.decode("utf-8", "ignore"))
    except Exception as e:
        _PAGES[url] = e
        raise
    return _PAGES[url]


def readable(url, limit=12000):
    """Readable text of a page: headings, paragraphs, list items and table cells. Returns (final_url, title, text, html)."""
    final, doc = page(url)
    body = re.sub(r"(?is)<(script|style|nav|footer|header|aside|form|noscript|svg)[^>]*>.*?</\1>", " ", doc)
    blocks = []
    for tag, inner in re.findall(r"(?is)<(h[1-4]|p|li|td|th|blockquote)[^>]*>(.*?)</\1>", body):
        t = text_of(inner)
        if len(t) < 3 or re.search(r"cookie|subscribe to|sign up for|newsletter|all rights reserved|javascript", t, re.I):
            continue
        blocks.append(("## " + t) if tag.lower().startswith("h") else t)
    text, seen = [], set()
    for b in blocks:
        if b in seen:
            continue
        seen.add(b); text.append(b)
    m = re.search(r"(?is)<title[^>]*>(.*?)</title>", doc)
    return final, (text_of(m.group(1)) if m else ""), "\n".join(text)[:limit], doc


def og_images(doc, base):
    imgs = re.findall(r'<meta[^>]+(?:property|name)=["\'](?:og:image|og:image:secure_url|twitter:image)["\'][^>]+content=["\']([^"\']+)', doc)
    imgs += re.findall(r'content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\'](?:og:image|twitter:image)', doc)
    out = []
    for i in imgs:
        u = urllib.parse.urljoin(base, html.unescape(i))
        if u not in out:
            out.append(u)
    return out


# ------------------------------------------------------------------ feeds

def parse_date(s):
    if not s:
        return None
    s = s.strip()
    try:
        d = email.utils.parsedate_to_datetime(s)
    except Exception:
        try:
            d = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=datetime.timezone.utc)
    return d


def parse_feed(raw):
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return parse_feed_loose(raw)
    items, strip = [], (lambda t: t.split("}", 1)[-1])
    for el in root.iter():
        if strip(el.tag) not in ("item", "entry"):
            continue
        d = {strip(c.tag): c for c in el}
        title = text_of(d["title"].text if "title" in d else "")
        link = ""
        if "link" in d:
            link = (d["link"].text or "").strip() or d["link"].get("href", "")
        for c in el:
            if strip(c.tag) == "link" and c.get("rel", "alternate") == "alternate" and c.get("href"):
                link = c.get("href")
        when = None
        for k in ("pubDate", "published", "updated", "date"):
            if k in d and d[k].text:
                when = parse_date(d[k].text)
                if when:
                    break
        desc = ""
        for k in ("description", "summary", "content", "encoded"):
            if k in d and (d[k].text or "").strip():
                desc = text_of(d[k].text)[:600]
                break
        if title and link.startswith("http"):
            items.append({"title": title, "url": link.strip(), "date": when, "summary": desc})
    return items


def parse_feed_loose(raw):
    text = raw.decode("utf-8", "ignore")
    grab = lambda tag, block: (re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", block, re.S | re.I) or [None, ""])[1]
    items = []
    for block in re.findall(r"<(?:item|entry)\b.*?</(?:item|entry)>", text, re.S | re.I):
        title = text_of(re.sub(r"<!\[CDATA\[|\]\]>", "", grab("title", block)))
        link = text_of(grab("link", block)) or (re.search(r'<link[^>]+href="([^"]+)"', block) or [None, ""])[1]
        when = None
        for k in ("pubDate", "published", "updated", "dc:date"):
            when = parse_date(text_of(grab(k, block)))
            if when:
                break
        desc = text_of(re.sub(r"<!\[CDATA\[|\]\]>", "", grab("description", block) or grab("summary", block)))[:600]
        if title and link.startswith("http"):
            items.append({"title": title, "url": link.strip(), "date": when, "summary": desc})
    return items


# ------------------------------------------------------------------ Roko

def roko(path, private=False):
    """GET a Roko journal API endpoint. Private endpoints need ROKO_JOURNAL_KEY."""
    url = ROKO_URL + path
    headers = {"User-Agent": UA, "Accept": "application/json"}
    if private:
        if not ROKO_KEY:
            raise RuntimeError("ROKO_JOURNAL_KEY is not set")
        headers["X-Journal-Key"] = ROKO_KEY
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.load(r)


_DIR = None


def directory():
    """Public directory index from Roko: category pages that have businesses, and public business profiles."""
    global _DIR
    if _DIR is None:
        try:
            _DIR = roko("/api/journal/directory")
        except Exception as e:
            log(f"Roko directory unavailable: {e}")
            _DIR = {"categories": [], "pages": {}, "vendors": []}
    return _DIR


# ------------------------------------------------------------------ articles

def articles():
    out = []
    for f in sorted(ARTICLES.glob("*.json")):
        a = load_json(f)
        if isinstance(a, dict) and a.get("slug"):
            a["_file"] = str(f)
            out.append(a)
    return out


def roadmap():
    return load_json(CONTENT / "roadmap.json", {"clusters": {}, "items": []})


def sources():
    return load_json(CONTENT / "sources.json", {"references": {}, "feeds": []})


# ------------------------------------------------------------------ competitors (never read, cited, linked, named or used for photos)

_BL = None


def blocked():
    global _BL
    if _BL is None:
        b = sources().get("blocked", {})
        names = []
        for n in b.get("names", []):
            if n == "The Knot":
                names.append(r"(?<![Tt]ie )\bThe Knot\b")            # "tie the knot" is an ordinary phrase
            elif n == "Hitched":
                names.append(r"(?<=[a-z,;:] )Hitched\b|^Hitched\b|Hitched\.co\.uk")   # the company, not "got hitched"
            else:
                names.append(r"\b" + re.escape(n) + r"\b")
        _BL = (re.compile("|".join(names), re.M) if names else None, [x.lower() for x in b.get("domains", [])])
    return _BL


def blocked_url(url):
    host = urllib.parse.urlparse(url or "").netloc.lower().replace("www.", "")
    return any(host == d or host.endswith("." + d) for d in blocked()[1])


def blocked_name(text):
    rx = blocked()[0]
    m = rx.search(text or "") if rx else None
    return m.group(0) if m else ""


def scrub(text):
    """Remove every sentence that names a competitor, so nothing from them reaches the writer."""
    rx = blocked()[0]
    if not rx or not text:
        return text
    parts = re.split(r"(?<=[.!?])\s+|\n", text)
    return "\n".join(p for p in parts if p.strip() and not rx.search(p) and not any(d in p.lower() for d in blocked()[1]))
