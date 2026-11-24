# Image Finder (v1.4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Each new pick gets up to 4 candidate images (Wikimedia, Steam, Openverse), scored by a local Ollama vision model, plus an optional "Screenshot idea" search link, all shown on the page.

**Architecture:** Haiku's existing curation call returns `image_searches` and `screenshot_idea` per pick. A new `newsbot/images.py` fetches candidates (phase 1), ranks them round-robin across picks with Ollama under a time budget (phase 2), and writes `images` onto each pick dict before `run()` saves. The page renders them with DOM APIs.

**Tech Stack:** Python 3.12, requests, pydantic, Ollama HTTP API (`gemma3:4b`), vanilla JS.

**Spec:** `docs/superpowers/specs/2026-11-17-news-curation-bot-design.md`, section "v1.4 change: image finder".

## Global Constraints

- Sources: `wikimedia`, `steam`, `openverse` only. No keys. Never scrape HTML pages; JSON APIs only.
- Every HTTP request sends `USER_AGENT = "newsbot/1.4 (+https://github.com/AbhishekKr11511/newsbot)"` (constant in `newsbot/fetch.py`). Never a browser UA.
- `image_searches`: 0–3 `{source, query}`; drop unknown source, empty query, or query over 80 chars; truncate to 3.
- `screenshot_idea` link is always `https://www.google.com/search?q=` + `urllib.parse.quote_plus(search)`, never a model-supplied URL. Empty text or search → `null`.
- Candidate: `{url, thumb, page_url, source, credit, license}`; `url`/`thumb`/`page_url` must pass `fetch._http_url` (else candidate dropped; `page_url` may fall back to `url`). Kept images add `score: int | None`.
- Per source per query: up to 5 candidates (Steam: header + first 2 screenshots = max 3).
- Defaults: `keep 4`, `max_scored 8`, `min_score 5`, `budget_s 300`, `ollama_url http://localhost:11434`, `ollama_model gemma3:4b`, Ollama call timeout 60 s.
- At most 2 kept images per source.
- Thumbnails are downloaded into memory only via `default_get` (5 MB / 30 s caps). Never written to disk or committed.
- The image step never fails a run: any exception for a pick → that pick gets `images: []`.
- Page: `textContent` and DOM APIs only; links through `safeHref`; found images never drawn on the canvas.

## Review Focus

1. **Ollama returns junk** (non-JSON content, missing `score`, score 14 or −3): RankError on junk, clamp to 0–10 on range. Task 4 `test_ranker_bad_json_raises`, `test_ranker_clamps_score`.
2. **Ollama not running under launchd** (connection refused on the first call): ranking stops for the run, every pick still gets unranked images. Task 4 `test_ranker_down_gives_unranked_images`.
3. **Budget runs out during phase 1**: picks not yet searched get `images: []`, no exception, the run still saves. Task 4 `test_budget_exhausted_in_phase1`.
4. **Wikimedia `Artist` holds HTML** (`<a href="...">Name</a>`, `<script>`): credit is plain text. Task 3 `test_wikimedia_credit_strips_html`.
5. **Openverse 429** (rate limit): openverse returns nothing for the rest of the run, with no retry storm, and other sources still work. Task 3 `test_openverse_429_disables_source`.

---

### Task 1: User-Agent constant and image settings

**Files:** Modify `newsbot/fetch.py`, `newsbot/config.py`, `settings.yaml`, `tests/test_fetch.py`, `tests/test_config.py`.

**Interfaces:**
- Produces: `fetch.USER_AGENT: str`; `config.ImageSettings` dataclass (`enabled: bool = True`, `sources: list[str] = ["wikimedia","steam","openverse"]`, `ollama_url: str`, `ollama_model: str`, `keep: int = 4`, `max_scored: int = 8`, `min_score: int = 5`, `budget_s: int = 300`); `Settings.images: ImageSettings = field(default_factory=ImageSettings)`; `load_settings` reads an optional `images:` mapping (missing keys → defaults; unknown source names → `ConfigError`).

- [ ] **Step 1: Failing tests.** `test_default_get_sends_user_agent` (monkeypatch `requests.get` with a fake that records `headers` and returns a fake streaming response; assert `headers["User-Agent"] == "newsbot/1.4 (+https://github.com/AbhishekKr11511/newsbot)"`). `test_load_settings_image_defaults` (YAML without `images:` → `keep == 4`, `max_scored == 8`, `min_score == 5`, `budget_s == 300`, `ollama_model == "gemma3:4b"`, `sources == ["wikimedia","steam","openverse"]`). `test_load_settings_image_overrides` (`images: {keep: 2, enabled: false}` → `keep == 2`, `enabled is False`, others default). `test_load_settings_unknown_image_source` (`sources: [pexels]` → `ConfigError`).
- [ ] **Step 2:** `pytest tests/test_fetch.py tests/test_config.py -q`. Expected: the 4 new tests FAIL.
- [ ] **Step 3:** Implement. Add the `images:` block from the spec to `settings.yaml`.
- [ ] **Step 4:** `pytest -q`. Expected: all pass.
- [ ] **Step 5:** Commit `feat: bot User-Agent with repo link; image settings`.

### Task 2: Haiku returns image searches and a screenshot idea

**Files:** Modify `newsbot/curate.py`, `newsbot/run.py`, `prompts/curator.md`; create `newsbot/images.py` (helpers only for now); tests in `tests/test_claude_code.py`, `tests/test_run.py`, new `tests/test_images.py`.

**Interfaces:**
- Consumes: Task 1 `ImageSettings`.
- Produces: pydantic `ImageSearch(source: str, query: str)`, `ScreenshotIdea(text: str, search: str)`. `Pick` gains required `image_searches: list[ImageSearch]` and `screenshot_idea: ScreenshotIdea`. In `images.py`: `clean_searches(raw: list[dict] | None) -> list[dict]` (rules from Global Constraints; strips whitespace) and `screenshot_link(raw: dict | None) -> dict | None` returning `{"text": str, "url": str}`. `curate_all` pick dicts gain `image_searches` (cleaned) and `screenshot_idea` (from `screenshot_link`). A missing key in the raw pick (old fake curators) gives `[]` / `None`.

- [ ] **Step 1: Failing tests.**
  - `test_cli_schema_has_image_fields` (the schema JSON passed to `claude` contains `image_searches` and `screenshot_idea` in `required`).
  - `test_clean_searches`: input `[{"source":"steam","query":" GTA 6 "},{"source":"pexels","query":"x"},{"source":"wikimedia","query":""},{"source":"wikimedia","query":"a"*81},{"source":"openverse","query":"server room"},{"source":"wikimedia","query":"Satya Nadella"},{"source":"steam","query":"Halo"}]` → `[{"source":"steam","query":"GTA 6"},{"source":"openverse","query":"server room"},{"source":"wikimedia","query":"Satya Nadella"}]`.
  - `test_screenshot_link`: `{"text":"Metacritic user score for GTA 6","search":"GTA 6 metacritic user score"}` → url `https://www.google.com/search?q=GTA+6+metacritic+user+score`; empty text or empty search → `None`; `None` → `None`.
  - `test_pick_has_image_fields` (run with a fake curator returning both fields → saved pick has cleaned `image_searches` and the `screenshot_idea` dict).
  - `test_old_fake_pick_without_image_fields` (a fake curator without the fields → `image_searches == []`, `screenshot_idea is None`, no crash).
- [ ] **Step 2:** `pytest -q`. Expected: the new tests FAIL.
- [ ] **Step 3:** Implement. Prompt: add an "## Images" section after "Card text": `image_searches` guidance per source (steam = exact game title; wikimedia = named person, company, product or place; openverse = generic visual when nothing specific fits; 2–6 words; 0–3 searches; never invent names) and `screenshot_idea` (a public page that proves the story, such as a review score page, outage map, store page or official post; `text` one line, `search` a web search phrase; empty strings when nothing fits). Update the fake picks in existing tests to include the fields where needed.
- [ ] **Step 4:** `pytest -q`. Expected: all pass (including `test_real_prompt_file_has_no_leftover_placeholders`).
- [ ] **Step 5:** Commit `feat: Haiku suggests image searches and a screenshot idea`.

### Task 3: Image sources

**Files:** Modify `newsbot/images.py`; create fixtures `tests/fixtures/wikimedia.json`, `steam_search.json`, `steam_appdetails.json`, `openverse.json`; tests in `tests/test_images.py`.

**Interfaces:**
- Consumes: `fetch.default_get`, `fetch._http_url`, `fetch._clean_text` (HTML to text).
- Produces: `SourceUnavailable(Exception)` (raised on HTTP 429); `search_wikimedia(query, http_get, timeout) -> list[dict]`, `search_steam(...)`, `search_openverse(...)`, each returning candidates as in Global Constraints; `SOURCES: dict[str, Callable]` mapping the three names to those functions.

API details (from the spec):
- Wikimedia: `https://commons.wikimedia.org/w/api.php?action=query&format=json&generator=search&gsrsearch=<q> filetype:bitmap&gsrnamespace=6&gsrlimit=5&prop=imageinfo&iiprop=url|extmetadata|mime&iiurlwidth=640`. Order by page `index`. `url = imageinfo[0].url`, `thumb = thumburl`, `page_url = descriptionurl`, `credit = clean(extmetadata.Artist.value)` (or "Wikimedia Commons" if empty), `license = extmetadata.LicenseShortName.value`.
- Steam: `https://store.steampowered.com/api/storesearch/?term=<q>&l=english&cc=US` → first `items[].id`; `https://store.steampowered.com/api/appdetails?appids=<id>` → if `success`, `header_image` + first 2 `screenshots` (`path_full` as url, `path_thumbnail` as thumb; header uses itself for both). `page_url = https://store.steampowered.com/app/<id>/`, `credit = "Official art · Steam"`, `license = "Promotional"`.
- Openverse: `https://api.openverse.org/v1/images/?q=<q>&page_size=5&license_type=commercial,modification`. `url`, `thumb = thumbnail or url`, `page_url = foreign_landing_url`, `credit = f"{title} by {creator} ({source})"`, `license = f"CC {license.upper()} {license_version}"`, but `"CC0"` / `"Public domain"` for `cc0` / `pdm`.
- Queries URL-encoded with `urllib.parse.quote`.

- [ ] **Step 1: Capture fixtures.** Run each URL once with `curl -A "<USER_AGENT>"` (queries: "Satya Nadella", "Grand Theft Auto V" → its app id, "server room"). Trim each to 2–3 results and save. Add one Wikimedia item whose `Artist` is `<a href="//x">Jane <b>Doe</b></a><script>x</script>` and one Openverse item whose `url` is `javascript:alert(1)`.
- [ ] **Step 2: Failing tests.** `test_wikimedia_parses` (first candidate fields match the fixture, `source == "wikimedia"`). `test_wikimedia_credit_strips_html` (credit == `"Jane Doe"`; no `<`, no `script`). `test_steam_two_calls_max_three` (the fake `http_get` routes by URL; 3 candidates; first is the header image). `test_steam_no_match_empty` (empty `items` → `[]`, only one call made). `test_openverse_parses_and_drops_unsafe` (the `javascript:` item is dropped; license string like `"CC BY-SA 2.0"`). `test_openverse_429_disables_source` (fake `http_get` raises `requests.HTTPError` whose `response.status_code == 429` → `SourceUnavailable`).
- [ ] **Step 3:** `pytest tests/test_images.py -q`. Expected: FAIL.
- [ ] **Step 4:** Implement. The source functions parse with `json.loads(http_get(url, timeout))`; 429 → `SourceUnavailable`; other errors propagate (handled by the caller in Task 4).
- [ ] **Step 5:** `pytest -q`. Expected: all pass. Commit `feat: Wikimedia, Steam and Openverse image search`.

### Task 4: Ollama ranker and find_images

**Files:** Modify `newsbot/images.py`, `tests/test_images.py`.

**Interfaces:**
- Consumes: Task 1 `ImageSettings`, Task 3 `SOURCES` / `SourceUnavailable`, Task 2 pick fields.
- Produces:
  - `RankError(Exception)`; `Ranker = Callable[[bytes, str], int]` (image bytes, post text → score 0–10).
  - `ollama_ranker(cfg: ImageSettings, post=requests.post) -> Ranker`: POST `{ollama_url}/api/chat` with `{"model": cfg.ollama_model, "stream": False, "format": {JSON schema: score integer, reason string, both required}, "messages": [{"role": "user", "content": <prompt with the post text>, "images": [base64]}]}`, timeout 60. Parse `resp.json()["message"]["content"]` as JSON. Any HTTP, connection or parse error, or a missing `score` → `RankError`. Score clamped to 0–10.
  - `find_images(picks: list[dict], cfg: ImageSettings, fetch_timeout: int, http_get=default_get, ranker: Ranker | None = None, clock=time.monotonic) -> None`: sets `pick["images"]` on every pick, in place.

Algorithm (from the spec):
- Phase 1, per pick in order: if `clock() - start >= budget_s`, the pick gets `images: []`. Otherwise run each of its `image_searches` whose source is in `cfg.sources` and not disabled. `SourceUnavailable` disables that source for the run; any other exception skips that search. Dedupe by `url` within the pick. Interleave round-robin across searches into `pool`. `to_score = pool[:max_scored]`.
- Phase 2: while the ranker is alive and within budget, step round-robin across picks, taking each pick's next unscored `to_score` item. Thumb download failure → drop that candidate. `RankError` → ranker dead for the run (that candidate stays unscored).
- Final per pick: scored items with `score >= min_score`, by score descending (stable), then unattempted items in pool order with `score: None`. Then apply max 2 per source, truncated to `keep`. Scored items below `min_score` are never shown.
- Any exception while handling a pick → that pick's `images = []`.

- [ ] **Step 1: Failing tests** (fake `http_get` returns fixture JSON or `b"img"` for thumbs; fake ranker returns scores from a dict keyed by the thumb bytes or call order; fake clock is a list-driven counter).
  - `test_ranker_parses_score` (fake `post` returns `{"message":{"content":"{\"score\":7,\"reason\":\"fits\"}"}}` → 7; the sent JSON has `images` base64 and `model == "gemma3:4b"`).
  - `test_ranker_clamps_score` (14 → 10, −3 → 0).
  - `test_ranker_bad_json_raises` (content `"nope"` → RankError; a connection error → RankError).
  - `test_find_images_ranks_and_keeps_top` (scores 9, 3, 7, 6 → kept order 9, 7, 6; the 3 is dropped).
  - `test_max_two_per_source` (5 Steam candidates all scoring 9 plus 1 Wikimedia scoring 6 → 2 Steam, 1 Wikimedia).
  - `test_max_scored_round_robin` (two searches with 5 each, `max_scored=4` → ranker called on items 1a, 1b, 2a, 2b in that interleaved order).
  - `test_ranker_down_gives_unranked_images` (ranker raises RankError on the first call → called once only; every pick gets up to `keep` images with `score is None`).
  - `test_budget_exhausted_in_phase1` (the clock passes the budget after the first pick's searches → pick 1 gets unranked images, pick 2 gets `[]`).
  - `test_rank_round_robin_across_picks` (the budget allows 2 ranker calls → one per pick, not two for pick 1).
  - `test_disabled_source_skipped` (`SourceUnavailable` on the first openverse search → later picks' openverse searches don't call `http_get`).
  - `test_search_exception_isolated` (one search raises `ValueError` → other searches still give candidates).
- [ ] **Step 2:** `pytest tests/test_images.py -q`. Expected: the new tests FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** `pytest -q`. Expected: all pass. Commit `feat: rank found images with a local Ollama vision model`.

### Task 5: Wire into the run, CLI and dry-run summary

**Files:** Modify `newsbot/run.py`, `newsbot/__main__.py`, `tests/test_run.py`, `tests/test_main.py`.

**Interfaces:**
- Consumes: Task 4 `find_images`, `ollama_ranker`.
- Produces: `run(..., image_finder: Callable[[list[dict]], None] | None = None)`. After `curate_all`, it collects every pick across categories and calls `image_finder(picks)` inside `try/except Exception` (log a warning and continue), before the summary and saving. `__main__` gains `--no-images`. When `settings.images.enabled` and not `--no-images`, it passes `functools.partial(find_images, cfg=settings.images, fetch_timeout=settings.fetch_timeout_s, ranker=ollama_ranker(settings.images))`.
- `_print_summary`, when a pick has `images`: `    images: 3 ranked (wikimedia 2, steam 1)`, or `unranked`, or `images: none`. When it has `screenshot_idea`: `    screenshot: <text>`.

- [ ] **Step 1: Failing tests.** `test_image_finder_called_with_all_picks` (a fake finder records the picks and sets `images`; the saved `picks.json` contains them). `test_image_finder_crash_does_not_fail_run` (the finder raises → exit code 0 and picks are saved). `test_summary_prints_images_line`. `test_main_no_images_flag` (`--no-images` → `run` gets `image_finder=None`; patch `run` as the existing main tests do).
- [ ] **Step 2:** `pytest -q`. Expected: the new tests FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** `pytest -q`. Expected: all pass. Commit `feat: find images during each run (--no-images to skip)`.

### Task 6: Page shows found images and screenshot idea

**Files:** Modify `site/app.js`, `site/style.css`, `scripts/sample_data.py`.

- `foundImages(pick)`: if `pick.images` has items, a `div.found` with heading "Found images" (plus " · unranked" if any `score === null`) and a grid of figures. Each figure: `<img loading="lazy" referrerpolicy="no-referrer" alt=credit>` from `safeHref(thumb)`, a figcaption with `credit · license` (textContent), and links "Open full size" (`url`) and "Source" (`page_url`), both `target=_blank rel="noopener noreferrer"`. If `pick.screenshot_idea`: a `p.shot` with "Screenshot idea: " + text and a "Search" link. Inserted in `cardBlock` after the hero and before the canvas. Grid: 2 columns on phones, 4 at ≥ 700 px, square thumbnails with `object-fit: cover`.
- Sample data: two picks with 4 and 2 images (one set with `score: null`), one with a `screenshot_idea`, and one old pick without the fields.

- [ ] **Step 1:** `python scripts/sample_data.py site/data && python -m http.server -d site 8000`, then screenshot with headless Chrome at desktop width and at 375 px via an iframe. Check: thumbnails render in the grid, credits show, the "unranked" note appears on the null-score set, the old pick renders without errors, Download card still produces a PNG, and there's no `innerHTML` with data (`grep -n innerHTML site/app.js` shows no new hits).
- [ ] **Step 2:** `pytest -q`. Expected: all pass. Remove the sample data (`git checkout site/data` / `git status` clean for `site/data`). Commit `feat: found images and screenshot idea on the page`.

### Task 7: Live dry run, docs, review

- [ ] **Step 1:** With the Ollama app running: `python -m newsbot --dry-run` in this (Documents) copy. Expected: drafts print with `images:` lines, mostly ranked, and the run finishes in under ~8 minutes. Write `site/data` once from a non-dry local run only if needed for a page check, then restore it. Show the owner a few picks with their images (serve the page locally).
- [ ] **Step 2:** Docs. README (image finder; `ollama pull gemma3:4b`; Ollama app must be running for ranking; licences and credits are the owner's responsibility). CLAUDE.md (layout line for `images.py`; the User-Agent rule). PROGRESS.md (v1.4 checklist, log line, next steps: X posting button deferred). Commit `docs: image finder`.
- [ ] **Step 3:** Owner approval, then go live. Before pushing, set `DRY_RUN=true` in `~/code/newsbot/.env` if the owner wants a scheduled dry run first; otherwise push and the next scheduled run uses images. Push only with the owner's OK.
