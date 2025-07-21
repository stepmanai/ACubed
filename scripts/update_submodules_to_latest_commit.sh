#!/bin/bash
set -e

uv run git submodule foreach '
  echo "🔄 Updating $name"
  git checkout main || true
  git fetch origin main
  git rebase origin/main || true
'

uv run git add .
uv run git commit -m "Update submodules to latest commits (rebase)"
