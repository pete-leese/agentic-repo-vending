# Cursor Cloud Agent notes

## Environment

[`.cursor/environment.json`](.cursor/environment.json) installs **uv** and runs `uv sync --group dev --extra cursor`.

Enable the **Atlassian** tool. Secrets: `GITHUB_TOKEN`, `CURSOR_API_KEY`.

## Conventions (SSOT)

| Doc | Purpose |
|-----|---------|
| [`docs/conventions/style.md`](docs/conventions/style.md) | Lint / format |
| [`docs/conventions/testing.md`](docs/conventions/testing.md) | Tests / coverage / mypy |
| [`docs/conventions/pr.md`](docs/conventions/pr.md) | PR expectations |
| [`rules/naming.md`](rules/naming.md) | Naming + Keyword Approval HITL |
| [`repo-vend.yaml`](repo-vend.yaml) | Board, keywords, templates, models |
| [`evals/`](evals/) | Extract + judge prompts |
| [`requests/`](requests/) | Spec Request YAML (via PR) |
| [`SECURITY.md`](SECURITY.md) | Secrets + reporting |

Skills: **setup-repo-vend-automation**, **generate-jira-automation**. Customize: [`docs/customizing.md`](docs/customizing.md).

## CLI

```bash
make sync doctor
uv run python -m repo_vendor propose --issue-file /tmp/issue.json --json
uv run python -m repo_vendor vend --issue-file /tmp/issue.json --approval-comment "lgtm" --json
```

Automation prompt: `docs/automation-setup.md`. Local gates: `make ci`.

## Do not

- Commit `.env` or API keys
- Create when `repo-vended` is present
- Skip deterministic checks or weaken coverage gates
- Support post-create rename
- Call Jira REST from the CLI
- Use global `CURSOR_API_KEY` as the webhook Bearer token
