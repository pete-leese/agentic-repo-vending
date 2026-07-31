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
| `models.*` | Orchestrator / eval model IDs |

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
3. Ensure `GITHUB_TOKEN` can `generate` from that template.
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

Edit wording and allow-lists here; prefer this over hardcoding prompts in Python.

## Vended README

After create-from-template, the vendor **rewrites `README.md`** on the new repo with the issue summary/description, Jira key, template id, and repo URL — so the repo does not keep “this is a template” boilerplate. Soft-failure → `repo-vend-warning`.

## Cursor rule

[`.cursor/rules/repo-vend.mdc`](../.cursor/rules/repo-vend.mdc) points agents at `rules/naming.md`, `evals/`, and `repo-vend.yaml`.
