# Getting started

## Prerequisites

- GitHub account `pete-leese` (or set `GITHUB_OWNER`)
- Jira project [KAN](https://agentic-workflow-demo.atlassian.net/jira/software/projects/KAN/boards/2)
- Cursor account with Cloud Agents + Automations
- API tokens stored only as **secrets** (not in git)

## 1. Clone and install

```bash
git clone https://github.com/pete-leese/agentic-repo-vending.git
cd agentic-repo-vending
pip install -e '.[dev,cursor]'
```

Cloud Agents use [`.cursor/environment.json`](../.cursor/environment.json) so `pip install -e '.[dev,cursor]'` runs on VM start.

## 2. Configure secrets

Create a `.env` locally (gitignored) or set Cloud Agent secrets:

| Secret | Purpose |
|--------|---------|
| `CURSOR_API_KEY` | Cursor SDK (`composer-2.5` / `composer-2`) — **generate a new key** |
| `GITHUB_TOKEN` | Create repos, branch protection, rename |
| `JIRA_EMAIL` | Jira Cloud user email |
| `JIRA_API_TOKEN` | [Atlassian API token](https://id.atlassian.com/manage-profile/security/api-tokens) |

Optional overrides: `ORCHESTRATOR_MODEL`, `EVAL_MODEL`, `TEMPLATE_TERRAFORM`, `TEMPLATE_PYTHON`, `ALLOW_LLM_FALLBACK`.

```bash
python -m repo_vendor doctor
```

## 3. Publish GitHub templates

```bash
chmod +x scripts/publish_templates.sh
./scripts/publish_templates.sh
```

This creates public template repos:

- `https://github.com/pete-leese/template-terraform-repo`
- `https://github.com/pete-leese/template-python-repo`

## 4. Jira labels

Create labels (or let Jira create on first use):

- `repo-vend-approved` (required HITL)
- `repo-vended` (idempotency after create)
- `repo-vend-success` / `repo-vend-warning` / `repo-vend-error` (outcome)
- Optional helpers: `type-terraform`, `type-python`, `tf-module`, `tf-root`, `platform-aws`, `platform-gcp`, `platform-azure`

## 5. Wire Jira → Cursor webhook

Follow **[jira-setup.md](jira-setup.md)** (Cursor webhook Automation + Jira Send web request with `Authorization: Bearer <webhook_api_key>`).

## 6. First ticket

1. Create a KAN issue with free-text description, e.g.  
   `I need a new repo for a terraform module for S3 bucket for my aws platform`
2. Move to **In Review**
3. Add `repo-vend-approved`
4. Watch for the agent comment + new public GitHub repo

## Naming cheat sheet

| Type | Pattern | Example |
|------|---------|---------|
| Terraform module | `terraform-module-<name>-<platform>` | `terraform-module-s3-bucket-aws` |
| Terraform root | `terraform-<name>` | `terraform-eks-gitops-management` |
| Python | `python-<purpose-kebab>` | `python-invoice-parser` |

Snake_case / spaces are normalized to kebab-case automatically.
