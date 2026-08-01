# Style

Lint and format with **ruff** (see `[tool.ruff]` in `pyproject.toml`).

```bash
make lint      # ruff check
make format    # ruff format (write)
```

- Python ≥ 3.11, package under `src/repo_vendor/`.
- Prefer typed public functions on the critical path (`naming`, `spec`, `workflow`).
- Conventional commits; no AI attribution footers.
- Do not commit generated Jira import files that contain real webhook URLs or Bearer tokens — placeholders only.
