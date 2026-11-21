# Claude Code Backend (v1.1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run curation through `claude -p` on the owner's Pro plan, track tokens per category, compare Haiku against Sonnet on the same headlines, and move scheduling to the Mac.

**Architecture:** `curate.py` gets a pluggable "curator": a callable `(system_prompt, user_message) -> (picks, usage)`. One curator shells out to the Claude Code CLI; the other is the existing API path. `run.py` is split into a fetch stage and a curate stage, so the comparison script can reuse both. A shell script plus a launchd plist runs the bot on the Mac. GitHub Actions only deploys Pages.

**Tech Stack:** Python 3.12, `subprocess`, Claude Code CLI 2.1.x, launchd, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-11-17-news-curation-bot-design.md`, section "v1.1 change".

## Global Constraints

- CLI call, exactly: `claude -p --model <model> --system-prompt <prompt> --json-schema <json> --tools "" --strict-mcp-config --setting-sources "" --no-session-persistence --output-format json`, with the user message on stdin. Timeout 300 s.
- `settings.yaml`: `backend: claude-code` (default) or `api`. `model: haiku` (default) or `sonnet` for claude-code. A full model id is used for api.
- Usage record keys: `model`, `input_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`, `output_tokens`, `thinking_tokens`, `cost_usd_equiv`.
- Any CLI failure (missing binary, non-zero exit, `is_error: true`, timeout, bad JSON, schema mismatch) raises `CurationError`. One category fails; the run continues.
- The comparison script never writes to `site/data`.
- The schedule runs at 00, 04, 08, 12, 16 and 20 local time via `StartCalendarInterval`, which catches up after sleep.

## Review Focus

1. **`claude` not on PATH under launchd** (launchd has a minimal PATH). The script must add `~/.local/bin` and `/opt/homebrew/bin`. Pinned by Task 4's manual check (`env -i` run).
2. **Pro usage limit hit mid-run.** The CLI exits non-zero or returns `is_error`, the category becomes `curation_failed`, and the remaining categories still run. Pinned by Task 1's `test_cli_is_error_raises`.
3. **The CLI returns prose instead of `structured_output`** (e.g. a refusal). Pinned by Task 1's `test_cli_missing_structured_output_raises`.
4. **Nothing changed** (no new data). The publish script must not create an empty commit or fail. Pinned by Task 4's manual check.
5. **Usage missing from the CLI output** (older CLI). Token fields default to 0 and the run doesn't crash. Pinned by Task 1's `test_usage_defaults_to_zero`.

---

### Task 1: Claude Code curator and usage

**Files:** Modify `newsbot/curate.py`, `newsbot/config.py`, `settings.yaml`. Test: `tests/test_curate.py`, `tests/test_config.py`

**Interfaces:**
- `Settings` gains `backend: str = "claude-code"`. `settings.yaml` gets `backend: claude-code` and `model: haiku`.
- `Curator = Callable[[str, str], tuple[list[dict], dict]]`
- `claude_code_curator(settings: Settings, runner=subprocess.run, claude_bin: str = "claude") -> Curator`
- `api_curator(client, settings: Settings) -> Curator`, which wraps the existing `curate_category` (keep that function; its usage comes from `response.usage`, or zeros)
- `make_curator(settings: Settings, model_override: str | None = None) -> Curator`. For `api` it builds `anthropic.Anthropic()`.
- `empty_usage(model: str) -> dict`

Tests (with a fake `runner` returning `SimpleNamespace(returncode, stdout, stderr)`):
```python
def test_cli_builds_expected_command(): ...        # argv contains "-p", "--model","haiku", "--tools","", "--json-schema", "--output-format","json"; input == user message
def test_cli_parses_structured_output_and_usage(): # picks list, usage["output_tokens"]==348, usage["thinking_tokens"]==190, usage["model"]=="claude-haiku-5-5"
def test_cli_is_error_raises(): ...                # {"is_error": true, "result": "usage limit"} -> CurationError
def test_cli_nonzero_exit_raises(): ...
def test_cli_missing_structured_output_raises(): ...
def test_cli_timeout_raises(): ...                 # runner raises subprocess.TimeoutExpired
def test_cli_missing_binary_raises(): ...          # runner raises FileNotFoundError
def test_usage_defaults_to_zero(): ...             # output has no "usage" -> all token fields 0
def test_make_curator_model_override(): ...        # override "sonnet" reaches argv
def test_load_settings_backend(): ...              # repo settings.yaml -> backend "claude-code", model "haiku"
```

- [ ] Write the tests, then run `pytest tests/test_curate.py tests/test_config.py -q`. Expected: FAIL.
- [ ] Implement them, then run the same command. Expected: PASS. Commit `feat: Claude Code curator with token usage`.

### Task 2: Run uses curators, records tokens, `--model` flag

**Files:** Modify `newsbot/run.py`, `newsbot/__main__.py`, `tests/test_run.py`, `tests/test_main.py`

**Interfaces:**
- `@dataclass Context(categories, settings, template, articles: list[Article], fetched: list[Article], feed_errors: list[str], runs: list[dict], previous: list[dict])`
- `prepare(paths: Paths, now: datetime, http_get=default_get) -> Context`
- `curate_all(ctx: Context, curator: Curator, now: datetime) -> dict[str, dict]`. Each category dict gains `usage` (or `None` when Claude isn't called).
- `total_usage(result: dict[str, dict]) -> dict` sums the token fields.
- `run(paths, now, dry_run, curator, http_get=default_get, out=sys.stdout) -> int`. The run record gains `usage_total`. The summary prints tokens per category and in total.
- CLI: `--model haiku|sonnet` overrides settings. With the claude-code backend, the API-key check is replaced by `shutil.which("claude")`; if it's missing, print a message and exit 2. The api backend keeps the key check.

Tests: update `tests/test_run.py` to pass a fake curator (a function) instead of `FakeClient`, keeping all existing assertions. Add:
```python
def test_usage_recorded_per_category_and_total(root): ...  # picks.json category usage present; usage_total.output_tokens == sum
def test_summary_prints_tokens(root): ...                  # stdout contains "tokens"
```
Update `tests/test_main.py`: when `claude` is missing (monkeypatch `shutil.which` → `None`), exit 2 with "claude" in stderr. When the backend is api and the key is missing, exit 2.

- [ ] Write the tests and see them fail. Implement. Run the full `pytest -q`: PASS. Commit `feat: run with pluggable curator and token tracking`.

### Task 3: Model comparison script

**Files:** Create `scripts/compare_models.py`, `tests/test_compare.py`

**Interfaces:**
- `compare(paths: Paths, now: datetime, curators: dict[str, Curator], http_get=default_get) -> str` returns markdown. It calls `prepare` once, then `curate_all` per model on the same `Context`.
- `main()`: models default to `haiku sonnet` (`--models` to change), writes `compare-<YYYY-MM-DD-HHMM>.md` in the repo root (gitignored), and prints the path.
- Markdown layout: a token table first (model | input | cache write | cache read | output | thinking | ≈$ equiv), then per category `### <name>` with a `**<model>**` list of drafts for each model.

Tests:
```python
def test_compare_runs_same_candidates_through_each_model(root): ...  # both fake curators receive identical user messages per category
def test_compare_markdown_has_table_and_drafts(root): ...            # "| haiku |" and "| sonnet |" rows; both drafts present
def test_compare_writes_nothing_to_site_data(root): ...
```
- [ ] Write the tests and see them fail. Implement. `pytest -q`: PASS. Add `compare-*.md` to `.gitignore`. Commit `feat: Haiku vs Sonnet comparison script`.

### Task 4: Mac schedule and Pages-only workflow

**Files:** Create `scripts/run_and_publish.sh`, `scripts/com.newsbot.run.plist.template`, `scripts/install_schedule.sh`. Modify `.github/workflows/run.yml`.

- `run_and_publish.sh`:
  - `set -euo pipefail`, cd to the repo root, set `PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"`, and append all output to `logs/run.log` with a timestamp.
  - `git pull --rebase --autostash`, then `.venv/bin/python -m newsbot` (keeping its exit code). If `DRY_RUN` in `.env` is not true: `git add site/data`, commit only if anything is staged, then `git push`. Exit with the bot's exit code.
- The plist template uses `StartCalendarInterval` for hours 0, 4, 8, 12, 16 and 20 (minute 0), `ProgramArguments` running `/bin/bash <repo>/scripts/run_and_publish.sh`, and a `__REPO__` placeholder.
- `install_schedule.sh` fills the placeholder, copies the plist to `~/Library/LaunchAgents/com.newsbot.run.plist`, and runs `launchctl bootout` (ignoring errors) then `launchctl bootstrap gui/$(id -u)`. The owner runs it; Claude does not.
- Workflow: remove the bot-run steps. Trigger on `push` to `main` with paths `site/**`, plus `workflow_dispatch`. Steps: checkout, upload-pages-artifact (`site`), deploy-pages.
- `logs/` goes in `.gitignore`.

- [ ] `bash -n` both scripts. Run `plutil -lint` on the template after substituting a path. Validate the workflow YAML.
- [ ] Manual check: `DRY_RUN=true env -i HOME="$HOME" bash scripts/run_and_publish.sh` finds `claude` under a minimal environment. It needs no git remote in dry-run mode (skip the pull when there's no remote). A second run with no changes makes no empty commit.
- [ ] Commit `feat: Mac launchd schedule and Pages-only workflow`.

### Task 5: CLAUDE.md, PROGRESS.md, README

**Files:** Create `CLAUDE.md`, `PROGRESS.md`. Modify `README.md`.
- `CLAUDE.md`: what the project is, the layout (one line per module), the commands (tests, dry run, compare, feed check, preview), the conventions (TDD, config-not-code, textContent-only on the page, never commit `.env` or `site/data` sample data), where the spec, plans and progress live, and "update PROGRESS.md when finishing work".
- `PROGRESS.md`: status, a done checklist (v1 tasks, v1.1 tasks), next steps for the owner (dry run, compare, install schedule, GitHub setup), open decisions (Haiku vs Sonnet, GitHub-token route), known minor issues (the review's deferred minors), and a dated log.
- README: replace the API setup with the Pro/Claude Code setup, the comparison steps, schedule install/uninstall, and an updated cost section (₹0 extra, uses Pro limits).
- [ ] Write them. `pytest -q` stays green. Commit `docs: CLAUDE.md, PROGRESS.md, README for Claude Code backend`.

### Task 6: Live comparison (one real run)

- [ ] Run `python scripts/compare_models.py` once on real feeds with the owner's Pro login. Expected: a `compare-*.md` with drafts from both models and a token table. Record the token totals in PROGRESS.md and summarise them for the owner.
