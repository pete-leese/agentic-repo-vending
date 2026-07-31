#!/usr/bin/env bash
# Publish local template trees as public GitHub template repos under GITHUB_OWNER.
# Never force-pushes. Skips push if remote already has commits unless --update is passed
# with a normal (non-force) push to main.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OWNER="${GITHUB_OWNER:-pete-leese}"
ALLOW_UPDATE=false
if [[ "${1:-}" == "--update" ]]; then
  ALLOW_UPDATE=true
fi

publish_one() {
  local name="$1"
  local src="$ROOT/templates/$name"
  local tmp
  tmp="$(mktemp -d)"
  echo "Publishing $OWNER/$name from $src"
  cp -R "$src/." "$tmp/"
  (
    cd "$tmp"
    git init -b main
    git add .
    git -c user.email="repo-vendor@local" -c user.name="repo-vendor" commit -m "Initial template: $name"
    if gh repo view "$OWNER/$name" >/dev/null 2>&1; then
      echo "Repo $OWNER/$name already exists."
      if [[ "$ALLOW_UPDATE" == "true" ]]; then
        git remote add origin "https://github.com/$OWNER/$name.git"
        git push -u origin main
      else
        echo "Skipping content push (pass --update to push main without force)."
      fi
      gh repo edit "$OWNER/$name" --template || true
    else
      gh repo create "$OWNER/$name" --public --description "Repo vend template: $name" --source=. --remote=origin --push
      gh repo edit "$OWNER/$name" --template
    fi
  )
  rm -rf "$tmp"
  echo "Done: https://github.com/$OWNER/$name"
}

publish_one template-terraform-repo
publish_one template-python-repo
publish_one template-generic-repo
