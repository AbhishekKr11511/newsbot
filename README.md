# News Bot

Every 4 hours this bot:

1. Pulls the last 24 hours of headlines from the feeds in `sources.yaml` (Reuters, AP, BBC, TechCrunch, gaming sites, Indian tech outlets…).
2. Asks Claude Sonnet to pick **0–3 stories per category** (AI & Big Tech, Semiconductors, Gaming, Indian Tech & Startups, World & Markets) and draft a post for each in your voice. Claude skips repeats, gossip, sports and fluff.
3. Publishes everything to a web page: picks with a **Copy** button on top, all articles below, one tab per category.

You read the page, copy the posts you like, and post them to X yourself.

It runs on GitHub Actions and the page is hosted on GitHub Pages, so your Mac can be off.

---

## One-time setup (about 15 minutes)

1. **Create a public repo** on GitHub (e.g. `newsbot`) and push this folder to it:
   ```bash
   git remote add origin https://github.com/<you>/newsbot.git
   git push -u origin main
   ```
2. **Add your API key**: repo → Settings → Secrets and variables → Actions → *Secrets* → New repository secret. Name it `ANTHROPIC_API_KEY` and paste your key from console.anthropic.com.
3. **Turn on dry-run mode**: same page → *Variables* tab → New repository variable. Name it `DRY_RUN`, value `true`.
4. **Turn on Pages**: Settings → Pages → Source: **GitHub Actions**.
5. **First run**: Actions tab → enable workflows if asked → *newsbot* → **Run workflow**.
6. **Review the drafts**: open the run → *Run bot* step. Drafts are printed there, grouped by category. Nothing is published yet.
7. **Go live**: when you like the curation, change the `DRY_RUN` variable to `false` and run the workflow again. Your page will be at `https://<you>.github.io/<repo>/`.

After that it runs on its own every 4 hours. If a run fails (e.g. Claude was unreachable), GitHub emails you, and the page still updates the articles list.

---

## Changing what it covers

All of this is plain text editing. No code changes are needed. Push the change to GitHub and the next run picks it up.

| I want to… | Edit |
|---|---|
| Add or remove a news source | `sources.yaml`: copy a block and change `name`, `url`, `category` |
| Add a new category (e.g. Crypto) | `topics.yaml`: add a block with a new `id`, then point feeds at it in `sources.yaml` |
| Change what counts in a category | `topics.yaml`: edit `covers` / `skip` |
| Change the voice or rules | `prompts/curator.md`. You can add a few of your own past posts at the bottom as examples. |
| Pick more or fewer per category | `topics.yaml`: `max_picks` |
| Run more or less often | `.github/workflows/run.yml`: the `cron` line (`0 */6 * * *` = every 6 hours) |
| Cut cost | `settings.yaml`: lower `per_source_cap`, or set `effort: low` |

After adding a feed, check it works: `python scripts/check_feeds.py`

---

## Running it on your Mac

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # then paste your API key into .env
python -m newsbot --dry-run     # prints drafts, writes nothing
python scripts/check_feeds.py   # checks every feed URL
```

To preview the page with fake data:

```bash
python scripts/sample_data.py site/data
python -m http.server -d site 8000   # open http://localhost:8000
rm site/data/*.json                  # clean up before committing
```

Run the tests: `pytest`

---

## Cost

Each run makes one Claude Sonnet call per category (5 today), 6 runs a day. Sonnet 5.5 costs $2 per million input tokens and $10 per million output tokens. A typical call sends ~60–120 headlines. Rough estimate: **$1–2 a day**. Check your real usage at console.anthropic.com after the first day. The cheapest levers are `per_source_cap`, `effort: low`, or running every 6 hours.

## Notes

- Reuters and AP have no public RSS feeds, so they come through Google News searches. Their article links go through a Google redirect, which is fine for reading.
- Moneycontrol is not included: its RSS feed blocks bots.
- If Claude's safety filter declines a category's request, the API automatically retries it on another model (`fallbacks: "default"`). If that fails too, that tab shows "Curation failed this run".
- Posts are flagged on the page (⚠) if they're over 280 characters or contain a hashtag, a link, or a banned hype word (list in `settings.yaml`).
