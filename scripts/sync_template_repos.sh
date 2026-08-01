#!/usr/bin/env bash
# Sync local templates/<name>/ into pete-leese/<name> via PR (squash-merge).
# Usage: scripts/sync_template_repos.sh [template-name ...]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OWNER="${GITHUB_OWNER:-pete-leese}"
BRANCH="chore/template-sync-$(date +%Y%m%d%H%M%S)"

NAMES=("$@")
if [[ ${#NAMES[@]} -eq 0 ]]; then
  NAMES=(template-terraform-repo template-python-repo template-generic-repo)
fi

sync_one() {
  local name="$1"
  local src="$ROOT/templates/$name"
  local tmp
  tmp="$(mktemp -d)"
  echo "=== Syncing $OWNER/$name ==="
  gh repo view "$OWNER/$name" >/dev/null
  git clone --depth 1 "https://github.com/$OWNER/$name.git" "$tmp/repo"
  (
    cd "$tmp/repo"
    git checkout -b "$BRANCH"
    # Replace tree with local scaffold (keep .git)
    find . -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
    cp -R "$src"/. .
    git add -A
    if git diff --cached --quiet; then
      echo "No changes for $name"
      exit 0
    fi
    git -c user.email="repo-vendor@local" -c user.name="repo-vendor" \
      commit -m "Sync template scaffold: placeholders, terraform-docs, no nested modules"
    git push -u origin HEAD
    url="$(gh pr create \
      --title "Sync template: placeholders + terraform-docs" \
      --body "$(cat <<EOF
## Summary
- README uses \`{{REPO_NAME}}\` / \`{{DESCRIPTION}}\` / … placeholders for vend substitution
- Terraform: remove nested \`modules/\`, root \`.tf\` stubs, terraform-docs pre-commit + Action that merges docs PRs to main

## Test plan
- [ ] README placeholders present
- [ ] Terraform validate workflow runs at repo root
- [ ] terraform-docs workflow present
EOF
)" \
      --base main \
      --head "$BRANCH")"
    echo "PR: $url"
    gh pr merge --squash --delete-branch
    gh repo edit "$OWNER/$name" --template || true
    echo "Merged: https://github.com/$OWNER/$name"
  )
  rm -rf "$tmp"
}

for n in "${NAMES[@]}"; do
  sync_one "$n"
done
