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

DRY_RUN_VALUE="${DRY_RUN:-$(grep -E '^DRY_RUN=' .env 2>/dev/null | tail -1 | cut -d= -f2)}"
DRY=false
case "$(echo "$DRY_RUN_VALUE" | tr '[:upper:]' '[:lower:]')" in true|1) DRY=true ;; esac

HAS_REMOTE=false
git remote get-url origin >/dev/null 2>&1 && HAS_REMOTE=true

if [ "$HAS_REMOTE" = true ]; then
  git pull --rebase --autostash --quiet || echo "warning: git pull failed; continuing with local copy"
fi

if [ "$DRY" = true ]; then
  .venv/bin/python -m newsbot --dry-run
  status=$?
  echo "dry run finished (exit $status); nothing committed"
  exit $status
fi

.venv/bin/python -m newsbot
status=$?

git add site/data
if git diff --cached --quiet; then
  echo "no data changes"
else
  git commit --quiet -m "data: run $(date -u +%FT%TZ)"
  if [ "$HAS_REMOTE" = true ]; then
    git push --quiet || echo "warning: git push failed; will retry next run"
  else
    echo "no git remote yet; committed locally only"
  fi
fi
echo "finished (bot exit $status)"
exit $status
