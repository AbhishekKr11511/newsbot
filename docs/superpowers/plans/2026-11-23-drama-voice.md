# Drama Voice and Topic Mix (v1.3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Three categories (gaming, tech-ai, trending), a Pirat_Nation-style voice prompt, six new feeds, and the article image first on the page.

**Spec:** `docs/superpowers/specs/2026-11-17-news-curation-bot-design.md`, section "v1.3 change".

## Global Constraints
- Category ids: `gaming` (max 3), `tech-ai` (max 3), `trending` (max 1), in that order.
- Source remap: `ai-bigtech` → `tech-ai`; `semis`, `india-tech` and `world-markets` → `trending`. New: The Verge and Windows Central → `tech-ai`; 9to5Mac → `tech-ai`; Dexerto, VGC and Insider Gaming → `gaming`.
- Posts: max 280 chars, 2–3 short lines separated by `\n`, no sarcasm or "I", no hashtags or links, facts never invented.

## Review Focus
1. **Old `picks.json` entries reference removed category ids** (ai-bigtech etc.). The page must still render them under "All", with no crash. Task 3 check.
2. **A newline inside a post.** The page must keep the line breaks (`white-space: pre-wrap` already) and Copy must copy them. Task 3 check.
3. **Posts with line breaks counted against 280.** `check_post` counts `\n` as a character, like X does. Task 1 test.

### Task 1: Categories, sources, tests
- Rewrite `topics.yaml`; remap and extend `sources.yaml`. Update `tests/test_config.py` (ids `["gaming","tech-ai","trending"]`, `max_picks` `[3,3,1]`) and `tests/test_run.py` (SOURCES categories → `trending`, `gaming`, `tech-ai`; failure test uses "Trending"; empty-category test uses a category with no feeds). Add `test_post_newlines_count_toward_limit` in `tests/test_checks.py`.
- `pytest -q` green; `python scripts/check_feeds.py` all OK. Commit.

### Task 2: Voice prompt
- Rewrite `prompts/curator.md` for the bulletin voice, with three short example posts in the style (not copied from Pirat_Nation). Keep the placeholders and the card_text section. `test_real_prompt_file_has_no_leftover_placeholders` stays green. Commit.

### Task 3: Page: image first
- In `cardBlock`, when `image_url` is set, show the image large (full width, 16:9, cover) before the stat card, with "Open original image" first. CSS `.hero`. Check with sample data (an old category id in sample picks), then commit.

### Task 4: Dry run and review
- `python -m newsbot --dry-run` in the Documents copy, then show the new drafts next to the last live drafts. The owner approves before the scheduled copy picks it up. (It pulls on every run, so pushing this makes it live. Set `DRY_RUN=true` in `~/code/newsbot/.env` before pushing, and remove it after approval.)
