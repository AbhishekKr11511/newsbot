# News Curation Bot — Design (v1)

Date: 2026-11-17 (updated 2026-11-18)

## Intent

A scheduled bot that pulls recent headlines from a fixed, growing set of credible sources, has Claude pick the few stories worth talking about, and drafts an X post for each in the owner's voice. In v1 the owner reads the drafts on a simple web page and posts them to X by hand. The point is engagement on X built on signal, not volume: a small number of sharp, specific posts about AI, chips, big-tech moves, the gaming industry, Indian tech/startups (including jobs and economic impact), and real market shifts.

Coverage is organised into **categories** so topics stay balanced: each category is curated on its own, so a huge AI news day can't crowd out gaming or Indian tech.

Later versions will post automatically through the X API. v1 is built so that step is an add-on, not a rewrite.

## Goals

- Every 4 hours, fetch headlines from all configured sources.
- Keep only items published within 24 hours of the run time.
- For **each category**, Claude (Sonnet) picks **0–3** stories and writes one post per pick. Strong categories fill up; quiet ones stay empty. No filler.
- A static web page with a tab per category (plus "All") shows every fetched article from the last 24 hours, newest first, each with a date/time tag and source, with **Claude's picks and their drafts on top**, each draft with a Copy button.
- Adding a source, a topic, or a whole new category = editing config (`sources.yaml` / `topics.yaml`), no code change.
- Runs entirely on GitHub (Actions + Pages); the owner's Mac can be off.

## Non-goals (v1)

- Posting to X (manual in v1; X API later).
- User accounts or login.
- A database. State lives in JSON files committed to the repo.
- A `posted_urls.json` / "mark posted" tracking. The owner copies drafts and posts manually.
- A VPS or always-on server.
- Analytics on post performance.

## Anti-goals (failure even if it "works")

- Hype language ("game-changer", "masterstroke", "revolutionary", etc.).
- More than 3 picks in a category in one run, or filler picks to reach a number.
- Picking stories older than 24 hours.
- Re-picking the same event in later runs (runs are 4h apart but the window is 24h, so without memory the same story would be eligible ~6 times), or the same event in two categories in the same run.
- One dead feed, or one failed category, breaking the whole run.
- Picking gossip, sports, listicles, "10 ways to…" content, or press releases with no actual news.

## Constraints

- Python. `feedparser` for RSS. Anthropic Python SDK, Claude Sonnet (latest: `claude-sonnet-5-5`; builder confirms current model ID and pricing at build time) for curation.
- Public GitHub repo (owner accepted that drafts and the article list are publicly visible). Anthropic API key stored in GitHub Actions Secrets, never committed.
- GitHub Actions scheduled runs can start 5–30 min late or occasionally be skipped; acceptable.
- Each Actions run starts clean: any state must be committed back to the repo.

## Approaches considered

**Hosting / scheduling**
1. Local Mac with `launchd` — catches up after sleep, supports a live UI. Rejected: Mac must be on/awake.
2. **GitHub Actions + GitHub Pages (chosen)** — free for public repos, runs with the Mac off. Trade-off: no live backend, so the page is static and can't save clicks; scheduling is loose.
3. VPS — always-on and flexible, but costs money and maintenance; out of scope for v1.

**The page**
- **A) Python writes JSON data; one fixed HTML/JS page renders it (chosen).** Filtering/tabs are easy, the look is separate from the script, and the same data feeds future X posting.
- B) Python re-renders full HTML each run — no JS, but clumsy filtering and couples layout to the script.
- C) Static site generator (Hugo/MkDocs) — overkill for one page.

**Balancing topics**
- A single call picking 3–5 total — simplest, but one busy topic can take every slot.
- 3–5 required per category — balanced, but forces filler on slow days and ~100–150 drafts/day.
- **Up to 3 per category, 0 allowed, one Claude call per category (chosen by owner).** Balanced without filler; roughly 5–12 drafts per run in practice.

## Design

### Categories (initial)

| Category id | Name | Covers |
|---|---|---|
| `ai-bigtech` | AI & Big Tech | AI industry news; major tech companies' moves (Apple, Google, Microsoft, Meta, Amazon, OpenAI, Anthropic, etc.) |
| `semis` | Semiconductors | Chip market moves: DRAM/memory, Nvidia, Apple silicon, TSMC, Intel, AMD, fabs, export controls |
| `gaming` | Gaming | Gaming industry: business moves, layoffs, acquisitions, pricing, hardware, platform shifts, big releases with real numbers. Skip routine reviews, trailers, deals posts and guides unless they carry real industry news. |
| `india-tech` | Indian Tech & Startups | Indian tech and startups, including funding, employment opportunities, new job titles/roles, and economic impact |
| `world-markets` | World & Markets | World events and economics that signal a real market shift |

Planned later (config only): crypto, currency markets, AI developer tooling, AGI, etc.

### Config files

**`topics.yaml`** — one entry per category:

```yaml
- id: gaming
  name: Gaming
  max_picks: 3
  covers: business moves, layoffs, acquisitions, pricing, hardware, platform shifts, big releases with real numbers
  skip: routine reviews, trailers, deals posts, guides
```

Global skip rules and voice rules live in the prompt file (below), not per category.

**`sources.yaml`** — one entry per feed: `name`, `url`, `category` (one of the ids above), optional `kind` (`rss` default, `youtube`). Each feed belongs to exactly one category. Initial set:

| Source | Category | How | Notes |
|---|---|---|---|
| Reuters — Technology | ai-bigtech | Google News RSS search, e.g. `https://news.google.com/rss/search?q=site:reuters.com+technology+when:1d&hl=en-US&gl=US&ceid=US:en` | Reuters has no public RSS since 2020. Links are Google redirect URLs (fine; only used as "read article" links); titles end with " - Reuters" (strip it). |
| Reuters — Semiconductors/chips | semis | Google News RSS search (`site:reuters.com chips OR semiconductors`) | |
| Reuters — Gaming, Media | gaming | Google News RSS search | Media coverage that isn't gaming can go to `ai-bigtech`; builder's call. |
| Reuters — World, Business, Economics | world-markets | Google News RSS search per section | |
| AP News — Top stories, Business | world-markets | Google News RSS search on `site:apnews.com` | AP has no official public RSS. |
| AP News — Technology | ai-bigtech | Google News RSS search | |
| BBC News (top, business) | world-markets | Official RSS (`feeds.bbci.co.uk/news/rss.xml`, `/business/`) | |
| BBC Technology | ai-bigtech | Official RSS (`/technology/`) | |
| TechCrunch (main, AI, startups) | ai-bigtech | Official RSS | |
| IGN, GameSpot, Polygon, Eurogamer, PC Gamer, Kotaku, Rock Paper Shotgun | gaming | Official RSS for each | High-volume feeds; see the per-source cap. |
| Skill Up | gaming | YouTube channel RSS (`youtube.com/feeds/videos.xml?channel_id=…`) | Items are video titles; no article body. Builder looks up the channel ID. |
| Inc42, Economic Times Tech, Moneycontrol Tech | india-tech | Official RSS for each | |

The `semis` category starts thin (one Reuters search). Builder may add one reputable chips-focused feed if easily available; the owner will add more later.

Exact feed URLs are left to the builder to verify.

### Fetch & normalize

- Fetch each feed with a timeout; a failing feed is logged and skipped, never fatal.
- Normalize each item to: `id` (stable hash of canonical URL), `title`, `url`, `source`, `category`, `published_at` (UTC ISO 8601), `summary` (plain text, truncated to ~300 chars).
- Canonicalize URLs (strip `utm_*` and other tracking params) for dedupe.
- Drop items with no parseable publish date (they can't be checked against the 24h rule).
- Drop items older than 24h from run start.
- Deduplicate identical URLs within a run. Same-event-different-outlet dedupe is Claude's job.

### Curation (Claude) — one call per category

- For each category, one Messages API call. Input:
  - that category's candidates (id, source, title, summary, published time), capped **per source** (e.g. 15 newest per feed) so busy feeds can't crowd out others;
  - the category's `covers` / `skip` lines and `max_picks`;
  - **the last 24h of previous picks across all categories** (title + draft), so Claude avoids repeating an event over time or across categories.
- Categories are curated in a fixed order and each call also sees picks already made earlier in the same run, to prevent the same event appearing in two categories.
- Output via structured output / tool use: a list of 0–`max_picks` items `{article_id, post, reason}`. `reason` is a short note shown on the page, not posted.
- The system prompt (`prompts/curator.md`) encodes the owner's global rules; the category's lines are inserted each call:
  - Pick 0–3. Never pad; zero is a fine answer on a slow day. Quality over quantity.
  - Skip: celeb gossip, sports, listicles, "10 ways to…", press releases with no actual news, anything already in the previous picks.
  - Same event from multiple outlets: pick the version with the most specific detail (numbers, names, quotes).
  - Voice: dry, slightly skeptical, sarcastic. No hype words. One to two sentences. Lead with the concrete number or quote when there is one. No hashtags. **No links**: the post is text only (owner's decision, for reach). Write for engagement.
- The owner can tune the voice in `prompts/curator.md` without touching code, and later add a few of their own past posts as examples.
- Post-check in code: drop picks whose `article_id` isn't in that category's candidates or exceed `max_picks`; flag posts over 280 characters, containing `#` or a URL, or containing banned hype words (list kept in config). Flagged drafts are still shown, marked with a warning.
- **If a category's Claude call fails:** other categories carry on. The run still updates `articles.json` and publishes the page; the failed category is recorded with `status: "curation_failed"` and the page shows "curation failed" in that tab. If any category failed, the Actions run is marked failed so GitHub emails the owner.
- The Copy button copies the post text only. Google News redirect URLs never need resolving.

### Data (committed to the repo)

- `site/data/articles.json` — all articles fetched in the last 24h (rolling; older items pruned each run), merged across runs and deduped by `id`, each tagged with `category`.
- `site/data/picks.json` — list of runs: `{run_at, categories: {<id>: {status, picks: [{article_id, title, url, source, published_at, post, reason, flags}]}}}`. Keep 30 days.
- The page also needs category names/order; the bot writes them into the data (e.g. `site/data/meta.json`) from `topics.yaml`, so new categories show up as tabs automatically.

No `posted_urls.json`. The "don't repeat" memory comes from `picks.json`.

### The page (`site/index.html`, served by GitHub Pages)

- Static HTML + a small amount of JS that loads the JSON files.
- Tabs: **All**, then one per category (from `meta.json`).
- In each tab, top section: picks within the last 24h for that category, grouped by run, newest run first. Each pick shows the draft post, a **Copy** button, character count, any warning flags, Claude's reason, and the source article link with source name and date/time. "All" shows picks from every category, each labelled with its category.
- Below: all articles in that tab from the last 24h, newest first, each with title (linked), source, and date/time tag (absolute time in the viewer's local timezone plus "3h ago").
- Mobile-friendly. No login.

```
┌──────────────────────────────────────────────┐
│ News Bot              Last run: 18 Nov 14:02 │
│ [All] [AI & Big Tech] [Semis] [Gaming] [India] [World] │
├──────────────────────────────────────────────┤
│ PICKS — 14:02 run                            │
│ ┌──────────────────────────────────────────┐ │
│ │ "$4.2B for a fab that won't ship until   │ │
│ │  2029. Patience is a virtue, apparently."│ │
│ │ 112/280   [Copy]                         │ │
│ │ Reuters · 18 Nov 11:40 · 2h ago          │ │
│ └──────────────────────────────────────────┘ │
│ …                                            │
├──────────────────────────────────────────────┤
│ ALL ARTICLES (last 24h)                      │
│ 13:55  TechCrunch   Title…                   │
│ 13:41  BBC          Title…                   │
└──────────────────────────────────────────────┘
```

### Scheduling & first run

- GitHub Actions workflow on cron `0 */4 * * *` (UTC) plus a manual "Run workflow" button (`workflow_dispatch`).
- Steps: checkout → install deps → run bot → commit `site/data/*` back to the repo as a bot commit (only if changed) → deploy `site/` to GitHub Pages.
- A concurrency group so two runs never overlap.
- **First run behaviour:** a repo variable `DRY_RUN` starts as `true`. In dry-run mode the bot prints its picks and drafts (grouped by category) to the Actions log and writes nothing. The owner reviews curation quality in the log, then sets `DRY_RUN=false` to start publishing to the page. (Designer's call: a switch is more reliable than detecting "first run", and lets the owner go back to dry-run any time.)
- The bot also runs locally (`python -m newsbot --dry-run`) with the API key from a local `.env` (gitignored), for testing.

### Cost

About 5 Claude calls per run × 6 runs/day = ~30 calls/day, each with up to a few hundred short headlines. Expected to stay in the cents-per-run range; builder confirms with current Sonnet pricing.

### Future (shape v1 so these are easy)

- X API auto-posting: a separate `post` step that reads the latest picks from `picks.json`. Individual posts vs. thread is decided then.
- More sources, topics, categories: config only.

## Left to the builder

- Exact feed URLs, the Skill Up channel ID, and which category Reuters Media lands in.
- Code layout, page styling, exact retention numbers and per-source cap, banned-word list contents (seed with the owner's examples: "game-changer", "masterstroke").
- Whether to use the SDK's structured output feature or a tool definition for the JSON response.
- Testing approach.

---

## v1.1 change: run curation through Claude Code on the Pro plan (2026-11-21)

**Why:** The owner has a Claude Pro plan and doesn't want to pay for API usage (~₹6000/month at Sonnet API rates). Claude Code is included in Pro and can run headless.

**Approaches considered:**
- **`claude -p` subprocess on the owner's Mac (chosen).** Uses the Pro allowance, so it costs nothing extra. Same Claude models. Verified on 2026-11-21: `claude -p --model haiku --tools "" --json-schema … --output-format json` returns `structured_output` plus token `usage`.
- Claude Code in GitHub Actions with a subscription token (`claude setup-token`). The Mac wouldn't need to be on, but it's unverified on Pro. Revisit later.
- Free third-party models (Gemini/Groq) or a local model (Ollama). Rejected for now: weaker voice and judgment.

**Design:**
- `settings.yaml` gains `backend: claude-code` (default) or `api`, and `model` takes `haiku` / `sonnet` for claude-code. The API code stays as the `api` backend.
- The claude-code backend runs: `claude -p --model <m> --system-prompt <prompt> --json-schema <CurationResult schema> --tools "" --strict-mcp-config --setting-sources "" --no-session-persistence --output-format json`, with the candidate list on stdin and a 5-minute timeout. A missing CLI, non-zero exit, `is_error`, a timeout, or bad JSON makes that category `curation_failed`; other categories continue. Pro usage limits are handled the same way.
- **Token tracking:** each category result records `usage` (input, cache write, cache read, output, thinking tokens) and `model`. The run summary prints per-category and total tokens. `picks.json` keeps them, so usage can be compared over days.
- **Model comparison:** `python scripts/compare_models.py` fetches once, runs every category through Haiku and then Sonnet on the **same** candidates, and writes `compare-<date>.md`. That file shows drafts side by side plus a token table, so the owner can judge whether Haiku is good enough. It writes nothing to `site/data`.
- **Scheduling moves to the Mac:** a `launchd` job runs `scripts/run_and_publish.sh` every 4 hours and catches up after sleep. The script does `git pull`, `python -m newsbot`, then commits and pushes `site/data` if anything changed. The GitHub workflow no longer runs the bot; it only deploys Pages when `site/data` changes on `main`. The `DRY_RUN` switch moves to `.env`.
- **Trade-offs accepted:** the Mac must be awake for runs (catch-up on wake), and heavy personal Claude use on the same day can exhaust the Pro limit and fail a run.

---

## v1.2 change: stat cards and article images (2026-11-21)

**Why:** Posts with images get more reach on X. The owner wants a branded card per post, plus the article's own picture to edit and use themselves.

**Approaches:** (A, chosen) the page draws the cards in the browser with `<canvas>` and offers them as PNG downloads; (B) Pillow PNGs per run; (C) a headless-Chrome screenshot. B and C were rejected because they commit images every run (~4 MB/day of git history) and re-render whenever the design changes.

**Design:**
- Claude returns `card_text` per pick: the single most concrete number or short quote, max 60 chars, no hashtags or links. The prompt gets one rule for it. The schema gains the field. `checks.py` flags `card_too_long` when it's over 60 chars.
- `fetch.py` stores `image_url` per article from the feed (`media:content`, `media:thumbnail`, enclosure of type image, or the first `<img>` in the summary). Only http(s) is kept; otherwise `null`. Nothing is downloaded or re-hosted.
- Picks carry `card_text` and `image_url`. Older picks without them still render (no card text → a card from the headline).
- `settings.yaml` gains `card_handle` (default `"@yourhandle"`) and `card_tagline` (optional). Both are written to `meta.json`.
- The page shows a 1200×675 dark card preview per pick: big `card_text`, source and date small, handle/tagline in a corner, text wrapped to fit. There's a **Download card** button (canvas → PNG, filename from the date and title). When the article has an image, there's a thumbnail and an **Open original image** link (new tab, `safeHref`).
- **Cost:** about 150 extra output tokens per run.

---

## v1.3 change: drama voice and new topic mix (2026-11-23)

**Why:** The live drafts read as neutral, insider and sarcastic, and the World/India/markets topics didn't fit. The owner wants posts that start arguments in the comments, modelled on @Pirat_Nation: plain-English news bulletins about gaming, pop-tech and AI drama that any regular person can have an opinion on.

**Decided with the owner:**
- Categories become: **Gaming** (core, up to 3), **Tech & AI drama** (core, up to 3), **Trending for everyone** (up to 1; only stories a regular person cares about and that could trend). Indian startups and World & Markets stop being categories; their feeds, plus the chip feeds, feed "Trending".
- Voice: first line is the story in plain words (big name + concrete fact), then one line of context plus the tension (contrast, backlash, contradiction) that makes people take sides. Confident framing ("players are furious") only when the article supports it. Never invent facts, numbers or quotes. No sarcasm, no "I", no hashtags, no links, no jargon. Max 280 chars (the owner has no X Premium; `max_post_chars` is the single switch), 2–3 short lines separated by line breaks.
- New sources, added if their feeds verify: The Verge, Dexerto, VGC, Insider Gaming, Windows Central, 9to5Mac.
- Page: the article's own image is shown larger and first; the stat card comes second.
- The owner reviews a dry run (new style next to the last live drafts) before it goes live.

---

## v1.4 change: image finder (2026-11-24)

**Why:** Posts with pictures get more reach on X. The owner doesn't know where to find good images, and the article's own photo is often licensed (Getty, Reuters). The owner wants the bot to find candidate images per post and show them on the page, so they can pick, download and edit one. Picking the right image takes judgement, so this is where an AI model earns its place. Auto-posting to X is **deferred** until the owner pays for the X API (pay-per-use, about $0.015 per post). It was designed as a local "Post" button with a per-post image choice (stat card / article image / own upload / none), and that design comes back later.

**What the owner wants:** a mix of official images of the subject (game art, CEO or company photos, products) and proof screenshots (Metacritic score, Downdetector map), "whichever is easier to procure". Official images can be fetched automatically. Proof screenshots can't be taken reliably (Metacritic, Downdetector and X block bots or need a login, and the project rule is to not scrape sites that block bots), so the bot **suggests** a screenshot with a search link and the owner takes it by hand.

**Goals**
- Each new pick shows up to 4 candidate images that fit the post, best first, with source and licence credit, plus at most one "Screenshot idea" line with a link.
- Free: the Claude Code call on the Pro plan (a few dozen extra output tokens per pick), free public APIs, and a local Ollama vision model.
- A run never fails because of images.

**Non-goals:** posting to X; downloading or storing images in the repo; taking screenshots automatically; editing images; images for old picks (only picks made from v1.4 on get them).

**Anti-goals:** scraping sites that block bots or spoofing a User-Agent; images that clearly don't match the story shown as "best"; the 4-hourly run becoming slow enough to overlap the next one; the image step breaking the post drafts.

**Approaches**
- **(A, chosen) Haiku plans, plain code fetches, Ollama picks.** The existing Haiku call already understands each story, so it also writes 0–3 image searches and a screenshot idea. Plain Python calls the image sources. A local Ollama vision model looks at each candidate next to the post and scores it; the top ones are kept.
- (B) A full Ollama agent (e.g. Google ADK) that decides what to search, calls tools and picks. Rejected: small local models are unreliable at multi-step tool use, it's slower and harder to test, and it re-reads stories Haiku already understood.
- (C) No vision model: keep the first result per search. Rejected: nothing checks that the picture fits ("Xbox" can return a random accessory).

**Design**

1. **Haiku output (schema + prompt).** `Pick` gains two required fields:
   - `image_searches`: list of 0–3 `{source, query}` where `source` is one of `wikimedia`, `steam`, `openverse`. Prompt guidance: `steam` for a named PC/console game (its exact title), `wikimedia` for a named person, company, product or place, `openverse` for a generic visual (a server room, a game controller, an office) when nothing specific fits. Queries are short (2–6 words), names spelled as in the story.
   - `screenshot_idea`: `{text, search}`, or both empty strings when nothing fits. `text` is one line for the owner ("Metacritic user score page for GTA 6"); `search` is a web search phrase ("GTA 6 metacritic user score"). The link is built by code as `https://www.google.com/search?q=<url-encoded search>`, never taken from the model, so it can't be a broken or made-up URL.
   - Invalid entries (unknown source, empty or >80-char query) are dropped silently; more than 3 searches are truncated.

2. **Image sources (`newsbot/images.py`).** Each source is a function `(query, http_get) -> list[Candidate]` returning up to 5 candidates. A `Candidate` has `url` (full size), `thumb` (~640 px wide where available), `page_url` (where it lives), `source`, `credit`, `license`. Only http(s) URLs are kept (same check as feed links). Duplicates by `url` are removed.
   - **wikimedia** (no key): Commons API search in the file namespace, bitmaps only, with `prop=imageinfo`, `iiprop=url|extmetadata|mime`, `iiurlwidth=640`. `credit` from `Artist` (HTML stripped), `license` from `LicenseShortName`. Wikimedia requires a descriptive User-Agent with contact info. Decided with the owner: every request the bot makes (feeds, Wikimedia, Steam, Openverse, image thumbnails) sends `newsbot/1.4 (+https://github.com/AbhishekKr11511/newsbot)`, defined once as a constant in `fetch.py` and replacing today's `newsbot/1.0`. No email. It's never a browser UA.
   - **steam** (no key): store search `store.steampowered.com/api/storesearch/?term=<q>&l=english&cc=US`, take the top match, then `api/appdetails?appids=<id>` for `header_image` and the first 2 `screenshots` (3 candidates max, so one game can't crowd out everything else). `credit` = "Official art · Steam", `license` = "Promotional". These endpoints are public but undocumented; if they start refusing, the source returns nothing.
   - **openverse** (no key; replaces Pexels, which paused new API keys on 2026-11-24): `api.openverse.org/v1/images/?q=<q>&page_size=5&license_type=commercial,modification`, so only licences that allow editing and commercial use (CC BY, BY-SA, CC0, PDM). `credit` = "<title> by <creator> (<source>)", `license` = upper-cased licence + version (e.g. "CC BY-SA 2.0"), `page_url` = `foreign_landing_url`, `thumb` = the result's `thumbnail` or `url`. Anonymous limits are 20/min and 200/day; the bot uses at most ~42/day. A 429 response returns nothing for the rest of the run (no retries). Checked live 2026-11-24.
   - IGDB (needs a Twitch developer account) is left for later.
   - The article's own `image_url` is not a candidate; it keeps its existing hero slot.

3. **Ranking with Ollama.** For each candidate, the bot downloads the `thumb` into memory only (same 5 MB / 30 s caps as feeds, never written to disk) and asks Ollama (`POST {ollama_url}/api/chat`, `stream: false`, the image as base64, a JSON `format` schema) to score how well it fits the post from 0 to 10, with a reason of up to 12 words. Each pick scores at most `max_scored` candidates (default 8), taken round-robin across its searches (first of each search, then second of each, …) so every search gets a look. Images scoring below `min_score` (default 5) are dropped; the rest are sorted by score and the top `keep` (default 4) are kept, with at most 2 from any one source so the owner sees a mix (builder's call, 2026-11-24). Each kept image records its `score`.
   - If Ollama isn't reachable, the model isn't installed, or a call errors or times out, ranking is skipped for the rest of the run. Picks keep their first `keep` candidates in the same round-robin order (still at most 2 per source) with `score: null`, and the page labels them "unranked".
   - Model: `gemma3:4b` (vision-capable, ~3.3 GB, fine on the owner's 16 GB M5). The owner runs `ollama pull gemma3:4b` once. The Ollama app must be running for ranked results; it's not required for the run to succeed.

4. **Time budget, two phases** (builder's call, 2026-11-24). Phase 1 fetches candidates for every pick (HTTP only, fast). Phase 2 ranks round-robin across picks (one candidate from pick 1, then pick 2, …), so a slow model can't leave a whole category unranked. The whole image step has a budget (`budget_s`, default 300). Each HTTP call uses `fetch_timeout_s`; each Ollama call has a 60 s timeout. When the budget runs out, each pick keeps its scored candidates and fills any remaining slots from its unscored ones in round-robin order (unscored ones carry `score: null`). Sizing: 7 picks × 8 = 56 calls × ~3 s ≈ 3 minutes, inside the budget.

5. **Where it runs.** In `run.py`, after `curate_all` and before saving: for each new pick, run the searches, rank, and attach `images` (list of kept candidates with `score`) and `screenshot_idea` (`{text, url}` or `null`). Dry run does the image step too and prints one line per pick: "images: 3 ranked (wikimedia 2, steam 1)" plus the screenshot idea. `--no-images` skips the step. Any exception in the image step for a pick is caught: that pick gets `images: []` and the run continues.

6. **Settings (`settings.yaml`).**
   ```yaml
   images:
     enabled: true
     sources: [wikimedia, steam, openverse]
     ollama_url: http://localhost:11434
     ollama_model: gemma3:4b
     keep: 4
     max_scored: 8
     min_score: 5
     budget_s: 300
   ```
   A missing block means the defaults. `enabled: false` skips the image step; Haiku still returns the image fields (one schema for both cases), and they're ignored.

7. **Page.** Under each pick's article image (hero) and before the stat card: a "Found images" row of up to 4 thumbnails (`<img loading="lazy" referrerpolicy="no-referrer">`, built with DOM APIs, never `innerHTML`). Each shows the credit and licence under it and links "Open full size" (the full `url`, new tab, `safeHref`) and "Source" (`page_url`). Unranked sets show a small "unranked" note. If there's a screenshot idea: one line "Screenshot idea: <text>" with a "Search" link. Found images are never drawn on the canvas (that would block Download card). Picks without these fields render as before.

8. **Data.** Only links and text are committed (in `picks.json`). No image files.

9. **Cost.** Pro plan: roughly 40–80 extra output tokens per pick. HTTP: about 2–6 API calls per pick. Ollama: up to `max_scored` (8) local scoring calls per pick, roughly 2–5 s each once the model is loaded.

**Left to the builder:** module layout inside `images.py`; exact prompt wording (following the rules above); how the Ollama prompt phrases the scoring; thumbnail sizes in CSS; how tests fake HTTP and Ollama (inject `http_get` and an Ollama callable, as the rest of the code does).
