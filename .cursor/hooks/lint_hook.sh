#!/usr/bin/env bash
# Run ruff before git commit / push. Gate failures deny; tool missing fails open.
set -uo pipefail

EVENT="$(cat)"

run_ruff() {
  if command -v uv >/dev/null 2>&1; then
    uv run ruff check . >&2 && uv run ruff format --check . >&2
    return $?
  fi
  if command -v ruff >/dev/null 2>&1; then
    ruff check . >&2 && ruff format --check . >&2
    return $?
  fi
  echo "lint_hook: ruff/uv not found — allowing (fail open)" >&2
  return 0
}

if ! run_ruff; then
  printf '{"permission":"deny","user_message":"ruff failed — fix lint/format before commit/push","agent_message":"lint_hook: ruff check/format failed"}\n'
  exit 0
fi

printf '{"permission":"allow"}\n'
exit 0
