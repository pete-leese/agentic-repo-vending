# Agentic Repo Vending

Laptop-free workflow that vends public GitHub repositories from Jira tickets using **Cursor Cloud Agents**, **PydanticAI**, and dual-model evals.

**Owner:** [`pete-leese`](https://github.com/pete-leese)  
**Jira board:** [KAN](https://agentic-workflow-demo.atlassian.net/jira/software/projects/KAN/boards/2)

## What it does

1. Human moves a ticket to **In Review** and adds label **`repo-vend-approved`**
2. A Cursor Automation wakes (recommended: **schedule** → `repo_vendor scan`; optional: Jira webhook)
3. Cloud Agent runs the PydanticAI CLI
4. Orchestrator model **`composer-2.5`** extracts intent (free text and/or labels)
5. Eval model **`composer-2`** judges naming + template choice
6. Deterministic kebab/pattern rules must also pass (hard gate)
7. On success: create public repo from `template-terraform-repo` or `template-python-repo`, protect `main`, comment URL, label **`repo-vended`**
8. On failure: comment what is missing — no repo created
9. Rename: comment a new name on a vended ticket → re-eval → rename

Trigger options (MCP is not one of them): [docs/jira-setup.md](docs/jira-setup.md).

## Architecture

```mermaid
sequenceDiagram
  participant Human
  participant Jira as Jira_KAN
  participant JiraAuto as Jira_Automation
  participant CursorWH as Cursor_Webhook
  participant CloudAgent as Cloud_Agent_composer25
  participant App as PydanticAI_App
  participant Eval as Eval_composer2
  participant Rules as Deterministic_Rules
  participant GitHub as GitHub_pete_leese

  Human->>Jira: Ticket description and/or labels
  Human->>Jira: Move In Review plus repo-vend-approved
  JiraAuto->>CursorWH: Webhook ticket key
  CursorWH->>CloudAgent: Start run
  CloudAgent->>App: python -m repo_vendor vend --issue KEY
  App->>Jira: Fetch issue
  App->>App: Extract intent composer-2.5
  App->>Eval: Judge naming and template composer-2
  App->>Rules: Kebab and pattern checks
  alt Checks fail
    App->>Jira: Comment missing info
  else Checks pass
    App->>GitHub: Create from template public
    App->>GitHub: Branch protect main
    App->>Jira: Comment URL plus rename invite
    App->>Jira: Add repo-vended
  end
```

## Models (explicit)

| Role | Model ID |
|------|----------|
| Cloud Automation runtime | `composer-2.5` |
| Orchestrator (intent) | `composer-2.5` |
| Eval judge | `composer-2` |
| Naming / template gate | deterministic (no LLM) |

## Quick links

- [Getting started](docs/getting-started.md)
- [Jira setup (cron / webhook / Cursor in Jira / MCP)](docs/jira-setup.md)
- [Demo walkthrough](docs/demo-walkthrough.md)
- [Automation setup](docs/automation-setup.md)
- [Post-MVP (OTEL / harnesses)](docs/post-mvp.md)
- [Domain glossary](CONTEXT.md)
- [ADRs](docs/adr/)

## Triggering (important)

**Atlassian MCP is not a trigger.** It only helps once an agent is already running.

Prefer **cron scan** (no Jira Automation): Cursor schedule → `python -m repo_vendor scan`.  
Webhook and Cursor-in-Jira are optional faster paths — see [docs/jira-setup.md](docs/jira-setup.md).

## Local development

```bash
pip install -e '.[dev,cursor]'
pytest
python -m repo_vendor doctor
python -m repo_vendor scan --dry-run
python -m repo_vendor vend --issue KAN-1 --dry-run
```

## Publish template repos

```bash
export GITHUB_TOKEN=...   # classic PAT with repo scope
chmod +x scripts/publish_templates.sh
./scripts/publish_templates.sh
```

## Secrets (Cloud Agent dashboard — never commit)

- `CURSOR_API_KEY` — generate a **new** key (rotate any key that was pasted into chat)
- `GITHUB_TOKEN`
- `JIRA_EMAIL` / `JIRA_API_TOKEN`
