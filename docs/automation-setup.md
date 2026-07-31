# Cursor Automation setup

Primary wake path: **Jira webhook** → this Automation → `repo_vendor vend`.  
Full Jira steps: [jira-setup.md](jira-setup.md).

## Webhook Automation

1. Cursor → Automations → New  
2. Trigger: **Webhook**  
3. Repo: `pete-leese/agentic-repo-vending` @ `main`  
4. Model: `composer-2.5`  
5. Instructions:

```text
You are the repo-vend cloud runner for pete-leese/agentic-repo-vending.

1. Parse the webhook JSON for a Jira issue key (issue.key, key, or issueKey).
2. Dependencies should already be installed via .cursor/environment.json.
3. If action is missing or "vend", run:
   python -m repo_vendor vend --issue <KEY>
4. If action is "rename", run:
   python -m repo_vendor rename --issue <KEY> --current-name <currentName> --comment "<comment>"
   If currentName is empty, infer it from recent Jira comments on the issue.
5. Reply with the CLI stdout/stderr. Never print secret values.
```

6. Save → copy **webhook URL** + **webhook API key** (scoped to this automation)  
7. Paste into Jira **Send web request** as:

```text
Authorization: Bearer <webhook_api_key>
Content-Type: application/json
```

Do **not** use the global Cloud Agent / Integrations `CURSOR_API_KEY` for the webhook — it lacks `automation:<id>` scope.

## Cloud Agent secrets

[Dashboard](https://cursor.com/dashboard?tab=cloud-agents) (for running `repo_vendor`, separate from webhook auth):

- `CURSOR_API_KEY`
- `GITHUB_TOKEN`
- `JIRA_EMAIL`
- `JIRA_API_TOKEN`

Optional: `JIRA_BASE_URL`, label/status overrides.

Confirm [`.cursor/environment.json`](../.cursor/environment.json) install succeeds on a test run.
