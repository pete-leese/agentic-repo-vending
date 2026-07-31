# Connecting your Jira to repo vending

**Primary path:** Jira Automation → HTTP webhook → Cursor Automation (**Atlassian tools** for all board I/O) → `repo_vendor` (evals + GitHub only).

**Atlassian MCP/tools are not a wake trigger** — they are how the running Automation reads/writes the KAN board. The CLI never calls Jira REST.

```mermaid
flowchart LR
  Human --> Jira
  Jira -->|webhook POST| CursorWH[Cursor_Webhook]
  CursorWH --> Agent[Cloud_Agent]
  Agent --> Atlassian[Atlassian_tools]
  Atlassian --> Jira
  Agent --> CLI[repo_vendor]
  CLI --> GitHub[GitHub_API]
  Agent -->|apply jira plan| Atlassian
```

## Path comparison

| Path | When to use |
|------|-------------|
| **Webhook (default)** | Working setup for this demo — near real-time |
| **Cursor in Jira** (`@Cursor`) | Cursor Teams/Enterprise + [Marketplace app](https://cursor.com/docs/integrations/jira) |
| **Atlassian tools** | Required on the Automation for all Jira board reads/writes once the agent is running |

---

## Shared prerequisites

1. Cloud Agent secrets: `CURSOR_API_KEY`, `GITHUB_TOKEN` (Jira via Atlassian Automation tool — no `JIRA_EMAIL` / `JIRA_API_TOKEN`)
2. Optional CLI overrides for status/label *names* used in the JSON plan: `JIRA_IN_REVIEW_STATUS`, `JIRA_DONE_STATUS`, outcome label env vars
3. Labels:
   - `repo-vend-approved` (HITL)
   - `repo-vended` (set after create)
   - `repo-vend-success` | `repo-vend-warning` | `repo-vend-error` (outcome)
4. Template repos published
5. **Atlassian** tool enabled on the Cursor Automation (see [automation-setup.md](automation-setup.md))

Board statuses used by the Automation (override via env if your names differ — values appear in `result.jira.transition_to`):

| Phase | Default status |
|-------|----------------|
| HITL gate | In Review |
| While vending | In Progress (Automation transitions before CLI) |
| Success / warning | Done |
| Error (retry) | In Review |

---

## Webhook setup (default)

### 1. Cursor Automation

- Trigger: **Webhook**
- Repo: your `agentic-repo-vending` @ `main`
- Model: `composer-2.5`
- Tools: **Atlassian** enabled
- Instructions: paste from [automation-setup.md](automation-setup.md) (fetch issue → HITL → run `vend --issue-file … --json` → apply `result.jira`)
- Save → copy **webhook URL** and the **webhook API key** for *this* automation  
  (not the global Cloud Agent `CURSOR_API_KEY` — that yields `missing required scope: automation:…`)

### 2. Jira Automation

1. Trigger: Issue transitioned **to** In Review  
2. Condition: Labels contains `repo-vend-approved`  
3. Action: **Send web request**
   - Method: `POST`
   - URL: Cursor webhook URL
   - Headers:

| Key | Value |
|-----|--------|
| `Authorization` | `Bearer <webhook_api_key_from_this_automation>` |
| `Content-Type` | `application/json` |

   - Body (custom JSON):

```json
{
  "action": "vend",
  "issue": { "key": "{{issue.key}}" }
}
```

4. Enable the rule and confirm Audit log → HTTP 2xx

If your site has no Automation **secrets**, paste the Bearer token in the header and limit who can edit automation rules.

### 3. Human workflow

1. Create ticket (free text and/or labels)  
2. Move to **In Review**  
3. Add **`repo-vend-approved`**  
4. Agent comments with repo URL (or what’s missing) and adds **`repo-vended`** on success  

---

## Configuring for *your* board

Status/label *names* in the CLI JSON plan (optional env overrides):

| Variable | Example |
|----------|---------|
| `JIRA_IN_REVIEW_STATUS` | Exact status name on your board |
| `JIRA_DONE_STATUS` | `Done` |
| `JIRA_APPROVED_LABEL` | `repo-vend-approved` |
| `JIRA_VENDED_LABEL` | `repo-vended` |
| `JIRA_LABEL_SUCCESS` / `_WARNING` / `_ERROR` | Outcome labels |

Jira authentication for board I/O is the **Atlassian Automation tool**, not env tokens.

---

## Optional: Cursor in Jira (Teams / Enterprise)

Install Cursor from the Atlassian Marketplace, assign `@Cursor` (or automate assign). See [Cursor Jira docs](https://cursor.com/docs/integrations/jira). Personal plans typically use the webhook path above.
