# Agentic Repo Vending

Laptop-free workflow that vends public GitHub repositories from Jira tickets using **Cursor Cloud Agents**, dual-model evals, and hybrid Spec Requests.

**Owner:** [`pete-leese`](https://github.com/pete-leese)  
**Jira board:** [REPO](https://agentic-workflow-demo.atlassian.net/jira/software/projects/REPO/boards/2)

## What it does

1. Human creates a ticket in **New Request**
2. Jira Automation POSTs `action: propose` → agent runs evals → comments proposal + opens `requests/<KEY>.yaml` PR
3. Optional: edit summary/description or add helper labels → re-propose with more context
4. Human replies **`lgtm`** / **`approved`** / … (Keyword Approval)
5. Jira POSTs `action: vend` → agent merges Spec PR → create-from-template → protect `main`
6. No post-create rename

Setup: [Getting started](docs/getting-started.md) · [Jira + webhook](docs/jira-setup.md) · [Cursor Automation](docs/automation-setup.md) · [Rules](rules/naming.md) · [Config](repo-vend.yaml)

## Quick setup (Jira ↔ Cursor)

**From Cursor (recommended):** run skill **setup-repo-vend-automation**. It opens a prefilled Webhook Automation draft, then when you **paste the webhook URL** into chat it automatically generates Jira import JSON (same as **generate-jira-automation** — no second skill).

Cursor cannot fully create the Automation or return webhook credentials without the UI — you still click **Save** and copy the webhook URL + API key.

**Manual path:**

1. Create a Cursor **Webhook** Automation ([automation-setup.md](docs/automation-setup.md)); copy webhook URL + **webhook API key**.
2. Generate importable Jira rules (skill **generate-jira-automation**, or script):

```bash
python3 scripts/generate_jira_automation_import.py \
  --webhook-url 'https://api2.cursor.sh/automations/webhook/<YOUR_ID>'
```

3. Import `docs/jira/automation-rules-import.json` via **Space Settings → Automation → Global automation**  
   (or `{jira.base_url}/jira/settings/automation` from [`repo-vend.yaml`](repo-vend.yaml)).
4. On **each** rule’s **Send web request** POST, set `Authorization: Bearer <webhook_api_key>`.
5. Enable all four rules; disable any old one-shot vend rule.

Full walkthrough: [docs/getting-started.md](docs/getting-started.md).

## Architecture

```mermaid
sequenceDiagram
  participant Human
  participant Jira as Jira_REPO
  participant Agent as Cloud_Agent
  participant App as repo_vendor
  participant Spec as requests_YAML
  participant GitHub as GitHub_pete_leese

  Human->>Jira: Create New_Request
  Jira->>Agent: webhook propose
  Agent->>App: propose --issue-file
  App->>Spec: open PR
  Agent->>Jira: proposal comment
  Human->>Jira: comment lgtm
  Jira->>Agent: webhook vend
  Agent->>App: vend --approval-comment
  App->>Spec: merge PR
  App->>GitHub: create from template
  Agent->>Jira: Done plus URL
```

## Models

| Role | Model ID | Notes |
|------|----------|--------|
| Cloud Automation (agent runtime) | `composer-2.5` | Prefill / Automations UI |
| Propose extract (orchestrator) | `claude-sonnet-5` | Other Models pool |
| Eval judge | `composer-2.5` | Cursor Models pool; must ≠ orchestrator |
| Naming gate | deterministic |

## Quick links

- [Getting started](docs/getting-started.md) (includes generate + import Jira rules)
- [Customizing (config, templates, rules)](docs/customizing.md)
- [Naming / HITL rules](rules/naming.md)
- [Project config](repo-vend.yaml)
- [Eval prompts (JSON)](evals/)
- [Spec requests](requests/)
- [Jira + webhook setup](docs/jira-setup.md)
- [Setup Cursor Automation skill](.agents/skills/setup-repo-vend-automation/SKILL.md)
- [Generate Jira Automation skill](.agents/skills/generate-jira-automation/SKILL.md)
- [Automation setup](docs/automation-setup.md)
- [Demo walkthrough](docs/demo-walkthrough.md)
- [Post-MVP](docs/post-mvp.md)
- [Domain glossary](CONTEXT.md)
- [ADRs](docs/adr/)
- [Conventions](docs/conventions/)
- [Contributing](CONTRIBUTING.md)
- [SECURITY](SECURITY.md)

## Local development

Requires [uv](https://docs.astral.sh/uv/).

```bash
make sync          # uv sync --group dev --extra cursor
make ci            # ruff + mypy (critical path) + pytest + coverage
make doctor
echo '{"key":"REPO-1","summary":"python logging helper","description":"...","status":"New Request","labels":["type-python"]}' \
  | uv run python -m repo_vendor propose --json --dry-run
```

Optional: `make hooks` installs pre-commit (ruff on commit, pytest on push).

Conventions: [style](docs/conventions/style.md) · [testing](docs/conventions/testing.md) · [PRs](docs/conventions/pr.md) · [SECURITY](SECURITY.md)

## Secrets (Cloud Agent — never commit)

- `CURSOR_API_KEY`
- `GITHUB_TOKEN` — classic `repo` (Spec PRs + template generate + classic branch protection). Fine-grained tokens need **Administration: Read and write**.
- Jira: **Atlassian Automation tool**
- See [SECURITY.md](SECURITY.md)
