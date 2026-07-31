# Getting started

## Prerequisites

- GitHub account `pete-leese` (or set `GITHUB_OWNER`)
- Jira project [REPO](https://agentic-workflow-demo.atlassian.net/jira/software/projects/REPO/boards/2)
- Cursor account with Cloud Agents + Automations
- API tokens stored only as **secrets** (not in git)

## 1. Clone and install

```bash
git clone https://github.com/pete-leese/agentic-repo-vending.git
cd agentic-repo-vending
pip install -e '.[dev,cursor]'
```

Cloud Agents use [`.cursor/environment.json`](../.cursor/environment.json) so `pip install -e '.[dev,cursor]'` runs on VM start.

## 2. Configure project + secrets

Edit [`repo-vend.yaml`](../repo-vend.yaml) for board URL, approval keywords, and template names (see [customizing.md](customizing.md)).

| Secret | Purpose |
|--------|---------|
| `CURSOR_API_KEY` | Cursor SDK (`composer-2.5` extract + `claude-sonnet-5` judge; see `repo-vend.yaml`) |
| `GITHUB_TOKEN` | Spec PRs on control plane + create-from-template (classic `repo`) |

Jira board I/O: **Atlassian** tool on the Cursor Automation (not Jira API tokens in the CLI).

```bash
python -m repo_vendor doctor
```

## 3. Publish GitHub templates

```bash
chmod +x scripts/publish_templates.sh
./scripts/publish_templates.sh
```

Creates/updates public templates including `template-terraform-repo`, `template-python-repo`, and `template-generic-repo`.

## 4. Jira labels

- `repo-vend-proposed` / `repo-vended`
- `repo-vend-success` / `repo-vend-warning` / `repo-vend-error`
- Optional helpers: `type-terraform`, `type-python`, `type-generic`, `tf-module`, `tf-root`, `platform-aws`, …

## 5. Cursor Automation

**Option A — skill (recommended):** in Cursor Agents Window, run **setup-repo-vend-automation**.  
It opens a prefilled Webhook Automation, then **automatically** runs the Jira import generator (**generate-jira-automation** steps) when you paste the webhook URL into chat — no second skill invoke.

You still must **Save** in the UI — Cursor does not return webhook URL/API key until then.

**Option B — manual:**

1. Create a **Webhook** Automation on this repo (`docs/automation-setup.md`).
2. Enable the **Atlassian** tool; bind the environment with secrets.
3. Paste instructions from [automation-setup.md](automation-setup.md).
4. Save and copy:
   - **Webhook URL** (`https://api2.cursor.sh/automations/webhook/…`)
   - **Webhook API key** (Automation-scoped Bearer — not `CURSOR_API_KEY`)

## 6. Generate + import Jira Automation rules

Two rules: **propose** on issue create (New Request), **vend** on Keyword Approval comment.

If you used **setup-repo-vend-automation**, Phase B already generates the import file. Otherwise:

**Option A — skill:** run **generate-jira-automation** in Cursor and paste your webhook URL when asked.

**Option B — script:**

```bash
python3 scripts/generate_jira_automation_import.py \
  --webhook-url 'https://api2.cursor.sh/automations/webhook/<YOUR_ID>'
```

Writes [`docs/jira/automation-rules-import.json`](jira/automation-rules-import.json) using your URL and settings from `repo-vend.yaml`.

### Import

1. Open **Space Settings → Automation → Global automation**, or go to  
   `{jira.base_url}/jira/settings/automation`  
   (from `repo-vend.yaml`, e.g. `https://YOUR.atlassian.net/jira/settings/automation`).
2. **⋯ → Import rules** → upload `docs/jira/automation-rules-import.json`.
3. Select `repo-vend-propose` and `repo-vend-approve`.
4. For **each** rule’s **Send web request** (POST) action, set:

```text
Authorization: Bearer <webhook_api_key_from_this_Cursor_Automation>
```

   Replace the placeholder `REPLACE_WITH_CURSOR_WEBHOOK_API_KEY` if present.
5. **Enable** both rules; disable/delete any old one-shot vend rule.

Full detail: [jira-setup.md](jira-setup.md). Export pitfalls: `.cursor/rules/jira-automation-export.mdc`.

## 7. First ticket

1. Create a REPO issue in **New Request**, e.g.  
   `I need a new repo for a terraform module for S3 bucket for my aws platform`
2. Read the proposal comment (name, template, evals) + Spec PR
3. Reply `lgtm` (or another keyword from `repo-vend.yaml`)
4. Watch for the vended repo URL (README is rewritten away from template boilerplate)

## Naming cheat sheet

Canonical rules: **[rules/naming.md](../rules/naming.md)**. Project config / templates: **[customizing.md](customizing.md)** · [`repo-vend.yaml`](../repo-vend.yaml).

| Type | Pattern | Example |
|------|---------|---------|
| Terraform module | `terraform-module-<name>-<platform>` | `terraform-module-s3-bucket-aws` |
| Terraform root | `terraform-<name>` | `terraform-eks-gitops-management` |
| Python | `python-<purpose-kebab>` | `python-invoice-parser` |
| Generic | plain kebab | `billing-gateway` |
