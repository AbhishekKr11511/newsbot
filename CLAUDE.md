# News Bot

A bot that every 4 hours pulls headlines from RSS feeds, has Claude pick 0–3 stories per category and draft X posts in the owner's voice (dry, slightly skeptical, no hype, no hashtags, no links), and publishes everything to a static page on GitHub Pages. The owner copies the drafts and posts them to X by hand. Auto-posting via the X API comes later.

Curation runs through the **Claude Code CLI on the owner's Pro plan** (`claude -p`), not the paid API. The API path still exists behind `backend: api` in `settings.yaml`.

## Layout

- `newsbot/config.py`: loads `sources.yaml`, `topics.yaml`, `settings.yaml` into dataclasses
- `newsbot/fetch.py`: feed download (5 MB / 30 s cap), parsing, URL canonicalization, 24h window
- `newsbot/curate.py`: candidate selection, prompt building, curators (`claude_code_curator`, `api_curator`, `make_curator`), token usage
- `newsbot/checks.py`: post flags (length, hashtag, link, hype words) and pick validation
- `newsbot/store.py`: `site/data/*.json` read/write/merge/prune (atomic writes)
- `newsbot/run.py`: `prepare` → `curate_all` → summary → save; `python -m newsbot`
- `prompts/curator.md`: the system prompt / voice (owner-editable)
- `site/`: static page (`index.html`, `app.js`, `style.css`) reading `site/data/*.json`; `drawCard` in `app.js` draws the 1200×675 stat cards on canvas (never draw cross-origin article images onto the canvas, because that blocks Download)
- `scripts/`: `check_feeds.py`, `compare_models.py`, `sample_data.py`, `run_and_publish.sh`, `install_schedule.sh`
- `docs/superpowers/specs/`: design; `docs/superpowers/plans/`: implementation plans

## Commands

```bash
source .venv/bin/activate
pytest -q                                  # tests (must stay green)
python -m newsbot --dry-run                # one run, print drafts + tokens, write nothing
python -m newsbot --dry-run --model sonnet # same, other model
python scripts/compare_models.py           # Haiku vs Sonnet on the same headlines -> compare-*.md
python scripts/check_feeds.py              # every feed URL OK?
python scripts/sample_data.py site/data && python -m http.server -d site 8000   # preview page
bash scripts/run_and_publish.sh            # what the schedule runs (run + commit + push site/data)
```

## Conventions

- TDD: write the failing test first, watch it fail, then implement. Run the full `pytest -q` before committing.
- Config, not code: sources, categories, voice and model choice live in YAML and Markdown files the owner edits.
- The page renders feed text with `textContent` only. Never use `innerHTML` with feed data. Links go through `safeHref`.
- One failing feed or category must never stop a run; failures become `curation_failed` and other categories still publish.
- Never commit `.env`, `logs/`, `compare-*.md`, or sample data in `site/data/` (only real run output is committed, by the schedule).
- Don't spoof User-Agents or scrape sites that block bots; use feeds that allow it.
- Commits end with the Co-Authored-By line used in the history.

## Tracking

- Update `PROGRESS.md` when you finish a piece of work: tick the checklist, add a dated line to the log, and adjust "Next steps".
