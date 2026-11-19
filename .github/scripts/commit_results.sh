#!/usr/bin/env bash
# Commits the bot's output files back to the repository so you can view them
# on GitHub (e.g. on your phone). Usage: commit_results.sh "message"
set -u
MESSAGE="${1:-Bot update}"

git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

# Only add files that exist (a brand-new repo won't have all of them yet)
for f in trades.csv performance.csv summary.md performance_chart.png \
         logs state data backtest; do
  [ -e "$f" ] && git add "$f"
done

if git diff --cached --quiet; then
  echo "Nothing new to commit."
  exit 0
fi

git commit -m "$MESSAGE ($(date -u +'%Y-%m-%d %H:%M') UTC)"

# Push, retrying in case another commit landed in the meantime
for attempt in 1 2 3 4; do
  if git pull --rebase --quiet && git push --quiet; then
    echo "Pushed results."
    exit 0
  fi
  echo "Push failed (attempt $attempt); retrying..."
  sleep $((attempt * 5))
done
echo "Could not push results."
exit 1
