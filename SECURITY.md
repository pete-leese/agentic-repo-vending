# Security

## Reporting

If you discover a vulnerability in this control plane or the vended-template flow, please open a private GitHub security advisory on this repository (or email the maintainer listed on the GitHub profile). Do not file a public issue with exploit details or live credentials.

## Secrets

| Secret | Scope |
|--------|--------|
| `CURSOR_API_KEY` | Cloud Agent / SDK (orchestrator + judge) |
| `GITHUB_TOKEN` | Spec PRs + create-from-template + classic branch protection. Classic PAT: `repo`. Fine-grained: Contents, PRs, **Administration** (read/write). |
| Webhook API key | Cursor Automation Bearer only — **not** `CURSOR_API_KEY` |

Never commit `.env`, real webhook URLs with embedded credentials, or Bearer tokens. Use placeholders in `docs/jira/*.json`.

## Trust boundaries

- Jira I/O goes through the **Atlassian** Cursor tool / Automation only; the CLI does not call Jira REST.
- Cursor hooks (`.cursor/hooks/`) are best-effort early feedback — **CI is the hard gate**.
- Hooks and `permissions.json` are not a sandbox; treat agent output as untrusted until reviewed.

## Dependency updates

Dependabot opens weekly PRs for pip and GitHub Actions (`.github/dependabot.yml`). Review lockfile diffs before merge.
