# News Curation Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A GitHub Actions bot that every 4 hours fetches RSS headlines, has Claude Sonnet pick 0–3 stories per category and draft X posts, and publishes everything to a static GitHub Pages site.

**Architecture:** A small Python package (`newsbot`) with one module per stage — config → fetch → curate → checks → store — orchestrated by `run.py`. State is JSON in `site/data/`, committed back by the workflow. A fixed static page (`site/index.html` + `app.js`) renders the JSON.

**Tech Stack:** Python 3.12, `feedparser`, `requests`, `PyYAML`, `anthropic` (Python SDK), `pydantic`, `pytest`; vanilla HTML/CSS/JS; GitHub Actions + Pages.

**Spec:** `docs/superpowers/specs/2026-11-17-news-curation-bot-design.md`

## Global Constraints

- Model: `claude-sonnet-5-5` (owner named Sonnet). Set `output_config` effort explicitly to `"medium"` (configurable in `settings.yaml`). No `temperature`/`top_p`, no `budget_tokens`, no assistant prefill, no forced `tool_choice`.
- Structured output via `client.messages.parse(..., output_format=CurationResult)` (Pydantic). Always check `response.stop_reason == "refusal"` before reading `parsed_output`.
- Refusal fallback: send `betas=["server-side-fallback-2026-07-01"]`, `fallbacks="default"` via `client.beta.messages.parse`. If the installed SDK's beta `parse` rejects these, use plain `client.messages.parse` and treat a refusal as a category failure. Note which one was used in the README.
- `ANTHROPIC_API_KEY` comes from env only (GitHub Secret / local `.env`). Never committed.
- Article window: 24 hours from run start. Per category: 0–3 picks (`max_picks: 3`). Per-source cap sent to Claude: 15 newest. Picks history kept 30 days.
- Posts: one to two sentences, no hashtags, no links, max 280 chars. Banned-word seed list: `game-changer`, `game changer`, `masterstroke`, `master-stroke`, `revolutionary`.
- All times stored as UTC ISO 8601 (`2026-11-18T14:02:00Z`). The page shows them in the viewer's local timezone.
- A failing feed or a failing category never stops the run.
- `DRY_RUN` true → print to stdout, write nothing.
- The page must render feed text with `textContent` only (never `innerHTML` with feed data).

## Review Focus

1. **Feed text containing HTML or `<script>`** — the page must show it as plain text. Pinned by Task 7 step "XSS check".
2. **First run with no `site/data/*.json` files** — the bot creates them; the page shows an empty state rather than erroring. Pinned by Task 3 `test_load_missing_files_returns_empty` and Task 7 empty-state check.
3. **Entries with no timezone, or a publish date in the future** — naive dates are treated as UTC; dates more than 1h in the future are clamped to run time. Pinned by Task 2 `test_naive_date_is_utc` and `test_future_date_clamped`.
4. **A category with zero candidates, or every feed failing** — no Claude call for that category, status `no_candidates`, run succeeds, page shows "Nothing new". Pinned by Task 6 `test_empty_category_skips_claude`.
5. **Claude returns bad output** (unknown `article_id`, duplicates, more than 3 picks, refusal, API error) — bad picks are dropped, a refusal or API error marks the category `curation_failed`, and the other categories continue. Pinned by Task 4 `test_validate_picks_*` and Task 5 `test_refusal_raises_curation_error`.

---

## File Structure

```
newsbot/
  __init__.py
  __main__.py      CLI entry: `python -m newsbot [--dry-run]`
  config.py        dataclasses + loaders for sources.yaml, topics.yaml, settings.yaml
  fetch.py         Article dataclass, URL canonicalization, feed parsing, fetch_all
  store.py         read/write/merge/prune site/data/*.json
  checks.py        post flags + pick validation
  curate.py        candidate selection, prompt building, Claude call
  run.py           orchestrates one run, returns exit code
prompts/curator.md     system prompt template (owner-editable)
sources.yaml           feeds (owner-editable)
topics.yaml            categories (owner-editable)
settings.yaml          model, effort, caps, retention, banned words
site/index.html, site/app.js, site/style.css
site/data/.gitkeep
.github/workflows/run.yml
tests/fixtures/*.xml   sample RSS/Atom/YouTube feeds
tests/test_*.py
requirements.txt, .gitignore, .env.example, README.md
```

---

### Task 1: Project scaffold and config loading

**Files:**
- Create: `requirements.txt`, `.gitignore`, `.env.example`, `newsbot/__init__.py`, `newsbot/config.py`, `topics.yaml`, `settings.yaml`, `sources.yaml` (2–3 placeholder entries for now; Task 8 fills it in), `prompts/curator.md` (placeholder; Task 5 writes it)
- Test: `tests/test_config.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) Source(name: str, url: str, category: str, kind: str = "rss", strip_title_suffix: str | None = None)`
  - `@dataclass(frozen=True) Category(id: str, name: str, max_picks: int, covers: str, skip: str)`
  - `@dataclass(frozen=True) Settings(model: str, effort: str, per_source_cap: int, window_hours: int, picks_retention_days: int, max_post_chars: int, banned_words: list[str], fetch_timeout_s: int)`
  - `class ConfigError(Exception)`
  - `load_categories(path: Path) -> list[Category]`
  - `load_sources(path: Path, categories: list[Category]) -> list[Source]` raises `ConfigError` if a source names an unknown category or a required field is missing
  - `load_settings(path: Path) -> Settings`

- [ ] **Step 1:** `git init`, create a venv, write `requirements.txt` (`feedparser`, `requests`, `PyYAML`, `anthropic`, `pydantic`, `python-dotenv`, `pytest`), `.gitignore` (`.venv/`, `.env`, `__pycache__/`), `.env.example` (`ANTHROPIC_API_KEY=`), then run `pip install -r requirements.txt`.
- [ ] **Step 2:** Write `topics.yaml` with the spec's five categories (`ai-bigtech`, `semis`, `gaming`, `india-tech`, `world-markets`), copying the names and `covers`/`skip` text from the spec's Categories table, with `max_picks: 3` on each. Write `settings.yaml` using the Global Constraints values (`effort: medium`, `per_source_cap: 15`, `window_hours: 24`, `picks_retention_days: 30`, `max_post_chars: 280`, `fetch_timeout_s: 15`, plus the banned-word list).
- [ ] **Step 3: Write failing tests**

```python
def test_load_categories_reads_five(tmp_path): ...  # loads repo topics.yaml; len == 5; ids in expected order; all max_picks == 3
def test_unknown_category_raises(tmp_path):
    # sources.yaml with category: "nope" -> pytest.raises(ConfigError, match="nope")
def test_missing_url_raises(tmp_path): ...  # ConfigError
def test_source_defaults(tmp_path): ...     # kind == "rss", strip_title_suffix is None
def test_load_settings():                   # repo settings.yaml; model == "claude-sonnet-5-5"; "masterstroke" in banned_words
```

- [ ] **Step 4:** Run `pytest tests/test_config.py -v`. Expected: FAIL (module missing).
- [ ] **Step 5:** Implement `newsbot/config.py`.
- [ ] **Step 6:** Run `pytest tests/test_config.py -v`. Expected: PASS.
- [ ] **Step 7:** Commit `feat: project scaffold and config loading`. Include the spec and plan docs in this first commit.

---

### Task 2: Fetch and normalize feeds

**Files:**
- Create: `newsbot/fetch.py`, `tests/fixtures/rss_basic.xml`, `tests/fixtures/google_news.xml`, `tests/fixtures/youtube.xml`, `tests/fixtures/bad_dates.xml`
- Test: `tests/test_fetch.py`

**Interfaces:**
- Consumes: `Source`, `Settings` (Task 1)
- Produces:
  - `@dataclass Article(id: str, title: str, url: str, source: str, category: str, published_at: datetime, summary: str)`, where `published_at` is tz-aware UTC
  - `Article.to_dict() -> dict` (with `published_at` as `...Z` ISO) and `Article.from_dict(d: dict) -> Article`
  - `canonicalize_url(url: str) -> str`: lowercases the host, drops the fragment, and removes `utm_*`, `fbclid`, `gclid`, `ocid`, `cmpid`, `ref` query params
  - `article_id(url: str) -> str`: the first 16 hex chars of sha1(canonical url)
  - `parse_feed(content: bytes, source: Source, now: datetime, window_hours: int) -> list[Article]`
  - `fetch_all(sources: list[Source], now: datetime, settings: Settings, http_get: Callable[[str, int], bytes] = default_get) -> tuple[list[Article], list[str]]`, which returns the articles (deduped by `id`, newest first) and a list of error strings, one per failed feed

Rules in `parse_feed`: get the date from `published_parsed`, falling back to `updated_parsed`, and skip the entry if neither exists. Treat naive dates as UTC. Clamp dates more than 1h ahead of `now` to `now`. Drop anything older than `now - window_hours`. Strip HTML from the summary, collapse whitespace, and truncate to 300 chars. Strip `source.strip_title_suffix` from the end of the title. `default_get` uses `requests.get(url, timeout=…, headers={"User-Agent": "newsbot/1.0"})`, calls `raise_for_status()`, and returns `.content`.

- [ ] **Step 1:** Create the fixtures. Each one is a small hand-written feed of 3–5 items with dates relative to a fixed `NOW = datetime(2026, 11, 18, 12, 0, tzinfo=UTC)`. `google_news.xml` has titles ending in " - Reuters". `youtube.xml` is in Atom format. `bad_dates.xml` has one item with no date, one with a naive date, one dated 1 day in the future, and one dated 30 hours old.
- [ ] **Step 2: Write failing tests**

```python
def test_canonicalize_strips_tracking():
    assert canonicalize_url("https://Example.com/a?utm_source=x&id=5#top") == "https://example.com/a?id=5"
def test_article_id_stable_across_tracking_params(): ...  # ids equal for URLs differing only by utm_*
def test_parse_basic_rss(): ...            # count, fields populated, published_at tz == UTC
def test_strip_title_suffix(): ...         # google_news.xml with strip_title_suffix=" - Reuters" -> no title endswith " - Reuters"
def test_parse_youtube_atom(): ...         # titles + urls present
def test_entry_without_date_skipped(): ...
def test_naive_date_is_utc(): ...
def test_future_date_clamped(): ...        # published_at == NOW
def test_older_than_window_dropped(): ...  # 30h-old item absent
def test_fetch_all_survives_failing_feed():
    # http_get raises for source A, returns rss_basic for source B
    # -> articles from B only, errors has 1 entry naming A
def test_fetch_all_dedupes_by_id(): ...    # same URL in two feeds -> one article
```

- [ ] **Step 3:** Run `pytest tests/test_fetch.py -v`. Expected: FAIL.
- [ ] **Step 4:** Implement `newsbot/fetch.py`.
- [ ] **Step 5:** Run `pytest tests/test_fetch.py -v`. Expected: PASS.
- [ ] **Step 6:** Commit `feat: feed fetching and normalization`.

---

### Task 3: JSON store

**Files:**
- Create: `newsbot/store.py`, `site/data/.gitkeep`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: `Article` (Task 2), `Category` (Task 1)
- Produces:
  - `load_articles(path: Path) -> list[Article]` returns `[]` if the file is missing
  - `merge_articles(existing: list[Article], new: list[Article], now: datetime, window_hours: int) -> list[Article]`: unions by `id` (new wins), drops anything outside the window, and sorts by `published_at` desc
  - `save_articles(path: Path, articles: list[Article]) -> None`
  - `load_runs(path: Path) -> list[dict]` returns `[]` if the file is missing
  - `append_run(runs: list[dict], run: dict, now: datetime, retention_days: int) -> list[dict]`, which prunes runs older than the retention period
  - `recent_picks(runs: list[dict], now: datetime, hours: int = 24) -> list[dict]`: flat list of pick dicts from runs within `hours`, each with `category` added
  - `save_runs(path, runs)`, and `save_meta(path: Path, categories: list[Category], last_run_at: datetime, feed_errors: list[str]) -> None`

Run dict shape (written by Task 6):
```json
{"run_at": "2026-11-18T12:00:00Z",
 "categories": {"gaming": {"status": "ok|no_candidates|curation_failed",
                           "error": null,
                           "picks": [{"article_id": "...", "title": "...", "url": "...", "source": "...",
                                      "published_at": "...Z", "post": "...", "reason": "...", "flags": []}]}}}
```
Meta shape: `{"last_run_at": "...Z", "categories": [{"id": "...", "name": "..."}], "feed_errors": ["..."]}`.

Writes are atomic: write to `*.tmp`, then `os.replace`. Output JSON uses `indent=1` and `ensure_ascii=False`.

- [ ] **Step 1: Write failing tests**

```python
def test_load_missing_files_returns_empty(tmp_path): ...       # load_articles and load_runs -> []
def test_merge_dedupes_and_prunes(): ...                       # old (25h) dropped, duplicate id kept once, sorted desc
def test_articles_roundtrip(tmp_path): ...                     # save then load equals input
def test_append_run_prunes_after_retention(): ...              # run 31 days old removed, 29 days kept
def test_recent_picks_only_last_24h(): ...                     # picks from a 30h-old run excluded; category key present
def test_save_meta_shape(tmp_path): ...                        # keys last_run_at, categories (ordered), feed_errors
```

- [ ] **Step 2:** Run `pytest tests/test_store.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement `newsbot/store.py`.
- [ ] **Step 4:** Run `pytest tests/test_store.py -v`. Expected: PASS.
- [ ] **Step 5:** Commit `feat: JSON data store`.

---

### Task 4: Post checks and pick validation

**Files:**
- Create: `newsbot/checks.py`
- Test: `tests/test_checks.py`

**Interfaces:**
- Consumes: `Settings` (Task 1)
- Produces:
  - `check_post(text: str, settings: Settings) -> list[str]`. Possible flags: `"too_long"` (over `max_post_chars`), `"hashtag"` (`#\w`), `"link"` (`http://`, `https://`, or `www.`), `"empty"`, and `"hype:<word>"` for each banned word (case-insensitive substring match).
  - `validate_picks(picks: list[dict], candidate_ids: set[str], already_picked_ids: set[str], max_picks: int) -> list[dict]`. It drops picks with unknown ids, picks whose id is in `already_picked_ids`, and duplicate ids, keeps input order, and truncates to `max_picks`. Each pick dict has `article_id`, `post` and `reason`.

- [ ] **Step 1: Write failing tests**

```python
def test_clean_post_has_no_flags(): ...
def test_flags_too_long(): ...                    # 281 chars -> "too_long"; 280 -> no flag
def test_flags_hashtag_and_link(): ...
def test_flags_hype_case_insensitive(): ...       # "A Game-Changer for chips" -> "hype:game-changer"
def test_validate_picks_drops_unknown_ids(): ...
def test_validate_picks_drops_duplicates_and_already_picked(): ...
def test_validate_picks_truncates_to_max(): ...   # 5 valid picks, max 3 -> first 3
```

- [ ] **Step 2:** Run `pytest tests/test_checks.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement `newsbot/checks.py`.
- [ ] **Step 4:** Run `pytest tests/test_checks.py -v`. Expected: PASS.
- [ ] **Step 5:** Commit `feat: post checks and pick validation`.

---

### Task 5: Curation with Claude

**Files:**
- Create: `newsbot/curate.py`, `prompts/curator.md` (real content)
- Test: `tests/test_curate.py`

**Interfaces:**
- Consumes: `Article` (Task 2), `Category`, `Settings` (Task 1)
- Produces:
  - `class Pick(BaseModel): article_id: str; post: str; reason: str`
  - `class CurationResult(BaseModel): picks: list[Pick]`
  - `class CurationError(Exception)`
  - `select_candidates(articles: list[Article], category_id: str, per_source_cap: int) -> list[Article]`: the newest `per_source_cap` per source within the category, sorted newest first overall
  - `build_system_prompt(template: str, category: Category) -> str`: fills `{category_name}`, `{covers}`, `{skip}`, and `{max_picks}`
  - `build_user_message(candidates: list[Article], previous_picks: list[dict], now: datetime) -> str`
  - `curate_category(client, settings: Settings, system_prompt: str, user_message: str) -> list[dict]`. It returns `[p.model_dump() for p in parsed.picks]` and raises `CurationError` on an API error, `stop_reason == "refusal"`, `stop_reason == "max_tokens"`, or a missing/invalid `parsed_output`.

`prompts/curator.md` content: the spec's global rules, verbatim in substance. That means: pick 0 to `{max_picks}`, never pad; the skip list; on duplicate coverage, prefer the most specific version; the voice rules; no hashtags; no links; one to two sentences; lead with the number or quote; never repeat an event listed under "Already covered". Then a `## This category` section with the four placeholders. End with a commented-out `## Example posts in my voice` section so the owner can add examples later.

`build_user_message` format: the current UTC time, then an `Already covered (last 24h):` block (one line per previous pick, `- [category] title — post`, or `none`), then `Candidates:`, with one block per article:
```
id: <id>
source: <source> | published: <ISO> (<N>h ago)
title: <title>
summary: <summary>
```

Call: `client.beta.messages.parse(model=settings.model, max_tokens=4000, system=system_prompt, messages=[{"role": "user", "content": user_message}], output_format=CurationResult, output_config={"effort": settings.effort}, betas=["server-side-fallback-2026-07-01"], fallbacks="default")`. Fall back as described in Global Constraints if the SDK rejects this. Catch `anthropic.APIError` and re-raise as `CurationError`. The SDK already retries 429/5xx.

- [ ] **Step 1: Write failing tests** (with a fake client object whose `.beta.messages.parse` returns a stub `SimpleNamespace(stop_reason=..., parsed_output=...)`)

```python
def test_select_candidates_caps_per_source(): ...       # 20 from IGN + 3 from Kotaku, cap 15 -> 18, only that category
def test_system_prompt_fills_placeholders(): ...        # no "{" left; contains category name and "3"
def test_user_message_includes_ids_and_covered(): ...   # every candidate id present; previous pick title present; "none" when empty
def test_curate_returns_picks(): ...                    # stub parsed_output with 2 picks -> list of 2 dicts
def test_curate_passes_model_and_effort(): ...          # fake records kwargs: model == "claude-sonnet-5-5", output_config effort == "medium"
def test_refusal_raises_curation_error(): ...           # stop_reason="refusal" -> CurationError
def test_max_tokens_raises_curation_error(): ...
def test_api_error_raises_curation_error(): ...         # fake raises anthropic.APIConnectionError(request=httpx.Request("POST", "https://x"))
```

- [ ] **Step 2:** Run `pytest tests/test_curate.py -v`. Expected: FAIL.
- [ ] **Step 3:** Write `prompts/curator.md`, then implement `newsbot/curate.py`.
- [ ] **Step 4:** Run `pytest tests/test_curate.py -v`. Expected: PASS.
- [ ] **Step 5:** Commit `feat: Claude curation per category`.

---

### Task 6: Run orchestration and CLI

**Files:**
- Create: `newsbot/run.py`, `newsbot/__main__.py`
- Test: `tests/test_run.py`

**Interfaces:**
- Consumes: everything from Tasks 1–5
- Produces:
  - `@dataclass Paths(root: Path)` with properties `topics`, `sources`, `settings`, `prompt`, `articles` (`site/data/articles.json`), `picks` (`site/data/picks.json`), and `meta` (`site/data/meta.json`)
  - `run(paths: Paths, now: datetime, dry_run: bool, client, http_get=default_get, out=sys.stdout) -> int`, which returns exit code `0`, or `1` if any category is `curation_failed`
  - `__main__`: loads `.env` via python-dotenv if present, then reads `--dry-run` or the env var `DRY_RUN` (`"true"`/`"1"`, case-insensitive). It builds `anthropic.Anthropic()`, calls `run(Paths(Path.cwd()), datetime.now(UTC), …)`, and passes the result to `sys.exit`.

Flow of `run`:
1. Load the config.
2. Run `fetch_all`.
3. Merge with existing articles. This merged list is the candidate pool, so articles from previous runs that are still within 24h stay eligible.
4. Call `recent_picks` on the existing runs.
5. For each category in `topics.yaml` order:
   - Select candidates and exclude ids in `already_picked_ids`. That set is the ids from recent picks plus the ids picked earlier in this run.
   - If no candidates are left, the status is `no_candidates`.
   - Otherwise, build the prompts. `previous_picks` is the recent picks plus this run's picks so far. Call `curate_category`, then `validate_picks`, then attach `check_post` flags and the article fields to each pick. The status is `ok`.
   - On `CurationError`, set the status to `curation_failed` with the error string and continue.
6. Print a summary to `out`. For each category, show a header line, then each pick's post, flags and source. Then print the feed error count.
7. If `dry_run` is set, return here, before any write. Otherwise, save articles, append and save runs, and save meta.

- [ ] **Step 1: Write failing tests** (with a fake `http_get` serving the Task 2 fixtures and a fake client returning canned picks, all under `tmp_path` copies of the config files)

```python
def test_dry_run_writes_nothing(tmp_path): ...            # site/data/*.json absent afterwards; stdout contains a drafted post
def test_live_run_writes_three_files(tmp_path): ...       # articles/picks/meta exist; picks.json has 1 run with all 5 category keys
def test_empty_category_skips_claude(tmp_path): ...       # no sources for "semis" -> status "no_candidates"; fake client never called with semis prompt
def test_failed_category_does_not_stop_others(tmp_path):  # fake raises for gaming only -> gaming curation_failed, others ok, exit code 1
def test_second_run_excludes_previous_picks(tmp_path): ... # run twice; ids picked in run 1 not in run 2's candidate message
def test_flags_attached(tmp_path): ...                    # canned post with "#AI" -> pick flags contains "hashtag"
```

- [ ] **Step 2:** Run `pytest tests/test_run.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement `newsbot/run.py` and `newsbot/__main__.py`.
- [ ] **Step 4:** Run `pytest -v` (full suite). Expected: all PASS.
- [ ] **Step 5:** Commit `feat: run orchestration and CLI`.

---

### Task 7: Static page

**Files:**
- Create: `site/index.html`, `site/app.js`, `site/style.css`, `tests/fixtures/site_data/{articles,picks,meta}.json` (sample data, including one title `"<img src=x onerror=alert(1)> Nvidia"` and a `curation_failed` category)

**Interfaces:**
- Consumes: the JSON shapes from Task 3.

Behaviour:
- Load `data/meta.json`, `data/picks.json` and `data/articles.json` with `?t=<Date.now()>` to bust the cache.
- Header: "News Bot", plus the last run time in local time.
- Tabs: "All", then one per `meta.categories`. The selected tab is kept in the URL hash (`#gaming`).
- Picks section: runs from the last 24h, newest first. For each run, a heading ("14:02 run"). Each pick shows the post text, a char count (`112/280`), and a Copy button that calls `navigator.clipboard.writeText(post)` and briefly shows "Copied". It also shows flags as warning badges, the reason in muted text, and source · local date/time · "Nh ago" with a link to the article (`target="_blank" rel="noopener"`). "All" labels each pick with its category name. A `curation_failed` category shows "Curation failed this run"; `no_candidates` shows nothing.
- Articles section: articles for the tab, newest first. Each row shows the local time (`18 Nov, 13:55`), source, title link and "Nh ago".
- Empty state when there are no data files or no articles: "No data yet. The first run hasn't published."
- All feed-derived strings go through `textContent`. Build elements with `document.createElement`.
- Mobile-first, readable at 375px wide with a 16px side gutter, system font stack, light/dark via `prefers-color-scheme`.

- [ ] **Step 1:** Copy the sample data into `site/data/` temporarily. Run `python -m http.server -d site 8000` and open `http://localhost:8000`.
- [ ] **Step 2:** Implement `index.html`, `app.js` and `style.css`.
- [ ] **Step 3: Manual check:** tabs switch, and the hash persists across reload. Copy puts the exact post text on the clipboard. Times show in local time. The failed category shows its message. The layout works at 375px wide.
- [ ] **Step 4: XSS check:** the `<img onerror>` title shows as literal text, and no alert fires. `grep -n innerHTML site/app.js` returns nothing that involves data.
- [ ] **Step 5: Empty-state check:** remove `site/data/*.json`, reload, and the empty-state message shows with no console errors.
- [ ] **Step 6:** Restore `site/data/` to contain only `.gitkeep`. Commit `feat: static page`.

---

### Task 8: Real sources and a live smoke run

**Files:**
- Modify: `sources.yaml`
- Create: `scripts/check_feeds.py`

**Interfaces:**
- Consumes: `load_sources`, `fetch_all` (Tasks 1–2)
- Produces: `python scripts/check_feeds.py`, which prints one line per source (`OK  <name>  <n> items in 24h, newest <time>` or `FAIL <name>  <error>`) and exits 1 if any fail.

- [ ] **Step 1:** Fill in `sources.yaml` with every source from the spec's sources table, each with its category. Google News search URLs use the form `https://news.google.com/rss/search?q=<query>+when:1d&hl=en-US&gl=US&ceid=US:en` with `strip_title_suffix: " - Reuters"` or `" - AP News"`. Use the official RSS feeds for BBC, TechCrunch, the gaming outlets, Inc42, ET Tech and Moneycontrol. For Skill Up, use the YouTube channel feed (`kind: youtube`; look up the `channel_id`). Add one chip-focused feed under `semis` if a reputable one with working RSS exists. Reuters Media goes under `ai-bigtech`.
- [ ] **Step 2:** Write `scripts/check_feeds.py` and run it. Fix or replace any `FAIL` URL. Expected: all OK, or any remaining failure noted in the README with the reason.
- [ ] **Step 3:** Run `python -m newsbot --dry-run` with a real `ANTHROPIC_API_KEY` in `.env`. Expected: picks for most categories, each post 1–2 sentences with no hashtags or links, and nothing written to `site/data/`. Paste the output into the task report for the owner to review.
- [ ] **Step 4:** Commit `feat: real source list and feed checker`.

---

### Task 9: GitHub Actions workflow and README

**Files:**
- Create: `.github/workflows/run.yml`, `README.md`

`run.yml`:
- Triggers: `schedule: - cron: "0 */4 * * *"` and `workflow_dispatch`.
- Permissions: `contents: write`, `pages: write`, `id-token: write`.
- `concurrency: {group: newsbot, cancel-in-progress: false}`.
- Job steps:
  1. `actions/checkout@v4`
  2. `actions/setup-python@v5` (3.12, pip cache)
  3. `pip install -r requirements.txt`
  4. Run step (`id: bot`, `continue-on-error: true`): `python -m newsbot`, with env `ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}` and `DRY_RUN: ${{ vars.DRY_RUN || 'true' }}`
  5. If not a dry run: configure the git user as `github-actions[bot]`, run `git add site/data`, then `git diff --cached --quiet || git commit -m "data: run $(date -u +%FT%TZ)"`, then `git push`
  6. If not a dry run: `actions/upload-pages-artifact@v3` (path `site`) and `actions/deploy-pages@v4` (environment `github-pages`)
  7. Final step: `if: steps.bot.outcome == 'failure'`, run `exit 1`, so GitHub emails the owner

`README.md` (written for the owner):
- What the bot does.
- One-time setup:
  1. Create a public repo and push the code.
  2. Settings → Secrets → Actions: add `ANTHROPIC_API_KEY`.
  3. Settings → Variables: add `DRY_RUN=true`.
  4. Settings → Pages: set the source to "GitHub Actions".
  5. Actions tab → enable workflows → "Run workflow".
  6. Read the drafts in the run log, then set `DRY_RUN=false`.
- How to add a source (`sources.yaml`), a topic or category (`topics.yaml`), and how to tune the voice (`prompts/curator.md`).
- How to run locally: `.env`, `python -m newsbot --dry-run`, `python scripts/check_feeds.py`, and `python -m http.server -d site`.
- Expected cost.

- [ ] **Step 1:** Write `run.yml`. Validate it with `python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/run.yml'))"`, and with `actionlint` if it's installed.
- [ ] **Step 2:** Write `README.md`.
- [ ] **Step 3:** Run `pytest -v`. Expected: all PASS.
- [ ] **Step 4:** Commit `feat: GitHub Actions workflow and README`.
- [ ] **Step 5 (with the owner):** Create the GitHub repo, push, add the secret and variable, enable Pages, and trigger "Run workflow". Expected: a green run with drafts in the log and no data commit. Then set `DRY_RUN=false` and trigger again. Expected: a data commit and the site live at `https://<user>.github.io/<repo>/`.
