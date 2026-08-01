# Testing

```bash
make test   # uv run pytest (coverage gate on naming/workflow/spec)
make ci     # lint + mypy + test
```

## Expectations

- Unit tests live in `tests/`; mock GitHub/Cursor — **no live Jira/GitHub/Cursor** in default CI.
- Critical-path coverage gate (`--cov-fail-under=70` on `naming` / `workflow` / `spec`) is enforced in CI and pre-push.
- Prefer table-driven cases for naming heuristics; keep fixtures small and deterministic.
- Hook contract tests (`tests/test_cursor_hooks.py`) must stay green — hooks fail open on missing tools but must emit valid JSON decisions.
- Do not weaken gates (delete tests, skip coverage) to land a change; fix the code or raise coverage.

## Types

```bash
make typecheck   # mypy on naming.py, spec.py, workflow.py
```
