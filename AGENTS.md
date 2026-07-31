# Cursor Cloud Agent notes

## Environment

[`.cursor/environment.json`](../.cursor/environment.json) runs:

```bash
pip install -e '.[dev,cursor]' || pip install -e '.[dev]'
```

Idempotent install; secrets come from the Cloud Agent dashboard.

## Running the vend CLI

```bash
python -m repo_vendor scan
python -m repo_vendor vend --issue KAN-123
python -m repo_vendor rename --issue KAN-123 --current-name old-name --comment "Please rename to python-new-name"
python -m repo_vendor doctor
```

Prefer **scan** from a scheduled Cloud Automation when you want zero Jira webhook setup.

## Models

- Orchestrator / automation: `composer-2.5`
- Eval judge: `composer-2`
- Deterministic gate always authoritative

## Do not

- Commit `.env` or API keys
- Vend when `repo-vended` is already present (CLI enforces idempotency)
- Skip deterministic checks
