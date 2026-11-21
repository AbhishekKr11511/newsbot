# Stat Cards and Article Images (v1.2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Each pick gets a Claude-written `card_text` and the article's feed image link. The page draws a downloadable 1200×675 stat card and links the original image.

**Architecture:** Data changes in Python (`fetch.py`, `curate.py`, `checks.py`, `run.py`, `store.py`/`config.py` for meta). The card is drawn in `site/app.js` on `<canvas>`.

**Tech Stack:** Python 3.12, feedparser, vanilla JS canvas.

**Spec:** `docs/superpowers/specs/2026-11-17-news-curation-bot-design.md`, section "v1.2 change".

## Global Constraints

- `card_text` is at most 60 chars, with no hashtags or links. Flag `card_too_long` over 60.
- `image_url`: http(s) only, else `null`. Never downloaded or re-hosted.
- Card: 1200×675 PNG, dark background, `card_text` wrapped to fit, source · date small, `card_handle` (+ optional `card_tagline`) in a corner.
- `settings.yaml` gains `card_handle: "@yourhandle"` and `card_tagline: ""`. Both go into `meta.json` as `card: {handle, tagline}`.
- Old picks with no `card_text` or `image_url` must still render (card falls back to the title).
- All feed text is drawn with canvas `fillText` or `textContent`; never `innerHTML`.

## Review Focus

1. **Picks from before v1.2 (no `card_text`)**: the card falls back to the title, with no JS error. Task 3 manual check with old-shape data.
2. **A very long `card_text` or title**: text wraps and shrinks to stay inside the card. Task 3 manual check with a 200-char title.
3. **A feed image URL that's `javascript:` or relative**: becomes `null`. Task 1 `test_image_url_rejects_non_http`.
4. **A canvas tainted by a cross-origin image**: avoided by never drawing the article image on the canvas (thumbnail is a plain `<img>`). Task 3 check that Download works.
5. **Claude omits `card_text`**: the schema requires it. If the CLI returns it empty, the pick is kept with flag `card_empty`. Task 2 `test_card_flags`.

---

### Task 1: Feed image URL

**Files:** Modify `newsbot/fetch.py`, `tests/test_fetch.py`, `tests/fixtures/rss_basic.xml` (add `media:content` to item 1, an `<img>` in item 2's description, and nothing on item 3), and add a fixture item with `javascript:` media.

**Interfaces:** `Article` gains `image_url: str | None = None` (last field, default `None`, so old JSON loads). `_entry_image(entry) -> str | None` checks `media_content`, `media_thumbnail`, image enclosures, then the first `<img src>` in the raw summary, and accepts only absolute http(s) URLs.

Tests: `test_image_from_media_content`, `test_image_from_summary_img`, `test_no_image_is_none`, `test_image_url_rejects_non_http`, `test_old_article_json_without_image_loads`.

- [ ] Tests fail → implement → `pytest -q` green → commit `feat: store feed image URL per article`.

### Task 2: card_text from Claude, flags, pick fields, meta

**Files:** Modify `newsbot/curate.py` (`Pick.card_text: str`), `prompts/curator.md` (card rule), `newsbot/checks.py` (`check_card(text) -> list[str]`: `card_empty`, `card_too_long` at 60, `card_hashtag`, `card_link`), `newsbot/run.py` (pick dict gains `card_text`, `image_url`; flags merge post and card flags), `newsbot/config.py` (`Settings.card_handle: str = "@yourhandle"`, `card_tagline: str = ""`), `newsbot/store.py` (`save_meta(..., card: dict | None = None)` writes `card`), `settings.yaml`. Tests across `test_checks.py`, `test_run.py`, `test_store.py`, `test_config.py`, `test_claude_code.py`.

Tests: `test_card_flags`; `test_pick_has_card_text_and_image_url` (run with the fake curator returning `card_text`); `test_meta_has_card_settings`; `test_load_settings_card_defaults`; update the fake picks to include `card_text`; `test_cli_schema_requires_card_text`.

- [ ] Tests fail → implement → `pytest -q` green → commit `feat: card_text per pick and card settings`.

### Task 3: Page draws cards

**Files:** Modify `site/app.js`, `site/style.css`, `scripts/sample_data.py` (add `card_text`, `image_url`, one old-shape pick, and one 200-char title).

- `drawCard(canvas, {text, source, date, handle, tagline})`: 1200×675, background `#0f0f10`, a 6 px accent bar, the main text in bold system font starting at 92 px and shrinking (down to 44 px) until the wrapped lines fit in ~1040×380, source · date at 30 px muted, handle bottom-right and tagline bottom-left at 28 px.
- Each pick card gets a `<canvas>` preview (CSS width 100%), a **Download card** button (`canvas.toBlob` → object URL → `<a download="newsbot-<yyyy-mm-dd>-<slug>.png">`), and, if `image_url` is set, a thumbnail `<img loading="lazy" referrerpolicy="no-referrer">` plus an **Open original image** link.
- [ ] Generate sample data, serve it, and screenshot with headless Chrome. Check: cards render, a long title wraps inside, an old pick falls back to its title, there are no `<img>` elements from feed titles, and Download produces a PNG (verify `toBlob` in headless via `--dump-dom` with an injected status, or manually in a real browser).
- [ ] Commit `feat: stat cards and article images on the page`.

### Task 4: Live check and docs

- [ ] One real non-dry run (local only, no commit), then serve and open the page for the owner. Update the README (cards, handle setting), `PROGRESS.md` (checklist, log) and `CLAUDE.md` (layout line for cards). Commit `docs: stat cards`.
