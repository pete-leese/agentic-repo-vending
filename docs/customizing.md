# Customizing repo vending

How to change board URLs, Keyword Approval phrases, templates, naming rules, and eval prompts without rewriting Python.

## Project config — `repo-vend.yaml`

The control-plane repo reads **[`repo-vend.yaml`](../repo-vend.yaml)** at runtime (env vars / `.env` still override for secrets and local experiments).

| Section | What you change |
|---------|-----------------|
| `jira.board_url` / `base_url` | Board + site URLs shown in docs/doctor |
| `jira.statuses.*` | Exact status names on your board (`New Request`, `In Progress`, `Done`, …) |
| `jira.labels.*` | Outcome / HITL label names |
| `jira.approval.keywords` | Phrases that approve a proposal (`approved`, `lgtm`, …) |
| `github.templates.*` | Which GitHub **template repo** maps to terraform / python / generic |
| `github.default_project_type` | Fallback when the ticket is not clearly terraform or python (`generic`) |
| `models.*` | Orchestrator / eval model IDs (must differ; see below) |
| `cloud_docs.*` | Cloud Agent MCP enrichment (AWS Docs / Azure / optional GCP) |

### Models

Defaults in `repo-vend.yaml`:

| Role | Default ID | Why |
|------|------------|-----|
| `models.orchestrator` | `claude-sonnet-5` | Stronger extract from messy tickets (Other Models pool) |
| `models.eval` | `composer-2.5` | Independent naming judge (Cursor Models pool) |

Keep orchestrator ≠ eval. Env overrides: `ORCHESTRATOR_MODEL`, `EVAL_MODEL`. Discover IDs for your account with the Cursor SDK: `Cursor.models.list()`.

The **Cloud Automation** model (Automations UI / prefill) is separate — it runs Atlassian tools + CLI; keep that on `composer-2.5` unless you intentionally change the Automations editor.

### Cloud documentation MCP (`cloud_docs`)

Optional enrichment for **propose** when tickets look like terraform / infra modules. The **Cloud Agent** queries enabled MCP servers and puts a short factual digest into `IssueSnapshot.additional_context`. The CLI feeds that into extract + judge prompts and freezes it on the Spec Request. On vend of a **terraform module**, the board Description may include a “Cloud documentation notes” section.

| Key | Purpose |
|-----|---------|
| `cloud_docs.enabled` | Master switch (default true) |
| `cloud_docs.max_chars` | Cap digest length (default 4000) |
| `cloud_docs.providers.<aws\|azure\|gcp>` | Per-cloud MCP catalog name + enable flag |

Configure MCP servers for Cloud Agents at [cursor.com/agents](https://cursor.com/agents) or **Dashboard → Integrations & MCP** (team). Stdio examples:

- AWS Docs: `uvx awslabs.aws-documentation-mcp-server@latest`
- Azure: `npx -y @azure/mcp@latest server start`

Prefill (`scripts/build_repo_vend_automation_prefill.py`) includes enabled `mcp_server` names from this section alongside Atlassian. Catalog names must match what the Automations editor shows.

**Does not** change Keyword Approval, naming patterns, or the deterministic gate — docs are advisory only. See [automation-setup.md](automation-setup.md).

After editing YAML, restart the Cloud Agent run (no rebuild required if the file is in the checkout).

If you change **`jira.approval.keywords`** or status/label names used by Automation conditions, **regenerate and re-import** Jira rules:

```bash
python3 scripts/generate_jira_automation_import.py --webhook-url '<YOUR_CURSOR_WEBHOOK_URL>'
```

Or run the **generate-jira-automation** skill. Then update each rule’s **Authorization** Bearer again if needed. See [getting-started.md](getting-started.md) §6 and [jira-setup.md](jira-setup.md).

### Secrets stay in the environment

Never put tokens in `repo-vend.yaml`. Keep `GITHUB_TOKEN` and `CURSOR_API_KEY` in Cloud Agent secrets / `.env`.

## Template selection

Templates are public GitHub **template repositories** under `github.owner`:

| Key in YAML | Default repo | When used |
|-------------|--------------|-----------|
| `templates.terraform` | `template-terraform-repo` | `project_type: terraform` |
| `templates.python` | `template-python-repo` | `project_type: python` |
| `templates.generic` | `template-generic-repo` | `project_type: generic` or default fallback |

### Point at a different template

1. Publish or fork a template repo and mark it as a GitHub template.
2. Set e.g. `github.templates.python: my-company-python-template` in `repo-vend.yaml`.
3. Ensure `GITHUB_TOKEN` can `generate` from that template and apply **classic** branch protection
   (`PUT .../branches/main/protection` — not rulesets). Classic PAT needs `repo`; fine-grained needs
   Administration: Read and write.
4. Update [`rules/naming.md`](../rules/naming.md) and [`evals/judge-naming.json`](../evals/judge-naming.json) `allowed_templates` so the judge allow-list matches.

### Add a new type (advanced)

1. Add a template key under `github.templates` and a local tree under `templates/`.
2. Extend `ProjectType` + naming patterns in code / `rules/naming.md`.
3. Update eval JSON `allowed_values` / `allowed_templates`.
4. Run `./scripts/publish_templates.sh` (or `--update`).

### Generic template

Use when the request is not specifically Python or Terraform (label `type-generic`, or leave type unset so `default_project_type: generic` applies). Local scaffold: [`templates/template-generic-repo/`](../templates/template-generic-repo/). Naming: plain kebab-case (not `python-` / `terraform-` prefixed), e.g. `billing-gateway`.

## Naming and HITL rules — `rules/naming.md`

Agent-facing policy (patterns, Keyword Approval, labels). The deterministic gate in `repo_vendor` must stay aligned when you change patterns.

## Eval prompts — `evals/*.json`

| File | Role |
|------|------|
| [`evals/extract-intent.json`](../evals/extract-intent.json) | Orchestrator system + user template |
| [`evals/judge-naming.json`](../evals/judge-naming.json) | Judge system + user template (injects `rules/naming.md`) |

Both templates accept `{additional_context}` (cloud docs digest; defaults to `(none)`). Edit wording and allow-lists here; prefer this over hardcoding prompts in Python.

## Vended README

After create-from-template, the vendor **rewrites `README.md`** on the new repo with the issue summary/description, Jira key, template id, and repo URL — so the repo does not keep “this is a template” boilerplate. Soft-failure → `repo-vend-warning`.

## Cursor rule

[`.cursor/rules/repo-vend.mdc`](../.cursor/rules/repo-vend.mdc) points agents at `rules/naming.md`, `evals/`, and `repo-vend.yaml`.
