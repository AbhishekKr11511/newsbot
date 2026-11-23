#!/bin/bash
# Run the bot once, then commit + push site/data so GitHub Pages updates.
# Called by launchd every 4 hours (see scripts/install_schedule.sh). Safe to run by hand.
set -uo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO" || exit 1
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
mkdir -p logs
exec >>"logs/run.log" 2>&1
echo "===== $(date '+%Y-%m-%d %H:%M:%S') ====="

# macOS notification (tests override with NEWSBOT_NOTIFY_CMD).
notify() {
  if [ -n "${NEWSBOT_NOTIFY_CMD:-}" ]; then
    "$NEWSBOT_NOTIFY_CMD" "$1" "$2"
  else
    osascript -e "display notification \"$2\" with title \"$1\"" >/dev/null 2>&1 || true
  fi
}

BOT_OUT="$(mktemp)"
trap 'rm -f "$BOT_OUT"' EXIT
run_bot() {
  .venv/bin/python -m newsbot "$@" 2>&1 | tee "$BOT_OUT"
  return "${PIPESTATUS[0]}"
}
drafts() { grep -c '^  • ' "$BOT_OUT" || true; }

DRY_RUN_VALUE="${DRY_RUN:-$(grep -E '^DRY_RUN=' .env 2>/dev/null | tail -1 | cut -d= -f2)}"
DRY=false
case "$(echo "$DRY_RUN_VALUE" | tr '[:upper:]' '[:lower:]')" in true|1) DRY=true ;; esac

HAS_REMOTE=false
git remote get-url origin >/dev/null 2>&1 && HAS_REMOTE=true

BRANCH="$(git branch --show-current)"

if [ "$HAS_REMOTE" = true ] && [ "$DRY" = false ]; then
  if ! git pull --rebase --autostash --quiet; then
    git rebase --abort >/dev/null 2>&1 || true
    echo "git pull failed; skipping this run so nothing is committed on top of a conflict"
    notify "News Bot: run failed" "git pull failed. See logs/run.log"
    exit 1
  fi
fi

if [ "$DRY" = true ]; then
  run_bot --dry-run
  status=$?
  echo "dry run finished (exit $status); nothing committed"
  if [ $status -eq 0 ]; then
    notify "News Bot" "Dry run: $(drafts) drafts (nothing published)"
  else
    notify "News Bot: run failed" "Dry run had errors ($(drafts) drafts). See logs/run.log"
  fi
  exit $status
fi

run_bot
status=$?

if [ "$BRANCH" != "main" ]; then
  echo "not on main (on '$BRANCH'); data written locally but not committed"
  notify "News Bot" "$(drafts) drafts written locally (not on main, not published)"
  exit $status
fi

git add site/data
if git diff --cached --quiet -- site/data; then
  echo "no data changes"
else
  # Commit only site/data, even if other changes happen to be staged.
  git commit --quiet -m "data: run $(date -u +%FT%TZ)" -- site/data
  if [ "$HAS_REMOTE" = true ]; then
    git push --quiet || echo "warning: git push failed; will retry next run"
  else
    echo "no git remote yet; committed locally only"
  fi
fi
echo "finished (bot exit $status)"
if [ $status -eq 0 ]; then
  notify "News Bot" "$(drafts) drafts ready"
else
  notify "News Bot: run failed" "Some categories failed ($(drafts) drafts). See logs/run.log"
fi
exit $status
