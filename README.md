# Roko Journal

The research, writing and photo pipeline behind the Roko Journal (withroko.com/journal) and Roko Reports (withroko.com/reports).

Everything runs on GitHub Actions with Gemini's free tier, so it uses no Claude credits. Nothing is stored on the website's server: Roko reads `dist/journal.json` from this repository into its database, and the photos load from the jsDelivr CDN at a fixed commit.

## How it works

1. **Research** (`scripts/research.py`, every run). Monitors luxury, travel and hospitality publications, ONS and Bing News; Google's search suggestions in the UK and US (weekly, so new searches show up); Google Trends; news coverage of Instagram, TikTok and Pinterest trends; market research pages (monthly, so new reports are spotted); and Roko's own anonymised data, reader polls, approved business answers and the team's research notes. Output: `research/digest.json`.
2. **Writing** (`scripts/write.py`). One new article a day, written at 02:07 UTC (backup run 05:07). Each day's article is, in order:
   - the next article from `content/roadmap.json` (the first-90-days order, then the rest of the 100), unless one of these is due:
   - 1 Meet the Makers business feature a fortnight, only from a business's own approved answers;
   - 1 original research feature a month;
   - the State of Weddings report every January;
   - time-sensitive guides refreshed at six months.
   Gemini gets the editorial guide (`content/WRITING_GUIDE.md`), the brief, the only internal links it may use, and the MATERIAL it may take facts from. `scripts/check.py` then rejects any draft with figures or quotes that are not in the material, first-person writing, AI phrasing, dashes, missing links or the wrong length, and Gemini corrects it (up to three attempts).
3. **Photos** (`scripts/images.py`). Real photographs only, never stock libraries or AI images: photos from businesses' Roko profiles (where the owner allows it), the lead images of the websites the article cites, then Wikimedia Commons and Openverse (commercial-use licences only). Gemini checks each one for quality, relevance and signs of AI or stock. Every photo is credited. An article is published only once it has a cover photo.
4. **Build** (`build.py`). Validates every article and writes `dist/journal.json`.
5. **Roko** syncs every 30 minutes (and can start a run by hand from Admin > Journal). Guides go live automatically; features, research and reports wait for approval in Admin > Journal.

## Competitors

Wedding directories, planning platforms, gift registries and wedding blogs with supplier directories are never read, cited, linked, named or used for photos. The list is `blocked` in `content/sources.json`; the checks reject any article that names one.

## Secrets and variables

| Name | Where | What |
|---|---|---|
| `GEMINI_API_KEY` | Secret | Free key from aistudio.google.com/apikey |
| `ROKO_JOURNAL_KEY` | Secret | From Roko > Admin > Journal > Settings |
| `ROKO_URL` | Variable (optional) | Defaults to https://withroko.com |
| `GEMINI_TEXT_MODEL` | Variable (optional) | A preferred Gemini model |

## Running by hand

Actions > Journal > Run workflow. Leave the task empty for a normal run, or enter `next`, a roadmap number (e.g. `26`), `feature`, `research`, `report` or `refresh:<slug>`. Enter `feeds` in "check" to see which research feeds answer.

## Editing

- The plan: `content/roadmap.json` (titles, clusters, cornerstones, sources, conversion goals, order).
- The voice and rules: `content/WRITING_GUIDE.md`.
- Sources and feeds: `content/sources.json`.
- To unpublish an article, hide it in Roko's admin, or delete its file in `content/articles/`.
