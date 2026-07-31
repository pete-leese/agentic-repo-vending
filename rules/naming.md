# Repo vend naming and eval rules

Single source of truth for humans and the Cursor Automation. Board URLs, approval keyword *lists*, and template **repo names** are configured in [`repo-vend.yaml`](../repo-vend.yaml) — see [`docs/customizing.md`](../docs/customizing.md). LLM evals load `/evals/*.json` and inject this file into the judge.

## Two-phase HITL

1. **Propose** — Issue **created** in **New Request** → agent runs evals → Jira proposal comment. On pass, opens PR `requests/<ISSUE-KEY>.yaml`.
2. **Re-propose (more context)** — While still **New Request** and **not** `repo-vended`, editing **summary/description** or adding a helper label (`platform-*` / `tf-*` / `type-*`) re-triggers `action: propose`. Outcome labels (`repo-vend-*`) do **not** re-trigger.
3. **Approve** — Human replies with a Keyword Approval phrase (from `repo-vend.yaml` → `jira.approval.keywords`) → agent merges Spec PR → create-from-template.
4. **No rename after create** — Wrong name: edit the ticket and re-propose before approve, or open a new request.

### Keyword Approval (defaults)

Default phrases (override in `repo-vend.yaml`):

`approved` | `lgtm` | `looks good` | `ship it` | `+1`

Comment likes/reactions are **not** used. Keep the Jira Automation comment condition in sync when you change keywords.

### Labels

| Label | Meaning |
|-------|---------|
| **`repo-vend-proposed`** | Spec PR opened; awaiting Keyword Approval |
| **`repo-vended`** | Repo already created — do not create again |
| **`repo-vend-success`** | Created and `main` protection applied |
| **`repo-vend-warning`** | Repo created but a non-fatal step failed (e.g. branch protection / README rewrite) |
| **`repo-vend-error`** | Propose or vend did not complete |

Status flow: **New Request** (create / re-propose) → propose → **In Progress** while vending → **Done** on success/warning.

## Helper labels (optional)

| Label | Meaning |
|-------|---------|
| `type-terraform` / `type-python` / `type-generic` | Project type |
| `tf-module` / `tf-root` | Terraform shape |
| `platform-aws` / `platform-gcp` / `platform-azure` | Cloud platform (modules); often optional when the service implies a cloud |

## Naming (always kebab-case)

Snake_case, spaces, and CamelCase are normalized to kebab-case before checks.

| Type | Pattern | Example |
|------|---------|---------|
| Terraform module | `terraform-module-<name>-<platform>` | `terraform-module-s3-bucket-aws` |
| Terraform root | `terraform-<name>` | `terraform-eks-gitops-management` |
| Python | `python-<purpose-kebab>` | `python-invoice-parser` |
| Generic | plain kebab (no `terraform-` / `python-` prefix) | `billing-gateway` |

Platforms: `aws` | `gcp` | `azure`.

### Platform from service name

When `platform-*` / `aws|gcp|azure` is absent, derive platform from cloud-specific services (see `src/repo_vendor/platform_aliases.py`):

| Service (examples) | Platform |
|--------------------|----------|
| EKS, ECS, EC2, S3, RDS, Lambda, DynamoDB, SQS, SNS, CloudFront, Route53 | `aws` |
| GKE, GCS, BigQuery, Cloud Run, GCE, Pub/Sub | `gcp` |
| AKS, Azure AD, Cosmos DB | `azure` |

Example: summary `terraform module for EKS` + label `tf-module` → platform `aws` → `terraform-module-eks-…-aws` (no `platform-aws` label required).

If type is unclear, `github.default_project_type` in `repo-vend.yaml` applies (default **generic**).

## Templates

Configured under `github.templates` in `repo-vend.yaml` (defaults below):

| Project type | GitHub template |
|--------------|-----------------|
| Terraform | `template-terraform-repo` |
| Python | `template-python-repo` |
| Generic | `template-generic-repo` |

After create-from-template, the vendor **rewrites `README.md`** on the new repo so it describes the project (not the template).

## Spec Request (SDD)

Path: `requests/<ISSUE-KEY>.yaml` on the control-plane repo. Frozen after propose; **vend reads this file**, not a fresh ticket extract. Re-propose updates the Spec PR from the latest ticket.

## Eval policy

1. **Orchestrator** (`claude-sonnet-5` by default in `repo-vend.yaml`) extracts intent — prompt: `evals/extract-intent.json`.
2. **Judge** (`composer-2.5` by default) validates naming/template — prompt: `evals/judge-naming.json` (includes this file). Orchestrator and judge must be different model IDs.
3. **Deterministic gate** must also pass (kebab + pattern + template map). LLM pass alone is not enough.
4. Do not invent missing terraform shape; derive platform via labels, explicit cloud words, or service aliases above. Use **generic** when the request is not clearly terraform or python.
5. Both LLM judge and deterministic gate must pass before opening a Spec PR / commenting a green proposal.
