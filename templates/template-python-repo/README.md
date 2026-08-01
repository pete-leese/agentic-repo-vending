# {{REPO_NAME}}

{{DESCRIPTION}}

## Origin

- **Jira:** `{{ISSUE_KEY}}`
- **Summary:** {{SUMMARY}}
- **Created from template:** `{{TEMPLATE}}`
- **Repository:** {{REPO_URL}}

## Layout

- `src/` — Python package
- `tests/` — pytest
- `.github/workflows/python.yml` — ruff + pytest
- `.pre-commit-config.yaml` — local guardrails

## Getting started

```bash
pip install -e '.[dev]'
pytest
```

## Contributing

Direct pushes to `main` should be blocked — open a pull request.
