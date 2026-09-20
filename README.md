# eTenders Scraper API

A FastAPI service that scrapes tender listings from South Africa's National
Treasury eTenders portal (**etenders.gov.za**) — the official government
e-procurement platform.

## Why this uses a headless browser (Playwright), not `requests`

The portal's tender table is rendered **client-side**: the initial HTML you
get from a plain HTTP request contains an empty table with "loading, please
wait..." text, and the actual rows are injected afterwards by JavaScript
(an AJAX call feeding a DataTables grid). A `requests` + `BeautifulSoup`
scraper would only ever see the empty shell.

This project uses [Playwright](https://playwright.dev/python/) to drive a
real headless Chromium browser: it loads the page, waits for the table to
actually populate, then reads the rendered rows out of the DOM. It can also
walk through pagination pages.

## Setup

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt

# Playwright needs to download a browser binary once:
playwright install chromium
# On Linux you may also need OS-level deps:
playwright install-deps chromium
```

## Running

```bash
# On Windows, do not use --reload: Playwright needs the Proactor event loop.
uvicorn app.main:app --port 8000
```

Then open http://localhost:8000/docs for interactive Swagger docs.

## Endpoints

### `GET /health`
Simple liveness check.

### `GET /tenders`
Scrapes tender listings.

| Query param | Default   | Description |
|-------------|-----------|-------------|
| `status`    | `current` | One of `current`, `awarded`, `cancelled`, `closed` — matches the portal's four tabs. |
| `max_pages` | `3`       | How many result pages to page through (hard-capped at 20 per request). |
| `keyword`   | *(none)*  | Case-insensitive filter applied to category + description after scraping. |
| `refresh`   | `false`   | Set `true` to bypass the in-memory cache and force a fresh scrape. |

Example:

```bash
curl "http://localhost:8000/tenders?status=current&max_pages=2&keyword=security"
```

Response shape:

```json
{
  "status": "current",
  "source_url": "https://www.etenders.gov.za/Home/opportunities?id=1",
  "count": 42,
  "pages_scraped": 2,
  "tenders": [
    {
      "category": "Security and investigation activities",
      "description": "Appointment of a service provider for...",
      "tender_number": null,
      "e_submission": "Yes",
      "advertised_date": "12 Sep 2026",
      "closing_date": "10 Oct 2026",
      "detail_url": "https://www.etenders.gov.za/...",
      "raw_cells": ["Security and investigation activities", "..."]
    }
  ]
}
```

`raw_cells` is always included so you can see exactly what was scraped even
if the structured fields (`category`, `description`, etc.) didn't map
cleanly — useful for debugging if the portal tweaks its table layout.

## Important notes / limitations

- **Selectors may need tweaking over time.** Government portals like this one
  occasionally change their markup. All the CSS selectors this scraper
  depends on live at the top of `app/scraper.py` (`TABLE_SELECTOR`,
  `ROW_SELECTOR`, `NEXT_BUTTON_SELECTOR`) — if scraping starts failing,
  that's the first place to check by inspecting the live page in a browser's
  dev tools.
- **`tender_number` is currently unpopulated** — the portal doesn't show it
  directly in the summary table; it's typically inside the expandable row
  detail or the detail page linked from each row. If you need it, the
  `detail_url` field (when present) is the place to scrape further from.
- **Respect the portal's terms of use and load.** This scraper launches a
  real browser per request (mitigated by the built-in cache); avoid hammering
  it with a very high request rate or very high `max_pages` values.
- **Not a workaround for authentication.** Some actions on the real portal
  (bookmarking tenders, downloading certain documents) require a logged-in
  session — this scraper only reads the public, unauthenticated tender
  listings.
- If you actually need a **different** e-tender portal (many countries and
  even South African municipalities run their own), the `ETENDERS_BASE_URL`
  environment variable lets you point this at another site, but you'll very
  likely need to adjust the selectors and the `status_ids` mapping in
  `app/config.py` to match that site's markup.

## Configuration (environment variables)

| Variable | Default | Purpose |
|---|---|---|
| `ETENDERS_BASE_URL` | `https://www.etenders.gov.za` | Portal base URL |
| `ETENDERS_TABLE_TIMEOUT_MS` | `20000` | Max time to wait for the table to populate |
| `ETENDERS_MAX_PAGES_DEFAULT` | `3` | Default pagination depth per request |
| `ETENDERS_MAX_PAGES_HARD_CAP` | `20` | Absolute max pages per request |
| `ETENDERS_CACHE_TTL_SECONDS` | `300` | In-memory cache lifetime |
| `ETENDERS_USER_AGENT` | (a modern Chrome UA string) | Browser UA sent by Playwright |

## Project structure

```
etenders_scraper_api/
├── app/
│   ├── __init__.py
│   ├── main.py       # FastAPI routes
│   ├── scraper.py     # Playwright scraping logic
│   ├── models.py       # Pydantic response models
│   └── config.py       # Settings
├── requirements.txt
└── README.md
```
