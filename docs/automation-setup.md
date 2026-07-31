# Cursor Automation setup

See **[jira-setup.md](jira-setup.md)** for the full decision tree (Cursor in Jira vs cron vs webhook vs MCP).

## Recommended: cron scan (no Jira Automation)

1. Cursor → Automations → New  
2. Trigger: **Schedule** (e.g. every 5 minutes)  
3. Repo: `pete-leese/agentic-repo-vending` @ `main`  
4. Model: `composer-2.5`  
5. Instructions:

```text
Run: python -m repo_vendor scan
Paste stdout/stderr. Never print secrets.
```

6. Ensure Cloud Agent secrets: `CURSOR_API_KEY`, `GITHUB_TOKEN`, `JIRA_EMAIL`, `JIRA_API_TOKEN`

## Optional: webhook (near real-time)

1. Trigger: **Webhook**  
2. Same repo/model  
3. Instructions: parse `issue.key`, run `python -m repo_vendor vend --issue <KEY>`  
4. Save → copy URL/auth into a Jira Automation (details in [jira-setup.md](jira-setup.md) Path C)

## Cloud Agent secrets

[Dashboard](https://cursor.com/dashboard?tab=cloud-agents):

- `CURSOR_API_KEY`
- `GITHUB_TOKEN`
- `JIRA_EMAIL`
- `JIRA_API_TOKEN`

Optional: `JIRA_BASE_URL`, `JIRA_PROJECT_KEY`, label/status overrides.

Confirm [`.cursor/environment.json`](../.cursor/environment.json) install succeeds on a test run.
