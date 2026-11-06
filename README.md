# LinkedIn Organisation Crawler

Phase 1 of the Cyberyan AI-engineer assignment: a crawler that, given a company,
finds it on LinkedIn, discovers its employees and extracts for each profile:

| Section | Fields |
|---|---|
| Basic info | name, headline, location, connections, followers, about |
| Experience | title, company (+URL), employment type, dates, location, workplace type, description, skills |
| Education | school (+URL), degree, field, dates, grade, activities, description |
| Skills | name, endorsements, context ("3 experiences at …"), assessment passed |
| Activity | post / repost / comment, author, text, relative time, reactions, comments, reposts |

Built with **Playwright** (browser automation), **BeautifulSoup + lxml** (parsing),
**Pydantic** (domain models), **pandas** (tabular export) and an optional
**Redis** queue.

---

## Quick start

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows  (Linux/macOS: source .venv/bin/activate)
pip install -e ".[dev,redis]"
# Only needed if you do NOT use your installed Google Chrome (LI_BROWSER_CHANNEL=""):
playwright install chromium
```

**1. Log in once** – a browser window opens; log in to LinkedIn by hand
(complete any 2FA yourself), then press Enter in the terminal. The session is
stored in `.browser-profile/` and reused by later runs.

```bash
python -m li_crawler login
```

**2. Crawl a company** – by name (the best search match is used) or by URL:

```bash
python -m li_crawler crawl "Cafe Bazaar" --max-profiles 10
python -m li_crawler crawl https://www.linkedin.com/company/cafebazaar/ -n 10
python -m li_crawler crawl "Cafe Bazaar" --sections main experience skills
```

**3. Re-parse offline** – rebuild the dataset from the saved HTML (no network):

```bash
python -m li_crawler reparse
```

**Run the tests**

```bash
pytest
```

> The LinkedIn UI language must be **English** – the parser recognises labels
> such as "Experience", "Present" and "endorsements".

## Output

```
data/
  profiles.json          full nested documents (list)
  profiles.csv           one row per person
  experiences.csv        one row per role        ┐
  education.csv          one row per school      │ joined on profile_slug
  skills.csv             one row per skill       │ (ready for pandas)
  activities.csv         one row per feed item   ┘
  profiles/<slug>.json   one document per profile
  raw/                   original HTML of every page (for offline re-parsing)
```

## Architecture (hexagonal / ports & adapters)

```
                 ┌────────────────────────── application ──────────────────────────┐
  CLI ──────────▶│  CrawlCompanyUseCase / ReparseUseCase                            │
 (inbound        │        │ depends only on ports (Protocols)                       │
  adapter)       │        ▼                                                         │
                 │  LinkedInGateway · LinkedInPageParser · ProfileRepository ·      │
                 │  DatasetExporter · RawPageStore · TaskQueue · Throttle           │
                 └────────┬──────────────────────────────────────────────────────────┘
                          │ implemented by (outbound adapters)
     PlaywrightLinkedInGateway · SoupLinkedInParser · JsonProfileRepository ·
     FileDatasetExporter · FileRawPageStore · InMemory/RedisTaskQueue · PoliteThrottle
```

```
src/li_crawler/
  domain/            entities (Profile, Experience, …) and errors – no dependencies
  application/       ports.py (interfaces) + use_cases.py (workflows)
  adapters/
    inbound/cli.py   command line
    outbound/
      playwright_gateway.py   browser: navigation, scrolling, login detection
      parsing/                one module per page type + text rules
      storage/                JSON repository, raw HTML store, CSV/JSON export
      queues.py               in-memory and Redis task queues
      throttle.py             random delay + hourly request cap
  container.py       composition root – the only place that wires adapters to ports
  config.py          settings from environment / .env
```

The rules are that the domain imports nothing from the outer layers and use
cases only see ports. Because of that, the whole pipeline is tested with a fake
gateway and no browser (`tests/test_use_cases.py`). Swapping a technology, for
example MongoDB instead of JSON files or Kafka instead of Redis, means writing
one new adapter and changing `container.py`.

### Pipeline

```
resolve company ─▶ People tab ─▶ queue(CrawlTask) ─▶ for each task:
   (search or URL)   (scroll until N)     │            throttle ─▶ fetch 5 pages ─▶ save raw HTML
                                          │            ─▶ parse ─▶ save profile
                                          └─ retry on PageLoadError (max 2 attempts)
                                             stop everything on login wall / checkpoint
finally ─▶ export profiles.json + CSV tables
```

### Parsing approach

LinkedIn's current markup uses **hashed class names** (`fa4me9 fa4k8o …`) that
change between deployments, so the parser uses no CSS classes at all. It works
from more stable signals:

* page structure: `main > section`, entries split by `<hr>`, grouped roles in `<ul><li>`
* section headings ("Experience", "About") and the hidden "Feed post" heading on activity items
* URL patterns: `/in/<slug>/`, `/company/<slug>/`, `/school/<id>/`
* the shape of the text: date ranges (`Oct 2022 - Present · 4 yrs`), counts
  (`2,115`, `500+`), employment types, "Skills: …" lines

Each profile section is read from its own *details* page
(`/details/experience/`, `/details/education/`, `/details/skills/`,
`/recent-activity/all/`). These pages list every item; the main profile page
shows only some of them.

## Data source and responsible use

* Data comes from the logged-in LinkedIn web UI of the account that runs the
  tool, and only covers what that account can see.
* **No evasion.** The tool runs a normal, visible browser with a manual login.
  It never stores or types credentials, uses no stealth plugins or proxy
  rotation, and never solves CAPTCHAs. A login wall or security checkpoint
  stops the crawl.
* **Polite rate.** It waits 4–9 s (random) between page loads, caps requests
  at 120 per hour, and retries a failed page at most once. One profile is
  5 page loads.
* Scraping is against LinkedIn's User Agreement and can get the account
  restricted. Use small volumes, for this assessment only.
* `data/`, `.browser-profile/` and `.env` are git-ignored because they hold
  personal data and session cookies.

## Configuration

Copy `.env.example` to `.env`. Every setting is optional:

| Variable | Default | Meaning |
|---|---|---|
| `LI_DATA_DIR` | `data` | output directory |
| `LI_BROWSER_PROFILE_DIR` | `.browser-profile` | persistent browser profile (session) |
| `LI_BROWSER_CHANNEL` | `chrome` | `chrome` = installed Chrome, empty = bundled Chromium |
| `LI_HEADLESS` | `false` | hide the browser window |
| `LI_CDP_URL` | – | attach to your own Chrome (see below) |
| `LI_MIN_DELAY_S` / `LI_MAX_DELAY_S` | `4` / `9` | random delay between page loads |
| `LI_MAX_REQUESTS_PER_HOUR` | `120` | hard hourly cap |
| `LI_MAX_ACTIVITIES` | `20` | feed items kept per profile |
| `LI_QUEUE_BACKEND` | `memory` | `memory` or `redis` |
| `LI_REDIS_URL` | `redis://localhost:6379/0` | Redis connection |

**Using your everyday Chrome session instead of a separate profile:** close
Chrome and start it with a debugging port and a separate data dir (Chrome does
not allow remote debugging on the default profile), log in there, then run:

```bash
chrome.exe --remote-debugging-port=9222 --user-data-dir=%TEMP%\li-chrome
python -m li_crawler crawl "Cafe Bazaar" --cdp-url http://localhost:9222
```

**Redis queue:** `docker run -p 6379:6379 redis`, then `--queue redis`.
Tasks are JSON in a Redis list, and a Redis set de-duplicates profiles, so
several workers can share one queue.

## Known limitations

* LinkedIn's UI changes often. When a field comes back empty, check the saved
  HTML in `data/raw/`, fix the parser, and run `reparse`. No re-crawl is needed.
* People in the People tab are ordered by LinkedIn and limited by the viewer's
  network. Profiles shown as "LinkedIn Member" cannot be opened.
* Activity time is relative ("3w") because LinkedIn shows it that way.
* Experience skill lines are often truncated by LinkedIn ("A, B and +11 skills").
  The full list is on the Skills page, which is crawled separately.

## Lessons from the first real run

These were found by checking real crawled data (Cafe Bazaar, 10 profiles) and
fixed with a regression test for each:

* **Scrolling:** pages scroll inside `<main id="workspace">`, not the window,
  so mouse-wheel scrolling loaded nothing. The gateway now scrolls that
  container until its height stops growing.
* **Lazy batches:** each batch loaded on scroll sits in a separate container.
  `split_entries` now collects all of them. Skills went from 10 to the real
  count (up to 43).
* **Social counts** are read from the Reaction / Comment / Repost buttons
  (by `aria-label`), so a post with 0 comments is counted correctly.
* **Reposts:** "X reposted this" spans two lines.
* **Empty sections:** placeholders such as "Education that X adds will
  appear here" are ignored.
