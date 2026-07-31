# Cursor Automation setup

Primary wake path: **Jira webhook** → Cursor Automation (**Atlassian tools** for board I/O) → `repo_vendor propose` / `vend`.

## Required tools

Enable **Atlassian** on this Automation. Bind the Cloud Agent environment with `GITHUB_TOKEN` and `CURSOR_API_KEY`.

Read [`rules/naming.md`](../rules/naming.md). Eval prompts: [`evals/`](../evals/).

## Instructions (paste into the Automation)

```text
You are the repo-vend cloud runner for pete-leese/agentic-repo-vending.

Before inventing naming or HITL behavior, read and follow rules/naming.md.
Eval prompts live in evals/*.json (loaded by repo_vendor).

Jira rule: use ONLY Atlassian/Jira tools for every board interaction. Never call Jira REST; never ask repo_vendor to talk to Jira.

Parse webhook JSON for action (propose|vend) and issue.key.

## Propose (action == "propose" or missing)

1. Load issue via Atlassian (summary, description, status, labels).
2. If label repo-vended present: comment skipped; stop.
3. Write /tmp/issue.json IssueSnapshot from step 1.
4. Run: python3 -m repo_vendor propose --issue-file /tmp/issue.json --json
5. Apply result.jira with Atlassian tools (labels + markdown comment).
6. Reply briefly (proposed name + Spec PR URL if any). Never print secrets.

## Vend (action == "vend")

1. Load issue via Atlassian.
2. If repo-vended: comment skipped; stop.
3. Transition to In Progress.
4. Write /tmp/issue.json; set APPROVAL from webhook comment.body.
5. Run: python3 -m repo_vendor vend --issue-file /tmp/issue.json --approval-comment "$APPROVAL" --json
6. Apply result.jira (Done on success/warning; outcome labels; markdown comment).
7. Reply with outcome + repo URL. Never print secrets.

## Notes

- Keyword Approval only: approved | lgtm | looks good | ship it | +1
- No post-create rename.
- Webhook Authorization uses this Automation's webhook API key (not CURSOR_API_KEY).
```

## Webhook auth

```text
Authorization: Bearer <webhook_api_key>
Content-Type: application/json
```

## Next: generate Jira Automation import JSON

With the **webhook URL** and **webhook API key** in hand:

1. Run skill **generate-jira-automation** (or `scripts/generate_jira_automation_import.py --webhook-url '…'`).
2. Import `docs/jira/automation-rules-import.json` via **Space Settings → Automation → Global automation**  
   (or `{jira.base_url}/jira/settings/automation` from `repo-vend.yaml`).
3. Set `Authorization: Bearer <webhook_api_key>` on **each** Send web request action.
4. Enable both rules.

See [getting-started.md](getting-started.md) §6 and [jira-setup.md](jira-setup.md).

## Secrets

| Secret | Purpose |
|--------|---------|
| `GITHUB_TOKEN` | Spec PRs on control plane + create-from-template (classic `repo`) |
| `CURSOR_API_KEY` | composer-2.5 / composer-2 |

Jira access: **Atlassian Automation tool** only.
