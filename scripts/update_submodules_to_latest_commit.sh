#!/bin/bash
set -e

echo "🔁 Stashing, updating, and rebasing all submodules..."

uv run git submodule foreach '
  echo "🔄 Entering $name"

  # Stash any local changes (including untracked files)
  git stash --include-untracked || echo "  ⚠️ Nothing to stash"

  # Ensure we’re on main and fetch the latest commits
  git checkout main || true
  git fetch origin main

  # Rebase onto remote main
  git rebase origin/main || echo "  ⚠️ Rebase failed or unnecessary"

  # Reapply stashed changes
  git stash pop || echo "  ⚠️ Nothing to pop or already clean"
'

echo "✅ Submodules updated. Committing submodule pointer changes..."
echo "🚀 Done."
