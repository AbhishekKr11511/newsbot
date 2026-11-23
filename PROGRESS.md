# Progress

**Status (2026-11-21):** v1.2 is built and tested (91 tests passing). It runs end to end on the Mac through Claude Code on the Pro plan. It's on GitHub (https://github.com/AbhishekKr11511/newsbot), merged to `main`, and the page is live at https://abhishekkr11511.github.io/newsbot/ (empty until the first published run). The schedule is installed and runs from `~/code/newsbot` (still in dry-run mode).

## Done

### v1: core bot
- [x] Config files: `sources.yaml` (30 feeds), `topics.yaml` (5 categories), `settings.yaml`
- [x] Feed fetching with a 24h window, dedupe, safe links, and size/time caps
- [x] Claude curation per category (0–3 picks), post checks, JSON store
- [x] Static page: category tabs, picks with Copy buttons, all articles with local times
- [x] Final code review; the serious findings are fixed

### v1.1: free curation via the Pro plan
- [x] Claude Code backend (`claude -p`), Haiku or Sonnet via `settings.yaml` or `--model`
- [x] Token tracking per category and per run (printed and saved in `picks.json`)
- [x] `scripts/compare_models.py`: Haiku vs Sonnet on the same headlines
- [x] Mac schedule (launchd, every 4h, catches up after sleep) plus a publish script
- [x] GitHub workflow simplified to publish the page only
- [x] First live comparison run (results below)
- [x] Final review fixes: the schedule commits only `site/data`, only on `main`, and stops cleanly if `git pull` fails

### v1.2: images for posts
- [x] Claude writes a `card_text` (key number or quote, max 60 chars) per pick
- [x] Page draws a downloadable 1200×675 stat card per post, with your handle
- [x] Article's own image link saved from the feed, with an "Open original image" button (Reuters/AP have none)
- [x] Guard: picks whose draft is placeholder text are dropped

## Next steps (owner)

0. **Go live:** after a day of dry runs looks good, delete `DRY_RUN=true` from `~/code/newsbot/.env` (not the Documents copy).

1. **Decide Haiku or Sonnet** after reading `compare-2026-11-21-1304.md`. Run the comparison a couple more times on different days.
2. ~~Put it on GitHub~~ ✅ done 2026-11-21 (Pages enabled via the workflow).
3. ~~Install the schedule~~ ✅ done 2026-11-23, running from `~/code/newsbot` (macOS blocked `~/Documents`). Earlier notes: `bash scripts/install_schedule.sh` and `launchctl kickstart gui/$(id -u)/com.newsbot.run`. Check `logs/run.log` for a new entry: macOS may block background jobs in `~/Documents` (see the README). If it does, move the project to e.g. `~/code/newsbot`. Keep `DRY_RUN=true` in `.env` for the first day, then remove it.
4. Put your X handle in `settings.yaml` → `card_handle`.
5. Optional: add a few of your own past posts at the bottom of `prompts/curator.md` to sharpen the voice.

## Open decisions

- Haiku vs Sonnet (see the measurements below).
- Later: run on GitHub instead of the Mac using a subscription token (`claude setup-token`). Unverified on Pro.
- Later: auto-post via the X API.

## Measurements

| Date | Model | Input + cache tokens | Output tokens (thinking) | API-equivalent $ | Notes |
|---|---|---|---|---|---|
| 2026-11-21 | haiku | 48,106 | 11,096 (9,225) | 0.014 | 12 drafts; Semiconductors: no picks |
| 2026-11-21 | sonnet | 48,905 | 2,094 (0) | 0.207 | 14 drafts; more concrete numbers, more questions at the end |

On Pro you don't pay the $ column. Sonnet uses more of your Pro allowance per run than Haiku does.

## Known minor issues (deferred)

- Card: a very long handle plus tagline can overlap; the source/date line isn't wrapped; one very long word can truncate to "…".
- Card: font size and line spacing can be slightly out of step at the smallest size (still fits).
- One pick missing `card_text` fails its whole category (only if the CLI doesn't enforce the schema).
- Plain-http article images may not show as thumbnails on the https page ("Open original image" still works).

- The schedule under launchd is untested until you install it (macOS privacy on `~/Documents`; git credentials once a remote exists).
- `run_and_publish.sh`'s PATH covers `~/.local/bin` and Homebrew, not nvm-installed `claude`.
- Errors other than "not found" or a timeout when starting `claude` (e.g. a permissions error) would stop the whole run.
- Token counts are visible in the public `site/data/picks.json`.

- Some feeds' timezone-less RFC-822 dates are skipped instead of read as UTC.
- A corrupted `site/data/*.json` would need fixing by hand (writes are atomic, so this is unlikely).
- The All tab has no "nothing new" line for empty categories.

## Log

- **2026-11-17**: Design agreed: categories, 0–3 picks each, static page, GitHub Pages.
- **2026-11-18**: v1 plan written.
- **2026-11-21**: v1 built (52 tests). Final review fixed: refusal crash, `<` in titles, pinned deps, push race. Moneycontrol dropped (blocks bots); YourStory and Mint added.
- **2026-11-23**: Schedule installed from a clone at `~/code/newsbot` (macOS privacy blocked launchd in `~/Documents`, exit 126). First scheduled dry run: exit 0, 467 articles, 13 drafts. Added macOS notifications. Pull now runs on dry runs too.
- **2026-11-21**: Merged to `main`, created public repo AbhishekKr11511/newsbot, enabled Pages; first deploy succeeded.
- **2026-11-21**: v1.2 stat cards and article images (89 tests). Live run: 9 picks, 6 with article images, ~61k tokens. Caught Haiku returning "placeholder" drafts once, so validation now drops them.
- **2026-11-21**: v1.1 review: fixed scoped commit, branch guard, and clean stop on a failed pull (78 tests).
- **2026-11-21**: Switched to Claude Code on the Pro plan (v1.1). Token tracking, model comparison, Mac schedule. First live dry run: 527 articles, 14 Haiku drafts, ~58k tokens.
