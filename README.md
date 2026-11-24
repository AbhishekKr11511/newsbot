# News Bot

Every 4 hours this bot:

1. Pulls the last 24 hours of headlines from the feeds in `sources.yaml` (Reuters, AP, BBC, TechCrunch, gaming sites, Indian tech outlets…).
2. Asks Claude (Haiku or Sonnet, through **Claude Code on your Pro plan**, so no API bill) to pick **0–3 stories per category** (AI & Big Tech, Semiconductors, Gaming, Indian Tech & Startups, World & Markets) and draft a post for each in your voice. Claude skips repeats, gossip, sports and fluff.
3. Publishes everything to a web page: picks with a **Copy** button on top, all articles below, one tab per category.
4. Draws a **stat card** image (1200×675) for each post, the key number or quote in big type with your handle, and links the article's own picture when the feed has one. Use **Download card** and **Open original image** on each pick.

You read the page, copy the posts you like, and post them to X yourself.

The bot runs on your Mac every 4 hours (catching up after sleep) and pushes the results to GitHub, which publishes the page on GitHub Pages.

---

## One-time setup

**On your Mac** (you need Claude Code installed and logged in with your Pro plan: `claude` works in Terminal):

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
echo "DRY_RUN=true" >> .env          # first day: print drafts only
python -m newsbot --dry-run          # try one run now
python scripts/compare_models.py     # Haiku vs Sonnet on the same headlines -> compare-*.md
```

Pick the model in `settings.yaml` (`model: haiku` or `model: sonnet`).

**On GitHub** (for the web page):
1. Create a public repo (e.g. `newsbot`), then `git remote add origin https://github.com/<you>/newsbot.git && git push -u origin main`.
2. Settings → Pages → Source: **GitHub Actions**.

**Turn on the schedule:**
```bash
bash scripts/install_schedule.sh                       # every 4h: 00, 04, 08, 12, 16, 20
launchctl kickstart gui/$(id -u)/com.newsbot.run       # optional: run once right now
tail -f logs/run.log                                   # watch what it did
```
**How it's set up on this Mac:** macOS blocks background jobs from reading `~/Documents`, so the schedule runs from a second copy at `~/code/newsbot` (cloned from GitHub, with its own `.venv` and `.env`). Keep editing in your usual folder and `git push`. The scheduled copy runs `git pull` at the start of every run, so it picks up your changes. Its log is `~/code/newsbot/logs/run.log`. Go live by deleting `DRY_RUN=true` from **`~/code/newsbot/.env`**.

To set it up on another Mac: `git clone … ~/code/newsbot && cd ~/code/newsbot && python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt && cp .env.example .env && bash scripts/install_schedule.sh`.

After each run you get a macOS notification ("News Bot: 13 drafts ready" or "News Bot: run failed"). macOS sends these as **Script Editor** and silently drops them until it is allowed: open Script Editor once, run `display notification "hello" with title "News Bot"`, click **Allow**, and keep its alert style on Banners.

**Check the schedule can actually run.** macOS blocks background jobs from reading `~/Documents`, `~/Desktop` and `~/Downloads` unless you allow it. After the kickstart above, look at `logs/run.log`. If there's no new entry, or `logs/launchd.log` says "Operation not permitted", the easiest fix is to move the project out of those folders (e.g. to `~/code/newsbot`) and rerun `install_schedule.sh`.

The schedule only commits when the repo is on the `main` branch. On any other branch it writes data locally and says so in the log.

When the drafts look good, delete the `DRY_RUN=true` line from `.env`. Each run then commits `site/data` and pushes, and GitHub republishes the page at `https://<you>.github.io/<repo>/`.

Uninstall the schedule: `launchctl bootout gui/$(id -u)/com.newsbot.run && rm ~/Library/LaunchAgents/com.newsbot.run.plist`

---

## Image finder (v1.4)

Each new draft gets up to 4 **found images** on the page (with credit, licence, "Open full size" and "Source" links), plus an optional **Screenshot idea** with a search link.

- Haiku suggests the searches; the bot looks in **Steam** (official game art), **Wikimedia Commons** (people, companies, products) and **Openverse** (generic photos with licences that allow editing and commercial use). No keys or accounts.
- A local vision model judges each picture ("does this clearly show *Grand Theft Auto V*?") and keeps the best ones. One-time setup: `ollama pull gemma3:4b`, and keep the **Ollama app running** (menu bar). If it isn't running, you still get images, marked "unranked".
- Settings live under `images:` in `settings.yaml` (switch off with `enabled: false`, or try `ollama_model: qwen2.5vl:7b`). Skip for one run with `python -m newsbot --dry-run --no-images`.
- **Licences are your call.** Steam art is promotional; Wikimedia and Openverse images mostly need a credit (shown under each image), so add it to your post if you use one.
- Adds about 2–3 minutes per run. Only links are saved; no image files go into the repo.

## Changing what it covers

All of this is plain text editing. No code changes are needed. Push the change to GitHub and the next run picks it up.

| I want to… | Edit |
|---|---|
| Add or remove a news source | `sources.yaml`: copy a block and change `name`, `url`, `category` |
| Add a new category (e.g. Crypto) | `topics.yaml`: add a block with a new `id`, then point feeds at it in `sources.yaml` |
| Change what counts in a category | `topics.yaml`: edit `covers` / `skip` |
| Change the voice or rules | `prompts/curator.md`. You can add a few of your own past posts at the bottom as examples. |
| Pick more or fewer per category | `topics.yaml`: `max_picks` |
| Put your handle on the cards | `settings.yaml`: `card_handle` (and optional `card_tagline`) |
| Change the card look | `site/app.js`: `drawCard` (colours, sizes) |
| Run more or less often | `scripts/com.newsbot.run.plist.template` hours, then rerun `install_schedule.sh` |
| Use less of your Pro allowance | `settings.yaml`: `model: haiku`, or lower `per_source_cap` |
| Switch model | `settings.yaml`: `model: haiku` / `sonnet` |

After adding a feed, check it works: `python scripts/check_feeds.py`

---

## Handy commands

```bash
python -m newsbot --dry-run [--model sonnet]   # one run, prints drafts + token usage
python scripts/check_feeds.py                  # checks every feed URL
python scripts/sample_data.py site/data && python -m http.server -d site 8000   # preview page with fake data
rm site/data/*.json                            # clean up the fake data before committing
pytest                                         # tests
```

---

## Cost

**₹0 extra.** Curation runs through Claude Code on your Pro plan. Each run uses ~50–60k tokens (5 categories), which counts against your Pro usage limits. Haiku uses less of the allowance than Sonnet. On a day you use Claude heavily yourself, a run might hit the limit. Those categories then show "curation failed" and the next run tries again. Every run prints its token usage, and `site/data/picks.json` keeps it.

Prefer the paid API instead? Set `backend: api` and a full model id (e.g. `claude-haiku-5-5`) in `settings.yaml`, and put `ANTHROPIC_API_KEY` in `.env`.

## Notes

- Reuters and AP have no public RSS feeds, so they come through Google News searches. Their article links go through a Google redirect, which is fine for reading.
- Moneycontrol is not included: its RSS feed blocks bots.
- If Claude can't curate a category (usage limit, refusal, timeout), that tab shows "Curation failed this run" and the other categories still publish.
- Posts are flagged on the page (⚠) if they're over 280 characters or contain a hashtag, a link, or a banned hype word (list in `settings.yaml`).
