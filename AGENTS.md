# Cursor Cloud Agent notes

## Environment

[`.cursor/environment.json`](.cursor/environment.json) runs `pip install -e '.[dev,cursor]'` (fallback without cursor extra).

Enable the **Atlassian** tool. Secrets: `GITHUB_TOKEN`, `CURSOR_API_KEY`.

## Rules and evals

| Path | Purpose |
|------|---------|
| [`rules/naming.md`](rules/naming.md) | Naming, Keyword Approval, two-phase HITL |
| [`repo-vend.yaml`](repo-vend.yaml) | Board URL, approval keywords, template map |
| [`evals/extract-intent.json`](evals/extract-intent.json) | Orchestrator extract |
| [`evals/judge-naming.json`](evals/judge-naming.json) | Eval judge |
| [`requests/`](requests/) | Spec Request YAML (via PR) |
| [`docs/customizing.md`](docs/customizing.md) | How to customize templates and rules |
| Skill **generate-jira-automation** | Ask for Cursor webhook URL → write importable `docs/jira/*.json` |

## CLI

```bash
python -m repo_vendor propose --issue-file /tmp/issue.json --json
python -m repo_vendor vend --issue-file /tmp/issue.json --approval-comment "lgtm" --json
python -m repo_vendor doctor
```

Automation prompt: `docs/automation-setup.md`.

## Do not

- Commit `.env` or API keys
- Create when `repo-vended` is present
- Skip deterministic checks
- Support post-create rename
- Call Jira REST from the CLI
- Use global `CURSOR_API_KEY` as the webhook Bearer token
