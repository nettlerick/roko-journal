#!/usr/bin/env python3
"""One-off: gather candidate photos from Wikimedia Commons for the curated photo library.

Downloads small previews into library_review/ with an index, so an editor can pick the photos that go into
content/photo_library.json (used whenever the automatic picture check is unavailable). Run with check=library;
the previews are pushed to the 'library-review' branch, never to main.
"""
import json, os, sys, time, urllib.request
sys.path.insert(0, os.path.dirname(__file__))
from images import commons, download
from common import ROOT, log

QUERIES = {
    "venues": ["wedding reception hall", "banquet hall interior", "manor house", "castle courtyard", "palace garden", "hotel ballroom", "barn interior", "vineyard estate"],
    "flowers-styling": ["wedding bouquet", "flower arrangement roses", "peonies bouquet", "table setting candles", "floral arch", "wedding decoration flowers"],
    "catering": ["wedding cake", "banquet table food", "dessert table", "champagne glasses", "canapes", "wine glasses table"],
    "photography": ["camera lens", "film camera", "photographer camera"],
    "destination": ["Santorini", "Lake Como", "Amalfi coast", "Tuscany villa", "Algarve coast", "Dubai skyline", "Bali temple", "Provence lavender", "Udaipur palace", "Marrakech riad"],
    "planning": ["notebook pen desk", "wedding rings", "wedding invitations", "calendar desk"],
    "entertainment": ["string quartet", "dance floor lights", "jazz band", "grand piano"],
    "luxury": ["chandelier", "palace interior", "luxury hotel lobby", "silverware table"],
    "private-events": ["dinner party table", "birthday cake candles", "cocktail bar", "garden party"],
    "seasons": ["autumn leaves", "pumpkins harvest", "winter snow forest", "spring blossom", "summer garden roses"],
}
out = ROOT / "library_review"
out.mkdir(exist_ok=True)
index, seen, n = [], set(), 0
for cluster, qs in QUERIES.items():
    for q in qs:
        cands = []
        for mode in ("qi", ""):
            try:
                cands += commons(q, mode)
            except Exception as e:
                log(f"{q} {mode}: {e}")
            time.sleep(0.5)
        k = 0
        for c in cands:
            if c["page"] in seen or k >= 8:
                continue
            seen.add(c["page"])
            try:
                raw = download(c["thumb"] or c["download"], 3_000_000)
            except Exception as e:
                log(f"preview failed {c['title']}: {e}")
                continue
            n += 1; k += 1
            fid = f"{n:04d}"
            (out / f"{fid}.jpg").write_bytes(raw)
            index.append(dict(id=fid, cluster=cluster, query=q, **{x: c.get(x) for x in ("title", "desc", "author", "license", "license_url", "page", "download")}))
            time.sleep(0.3)
        log(f"{cluster} / {q}: {k}")
(out / "index.json").write_text(json.dumps(index, indent=1, ensure_ascii=False))
log(f"{n} previews")
