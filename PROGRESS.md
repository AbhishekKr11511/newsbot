# Progress

**Status (2026-11-24):** **LIVE** since 2026-11-23, now with v1.4 (image finder), merged and pushed 2026-11-24. 178 tests passing. The schedule runs from `~/code/newsbot` every 4 hours (00, 04, 08, 12, 16, 20) and publishes to https://abhishekkr11511.github.io/newsbot/. Repo: https://github.com/AbhishekKr11511/newsbot. Waiting on the first scheduled run with images to confirm it works under launchd.

## Done

### v1.4: image finder
- [x] Haiku suggests 0–3 image searches + a screenshot idea per pick
- [x] Wikimedia, Steam and Openverse search (no keys); Pexels dropped (new API keys paused)
- [x] Local Ollama `gemma3:4b` judges each image (yes/partly/no vs the search term), 5-minute budget, round-robin across picks
- [x] Page: "Found images" grid with credits and links, "Screenshot idea" with a search link
- [x] Thumbnail downloads refuse private/local hosts (security review)
- [x] Regression pass: 6 review minors fixed, plus two bugs found by end-to-end runs (cut-off Ollama answers stopped ranking; Openverse unusable because Flickr blocks the bot)

### v1.3: drama voice
- [x] Pirat_Nation-style bulletin voice; 3 categories; 36 feeds; image-first page

### v1.2: images for posts
- [x] Claude writes a `card_text` (key number or quote, max 60 chars) per pick
- [x] Page draws a downloadable 1200×675 stat card per post, with your handle
- [x] Article's own image link saved from the feed, with an "Open original image" button (Reuters/AP have none)
- [x] Guard: picks whose draft is placeholder text are dropped

### v1.1: free curation via the Pro plan
- [x] Claude Code backend (`claude -p`), Haiku or Sonnet via `settings.yaml` or `--model`
- [x] Token tracking per category and per run (printed and saved in `picks.json`)
- [x] `scripts/compare_models.py`: Haiku vs Sonnet on the same headlines
- [x] Mac schedule (launchd, every 4h, catches up after sleep) plus a publish script
- [x] GitHub workflow simplified to publish the page only
- [x] First live comparison run (results below)
- [x] Final review fixes: the schedule commits only `site/data`, only on `main`, and stops cleanly if `git pull` fails

### v1: core bot
- [x] Config files: `sources.yaml` (30 feeds), `topics.yaml` (5 categories), `settings.yaml`
- [x] Feed fetching with a 24h window, dedupe, safe links, and size/time caps
- [x] Claude curation per category (0–3 picks), post checks, JSON store
- [x] Static page: category tabs, picks with Copy buttons, all articles with local times
- [x] Final code review; the serious findings are fixed

## Next steps (owner)

0. ~~Go live~~ ✅ 2026-11-23.

1. ~~Decide Haiku or Sonnet~~: Haiku (2026-11-23).
2. ~~Put it on GitHub~~ ✅ done 2026-11-21 (Pages enabled via the workflow).
3. ~~Install the schedule~~ ✅ done 2026-11-23, running from `~/code/newsbot` (macOS blocked `~/Documents`). Earlier notes: `bash scripts/install_schedule.sh` and `launchctl kickstart gui/$(id -u)/com.newsbot.run`. Check `logs/run.log` for a new entry: macOS may block background jobs in `~/Documents` (see the README). If it does, move the project to e.g. `~/code/newsbot`. Keep `DRY_RUN=true` in `.env` for the first day, then remove it.
4. ~~Put your X handle in `settings.yaml`~~ ✅ `@nomicsexpress`.
5. Optional: add a few of your own past posts at the bottom of `prompts/curator.md` to sharpen the voice.
6. Keep the **Ollama app running** so found images are ranked (`ollama pull gemma3:4b` done 2026-11-24). If it's closed, images still appear, marked "unranked".
7. Check the first scheduled run with images (20:00 IST, 2026-11-24): images on the page, no warnings in `~/code/newsbot/logs/run.log`.
8. Later: "Post" button on a local page once the X API is paid for (design in the spec, v1.4 section).

## Open decisions

- ~~Haiku vs Sonnet~~ Decided 2026-11-23: **Haiku** for now. Switch with `model: sonnet` in `settings.yaml` if draft quality disappoints.
- Later: run on GitHub instead of the Mac using a subscription token (`claude setup-token`). Unverified on Pro.
- Later: posting via the X API (pay-per-use, about $0.015 per post, no free tier for new apps since Feb 2026). Planned as a local "Post" button with your approval per post, not autopilot.
- Later: IGDB as a fourth image source for console-only games (needs a free Twitch developer account).
- If image picks disappoint: try `ollama_model: qwen2.5vl:7b` in `settings.yaml` (bigger, better at reading text in images).

## Measurements

| Date | Model | Input + cache tokens | Output tokens (thinking) | API-equivalent $ | Notes |
|---|---|---|---|---|---|
| 2026-11-21 | haiku | 48,106 | 11,096 (9,225) | 0.014 | 12 drafts; Semiconductors: no picks |
| 2026-11-21 | sonnet | 48,905 | 2,094 (0) | 0.207 | 14 drafts; more concrete numbers, more questions at the end |

On Pro you don't pay the $ column. Sonnet uses more of your Pro allowance per run than Haiku does.

**v1.4 image step (dry runs, 2026-11-24, M5 16 GB, gemma3:4b):** whole run 140–300 s (was ~90 s). Ranking takes about 3–6 s per image, up to 8 per pick, capped at 5 minutes per run. Haiku output grew by roughly 50 tokens per pick. Last dry run: 6 drafts, all with 4 ranked images.

## Known minor issues (deferred)

- Card: a very long handle plus tagline can overlap; the source/date line isn't wrapped; one very long word can truncate to "…".
- Card: font size and line spacing can be slightly out of step at the smallest size (still fits).
- One pick missing `card_text` fails its whole category (only if the CLI doesn't enforce the schema).
- Plain-http article images may not show as thumbnails on the https page ("Open original image" still works).

- `run_and_publish.sh`'s PATH covers `~/.local/bin` and Homebrew, not nvm-installed `claude`.
- Errors other than "not found" or a timeout when starting `claude` (e.g. a permissions error) would stop the whole run.
- Token counts are visible in the public `site/data/picks.json`.

- Some feeds' timezone-less RFC-822 dates are skipped instead of read as UTC.
- A corrupted `site/data/*.json` would need fixing by hand (writes are atomic, so this is unlikely).

- Images: a typo in the `images:` block of `settings.yaml` stops the whole run (drafts too) with a clear error naming the setting.
- Images: Flickr blocks the bot's honest User-Agent, so Openverse skips Flickr; generic photos come mostly from Wikimedia.
- Images: a related-but-different subject can pass the yes/partly/no check (e.g. a Microsoft campus photo for an Outlook story).
- Images: the thumbnail host check can in theory be bypassed by DNS rebinding (accepted for a local bot; worst case one unwanted request to a device on your network).
- Images: Steam only matches when its store name contains every word of the search, so games listed under another name get no Steam art.
- The All tab has no "nothing new" line for empty categories.

## Log

- **2026-11-24**: Regression pass on v1.4 (178 tests): fixed the 6 review minors plus two bugs found by real runs (a cut-off Ollama answer stopped all ranking; Openverse returned nothing because Flickr blocks the bot). Merged to `main` and pushed; the scheduled copy pulled it. X auto-posting deferred until the X API is paid for.
- **2026-11-24**: v1.4 image finder (157 tests). Live runs: ~145 s per run incl. ~60 s of ranking; Nvidia/Outlook drafts got relevant Wikimedia photos. Learned: gemma3:4b scores nearly everything 8/10 on a free scale, so it answers yes/partly/no instead; Steam returns GTA V for "GTA VI" (now requires a name match); Openverse SVGs broke ranking (now jpg/png only, bad images skipped); Flickr 403s the bot's honest User-Agent, so Openverse now excludes Flickr.

- **2026-11-17**: Design agreed: categories, 0–3 picks each, static page, GitHub Pages.
- **2026-11-18**: v1 plan written.
- **2026-11-21**: v1 built (52 tests). Final review fixed: refusal crash, `<` in titles, pinned deps, push race. Moneycontrol dropped (blocks bots); YourStory and Mint added.
- **2026-11-23**: v1.3: drama voice modelled on @Pirat_Nation. Categories are now Gaming, Tech & AI drama (incl. outages), and Trending for everyone (max 1). Six new feeds (36 total). Article image shown first. Claims attributed in the first line, no disclaimer lines.
- **2026-11-23**: Went live. First live scheduled run: 15 drafts, committed and pushed from launchd, Pages deployed, page shows @nomicsexpress cards.
- **2026-11-23**: Model decision: Haiku.
- **2026-11-23**: Notifications confirmed working from the schedule (needed Script Editor to be allowed once). Second scheduled dry run: exit 0, 10 drafts.
- **2026-11-23**: Schedule installed from a clone at `~/code/newsbot` (macOS privacy blocked launchd in `~/Documents`, exit 126). First scheduled dry run: exit 0, 467 articles, 13 drafts. Added macOS notifications. Pull now runs on dry runs too.
- **2026-11-21**: Merged to `main`, created public repo AbhishekKr11511/newsbot, enabled Pages; first deploy succeeded.
- **2026-11-21**: v1.2 stat cards and article images (89 tests). Live run: 9 picks, 6 with article images, ~61k tokens. Caught Haiku returning "placeholder" drafts once, so validation now drops them.
- **2026-11-21**: v1.1 review: fixed scoped commit, branch guard, and clean stop on a failed pull (78 tests).
- **2026-11-21**: Switched to Claude Code on the Pro plan (v1.1). Token tracking, model comparison, Mac schedule. First live dry run: 527 articles, 14 Haiku drafts, ~58k tokens.
