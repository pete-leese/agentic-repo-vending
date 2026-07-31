# Cursor Cloud Agent notes

## Environment

[`.cursor/environment.json`](../.cursor/environment.json) runs:

```bash
pip install -e '.[dev,cursor]' || pip install -e '.[dev]'
```

Idempotent install; secrets come from the Cloud Agent dashboard. Enable the **Atlassian** tool on the Automation for all Jira board I/O.

## Running the vend CLI

`repo_vendor` does evals + GitHub only. Pass an IssueSnapshot JSON (from Atlassian tools) and apply `result.jira` back via Atlassian tools.

```bash
python -m repo_vendor vend --issue-file /tmp/issue.json --json
python -m repo_vendor rename --issue-file /tmp/issue.json --current-name old-name --comment "Please rename to python-new-name" --json
python -m repo_vendor doctor
```

Full Automation prompt: `docs/automation-setup.md`. Triggered by **Jira webhook → Cursor Automation**.

## Models

- Orchestrator / automation: `composer-2.5`
- Eval judge: `composer-2`
- Deterministic gate always authoritative

## Do not

- Commit `.env` or API keys
- Vend when `repo-vended` is already present (CLI enforces idempotency)
- Skip deterministic checks
- Call Jira REST from the CLI — use Atlassian Automation tools
- Use the global `CURSOR_API_KEY` as the Jira webhook Bearer token (needs the automation-scoped webhook key)
