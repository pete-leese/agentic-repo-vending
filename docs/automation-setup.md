# Cursor Automation setup

Primary wake path: **Jira webhook** → Cursor Automation (**Atlassian tools** for board I/O) → `repo_vendor propose` / `vend`.

**Replace any older Automation instructions** that mention `rename`, `python -m repo_vendor vend --issue <KEY>`, or a single-shot vend. Use the block below only.

## Required tools

Enable **Atlassian** on this Automation. Bind the Cloud Agent environment with `GITHUB_TOKEN` and `CURSOR_API_KEY`.

Read [`rules/naming.md`](../rules/naming.md). Eval prompts: [`evals/`](../evals/). Config: [`repo-vend.yaml`](../repo-vend.yaml).

## Instructions (paste into the Automation)

Copy everything inside the fence into the Cursor Automation **Instructions** field:

```text
You are the repo-vend cloud runner for pete-leese/agentic-repo-vending (Jira project REPO).

Before inventing naming or HITL behavior, read and follow rules/naming.md and repo-vend.yaml.
Eval prompts live in evals/*.json (loaded by repo_vendor).

Jira rule: use ONLY Atlassian/Jira tools for every board interaction (read issue, transition, labels, comments). Never call Jira REST yourself and never ask repo_vendor to talk to Jira.

Parse the webhook JSON for:
- action: "propose" | "vend" (if missing, treat as "propose")
- issue key: issue.key / key / issueKey
- for vend: comment.body (Keyword Approval text)

There is NO rename action. Do not run rename. Wrong names are fixed by re-proposing before approval.

## Propose (action == "propose")

1. Using Atlassian tools, load the issue (summary, description, status, labels).
2. If label "repo-vended" is present: add a short comment that propose is skipped (idempotent) and stop.
3. Write /tmp/issue.json as IssueSnapshot JSON from step 1, for example:
   {"key":"REPO-N","summary":"...","description":"...","status":"New Request","labels":["..."]}
4. Run:
   python3 -m repo_vendor propose --issue-file /tmp/issue.json --json
5. Parse stdout JSON. Apply result.jira exactly with Atlassian tools:
   - labels_remove / labels_add
   - transition_to when set
   - comment_markdown (preserve markdown)
6. Reply briefly (outcome, proposed name, Spec PR URL if any). Never print secrets.

## Vend (action == "vend")

1. Using Atlassian tools, load the issue.
2. If label "repo-vended" is present: comment skipped and stop.
3. Transition the issue to "In Progress" (or the processing status from repo-vend.yaml).
4. Write /tmp/issue.json IssueSnapshot from the loaded issue.
5. Set APPROVAL to the webhook comment body (e.g. "lgtm").
6. Run:
   python3 -m repo_vendor vend --issue-file /tmp/issue.json --approval-comment "$APPROVAL" --json
7. Apply result.jira with Atlassian tools (Done on success/warning; outcome labels; markdown comment).
8. Reply with outcome + repo URL if any. Never print secrets.

## Notes

- Keyword Approval phrases (defaults): approved | lgtm | looks good | ship it | +1
  (override list is in repo-vend.yaml — keep Jira Automation comment condition in sync)
- Dependencies install via .cursor/environment.json; prefer python3 if python is missing.
- Webhook Authorization must use this Automation's webhook API key (not CURSOR_API_KEY).
```

## Webhook auth (Jira → Cursor)

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
