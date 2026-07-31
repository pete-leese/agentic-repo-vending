# Cursor Automation + Jira webhook setup

## Why webhook

Cursor Automations have no native Jira trigger. Jira Automation → HTTP webhook keeps the path fast (no laptop, no cron lag). See [ADR 0001](adr/0001-jira-webhook-to-cursor.md).

## 1. Create Cursor Automation

1. Open Cursor → Automations
2. Trigger: **Webhook**
3. Model: **`composer-2.5`**
4. Repo: `pete-leese/agentic-repo-vending` (branch `main`)
5. Instructions (paste):

```text
You are the repo-vend cloud runner for this repository.

1. Parse the webhook JSON for a Jira issue key (fields like issue.key, key, or issueKey).
2. Ensure dependencies are installed (environment.json should already have run install).
3. Run:
   python -m repo_vendor vend --issue <KEY>
4. If the payload indicates a rename (action=rename) with currentName and comment, run:
   python -m repo_vendor rename --issue <KEY> --current-name <NAME> --comment "<TEXT>"
5. Paste the CLI stdout/stderr into your final reply.
6. Never print secret values.
```

6. Save and copy the **webhook URL** + auth secret if prompted

## 2. Jira Automation (vend)

Project: KAN

**Trigger:** Issue transitioned to **In Review**  
**Condition:** Labels contain `repo-vend-approved`  
(Alternatively: label added + status equals In Review)

**Action:** Send web request

- Method: POST
- URL: *(Cursor webhook URL)*
- Headers: as required by Cursor webhook auth
- Body example:

```json
{
  "action": "vend",
  "issue": {
    "key": "{{issue.key}}"
  }
}
```

## 3. Jira Automation (rename) — optional

**Trigger:** Comment added  
**Condition:** Labels contain `repo-vended`  
**Action:** Webhook POST

```json
{
  "action": "rename",
  "issue": { "key": "{{issue.key}}" },
  "comment": "{{comment.body}}",
  "currentName": ""
}
```

If `currentName` is empty, have the Cloud Agent read the last vend comment for the repo URL/name, or store the name in a Jira custom field later (post-MVP).

For MVP demos you can also run rename via CLI with an explicit `--current-name`.

## 4. Cloud Agent secrets

In [Cloud Agents dashboard](https://cursor.com/dashboard?tab=cloud-agents) for this repo:

- `CURSOR_API_KEY`
- `GITHUB_TOKEN`
- `JIRA_EMAIL`
- `JIRA_API_TOKEN`

Confirm [`.cursor/environment.json`](../.cursor/environment.json) install succeeds on a test agent run.
