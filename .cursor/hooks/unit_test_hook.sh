#!/usr/bin/env bash
# Run pytest (with coverage gate from pyproject) before git commit / push.
set -uo pipefail

EVENT="$(cat)"

run_pytest() {
  if command -v uv >/dev/null 2>&1; then
    uv run pytest >&2
    return $?
  fi
  if command -v pytest >/dev/null 2>&1; then
    pytest >&2
    return $?
  fi
  echo "unit_test_hook: pytest/uv not found — allowing (fail open)" >&2
  return 0
}

if ! run_pytest; then
  printf '{"permission":"deny","user_message":"pytest failed — fix tests/coverage before commit/push","agent_message":"unit_test_hook: pytest failed"}\n'
  exit 0
fi

printf '{"permission":"allow"}\n'
exit 0
