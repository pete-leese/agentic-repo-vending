# Repo vend naming and eval rules

Single source of truth for humans and the Cursor Automation. Board URLs, approval keyword *lists*, and template **repo names** are configured in [`repo-vend.yaml`](../repo-vend.yaml) — see [`docs/customizing.md`](../docs/customizing.md). LLM evals load `/evals/*.json` and inject this file into the judge.

## Two-phase HITL

1. **Propose** — Issue **created** in **New Request** → agent runs evals → Jira proposal comment. On pass, opens PR `requests/<ISSUE-KEY>.yaml`. Proposed names must be **unique** across Spec Requests under `requests/` (and must not collide with an existing GitHub repo of the same name); duplicates fail propose with an explicit comment.
2. **Re-propose (more context)** — While still **New Request** and **not** `repo-vended`, editing **summary/description** or adding a helper label (`platform-*` / `tf-*` / `type-*`) re-triggers `action: propose`. Outcome labels (`repo-vend-*`) do **not** re-trigger.
3. **Approve** — Human replies with a Keyword Approval phrase (from `repo-vend.yaml` → `jira.approval.keywords`) **after** `repo-vend-proposed` is present → agent merges Spec PR → create-from-template. The approve Automation must **not** run on issue create.
4. **No rename after create** — Wrong name: edit the ticket and re-propose before approve, or open a new request.

### Keyword Approval (defaults)

Default phrases (override in `repo-vend.yaml`):

`approved` | `lgtm` | `looks good` | `ship it` | `+1`

Comment likes/reactions are **not** used. Keep the Jira Automation comment condition in sync when you change keywords.

### Labels

| Label | Meaning |
|-------|---------|
| **`repo-vend-proposed`** | Spec PR opened; proposal ready for Keyword Approval (clears prior error-state labels) |
| **`repo-vended`** | Repo already created — do not create again |
| **`repo-vend-success`** | Created and `main` protection applied |
| **`repo-vend-warning`** | Repo created but a non-fatal step failed (e.g. branch protection / README rewrite) |
| **`repo-vend-error`** | Propose or vend did not complete |

Status flow: **New Request** (create / re-propose) → propose → Keyword Approval → **In Progress** while vending → **Done** on success/warning. After a successful vend, the agent replaces the issue **Description** with a short summary of what was approved and created (repo URL, template, type/platform). For **terraform modules**, that summary may also include propose-time **Cloud documentation notes** when the Cloud Agent supplied `additional_context` (AWS Docs / Azure MCP, etc.) — advisory only; it does not change naming or HITL.

## Helper labels (optional)

| Label | Meaning |
|-------|---------|
| `type-terraform` / `type-python` / `type-generic` | Project type |
| `tf-module` / `tf-root` | Terraform shape |
| `platform-aws` / `platform-gcp` / `platform-azure` | Cloud platform (modules); often optional when the service implies a cloud |

## Naming (always kebab-case)

Snake_case, spaces, and CamelCase are normalized to kebab-case before checks.

**Machine-enforced patterns** live in [`rules/deterministic.yaml`](deterministic.yaml) (regexes, platforms, purpose stopwords, service→platform aliases). Edit that file to change the gate — do not hardcode patterns in Python. This markdown is the human/HITL explanation; keep it aligned when you change the YAML.

| Type | Pattern | Example | When |
|------|---------|---------|------|
| Terraform module | `terraform-module-<name>-<platform>` | `terraform-module-s3-bucket-aws` | Terraform / infra module (incl. “EC2 module…”, “S3 module…”) |
| Terraform root | `terraform-<name>` | `terraform-eks-gitops-management` | Terraform root / project |
| Python | `python-<purpose-kebab>` | `python-invoice-parser` | Clearly a Python app/library |
| **Generic** | **plain kebab only** (no `terraform-` / `python-` prefix, no required platform suffix) | `billing-gateway` | **Fallback** when the request is not clearly terraform or python |

### Type selection / fallback

1. **Terraform** — labels `type-terraform` / `tf-module` / `tf-root`, the word terraform, **or** infra phrasing (`module` + cloud service/platform such as EC2, S3, EKS, aws/gcp/azure). The bare word **“project”** is **not** terraform (e.g. “repo for my project invoices-service” → **generic**).
2. **Python** — `type-python` or clear python intent.
3. **Generic (default)** — everything else, via `github.default_project_type` in `repo-vend.yaml` (default **generic**).

Generic uses **`template-generic-repo`** and is **not** held to terraform/python naming standards — only plain kebab-case. Do not invent a `terraform-module-…` name and then score it as generic (that was the EC2 failure mode). Do not invent `terraform-<name>` for an unclear service name when the judge says generic (REPO-16).

When the **eval judge** returns a `proposed_name` / `template`, those override a conflicting extract before the deterministic gate — proposal **name**, **template**, and **reasons** must stay aligned.

Platforms: `aws` | `gcp` | `azure` (required for **terraform modules** only; not for generic).

### Platform from service name

When `platform-*` / `aws|gcp|azure` is absent, derive platform from cloud-specific services listed under `platform_service_aliases` in [`rules/deterministic.yaml`](deterministic.yaml) (examples below):

| Service (examples) | Platform |
|--------------------|----------|
| EKS, ECS, EC2, S3, RDS, Lambda, DynamoDB, SQS, SNS, CloudFront, Route53, Transit Gateway / TGW | `aws` |
| GKE, GCS, BigQuery, Cloud Run, GCE, Pub/Sub | `gcp` |
| AKS, Azure AD, Cosmos DB | `azure` |

Example: summary `terraform module for EKS` + label `tf-module` → platform `aws` → `terraform-module-eks-…-aws` (no `platform-aws` label required).

Phrases like **“EC2 module repo for aws”** or **“S3 module”** (without the word terraform) still mean **terraform + module**, not generic.

## Templates

Configured under `github.templates` in `repo-vend.yaml` (defaults below):

| Project type | GitHub template |
|--------------|-----------------|
| Terraform | `template-terraform-repo` |
| Python | `template-python-repo` |
| Generic | `template-generic-repo` |

After create-from-template, the vendor **rewrites `README.md`** on the new repo so it describes the project (not the template).

## Spec Request (SDD)

Path: `requests/<ISSUE-KEY>.yaml` on the control-plane repo. Frozen after propose; **vend reads this file**, not a fresh ticket extract. Re-propose updates the Spec PR from the latest ticket. **Propose** rejects a name already claimed by another Spec under `requests/` (or an existing GitHub repo of that name).

## Eval policy

1. **Orchestrator** (`claude-sonnet-5` by default in `repo-vend.yaml`) extracts intent — prompt: `evals/extract-intent.json`.
2. **Judge** (`composer-2.5` by default) validates naming/template — prompt: `evals/judge-naming.json` (includes this file). Orchestrator and judge must be different model IDs.
3. **Deterministic gate** must also pass (kebab + pattern + template map from [`rules/deterministic.yaml`](deterministic.yaml)). LLM pass alone is not enough.
4. Do not invent missing terraform shape; derive platform via labels, explicit cloud words, or service aliases in the YAML. Use **generic** (plain kebab + `template-generic-repo`) when the request is not clearly terraform or python — generic is **not** subject to terraform/python naming patterns.
5. Both LLM judge and deterministic gate must pass before opening a Spec PR / commenting a green proposal.
