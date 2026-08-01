#!/usr/bin/env bash
# Deny writes to secret paths and a small set of dangerous shell patterns.
# Fail-open on parse errors so a hook bug never wedges the agent.
set -uo pipefail

EVENT="$(cat)"
MODE="${1:-}"

json_field() {
  # Prefer python3 (always available in this repo's Cloud env); fail open if missing.
  if command -v python3 >/dev/null 2>&1; then
    python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get(sys.argv[1],"") or "")' "$1" <<<"$EVENT" 2>/dev/null || true
    return
  fi
  [[ "$EVENT" =~ \"$1\"[[:space:]]*:[[:space:]]*\"([^\"]*)\" ]] && printf '%s' "${BASH_REMATCH[1]}"
}

deny() {
  local msg="$1"
  printf '{"permission":"deny","user_message":%s,"agent_message":%s}\n' \
    "$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$msg")" \
    "$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$msg")"
  exit 0
}

if [[ "$MODE" == "--tool-edit" ]]; then
  TARGET="$(json_field file_path)"
  [[ -z "$TARGET" ]] && TARGET="$(json_field path)"
  case "$TARGET" in
    */.env|*/.env.*|.env|.env.*|*/secrets/*|"$HOME"/.ssh/*|*/credentials.json|*/.aws/credentials)
      deny "refused write to sensitive path: ${TARGET}"
      ;;
  esac
  printf '{"permission":"allow"}\n'
  exit 0
fi

CMD="$(json_field command)"
case "$CMD" in
  *"rm -rf /"*|*"rm -rf /*"*|*"git push --force"*|*"git push -f "*|*"git push --force-with-lease origin main"*|*"git push --force-with-lease origin master"*)
    deny "refused dangerous shell command"
    ;;
esac
# Block redirecting secrets into the tree
if [[ "$CMD" =~ (curl|wget).*(>\s*\.?/?\.env|>\s*\.?/?secrets/) ]]; then
  deny "refused writing secrets via shell redirect"
fi

printf '{"permission":"allow"}\n'
exit 0
