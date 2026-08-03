# Domain glossary

Ubiquitous language for agentic repo vending. No implementation detail.

## Terms

### Repo Vend Request
A Jira ticket that asks for a new GitHub repository to be created. Expressed via free-flowing description and/or labels. Created in status **New Request**.

### Proposal
The agent's structured understanding of a Repo Vend Request after Eval Checks: proposed Repo Name, Repo Template, eval pass/fail, and reasons. Posted as a Jira comment for humans to read.

### Spec Request
A frozen Spec file at `requests/<ISSUE-KEY>.yaml` on the control-plane repository, opened via pull request during propose. After merge it is the system of record for vend (not a re-read of the live ticket text).

### Keyword Approval
The HITL gate for create: a human comments on the ticket with an approval phrase such as **approved**, **lgtm**, **looks good**, **ship it**, or **+1**. Comment likes/reactions are not used.

### Repo Template
A GitHub template repository used as the basis for a vended repo. MVP templates: **Terraform Repo Template** and **Python Repo Template**.

### Terraform Repo Template
The public template named `template-terraform-repo`, used when the request is for Terraform work.

### Python Repo Template
The public template named `template-python-repo`, used when the request is for Python work.

### Generic Repo Template
The public template named `template-generic-repo`, used when the request is not specifically Terraform or Python (or when configured as the default fallback).

### Vended Repo
A new public GitHub repository created from a Repo Template after Keyword Approval and create-from-template. The vendor rewrites the README so it describes the project rather than the template.

### Repo Name
The final GitHub repository name, always in **kebab-case**. Snake_case, spaces, and mixed case are normalized to kebab-case before checks.

### Terraform Module Name
Pattern: `terraform-module-<name>-<platform>` (example: `terraform-module-s3-bucket-aws`).

### Terraform Root Name
Pattern: `terraform-<name>` for non-module (root) projects (example: `terraform-eks-gitops-management`).

### Python Repo Name
Pattern: `python-<purpose-kebab>` (example: `python-invoice-parser`).

### Generic Repo Name
Plain kebab-case without `terraform-` or `python-` prefixes (example: `billing-gateway`).

### Eval Check
A judgment that the proposed Repo Name and chosen Repo Template match the Repo Vend Request. Uses a model distinct from the orchestrator, plus deterministic naming rules. Both must pass before a Spec Request PR is opened.

### Deterministic Gate
Non-LLM rules (kebab-case and naming patterns, template mapping). A failure here blocks propose (no Spec PR) even if the LLM eval judge passes.

### Repo Vended Marker
The Jira label **`repo-vended`**, applied after a successful create. Prevents duplicate vending (idempotency).

### Vend Outcome Labels
Result labels applied at the end of a propose or vend run:
- **`repo-vend-proposed`** — Spec PR opened; waiting for Keyword Approval
- **`repo-vend-success`** — repo created and `main` branch protection applied
- **`repo-vend-warning`** — repo created but a non-fatal step failed (e.g. branch protection)
- **`repo-vend-error`** — propose or vend did not complete

### Vend Status Flow
Create in **New Request** → propose (comment + optional Spec PR) → Keyword Approval → **In Progress** while creating → **Done** on success/warning. On error, leave actionable comment; human fixes ticket and re-triggers propose as needed.

### Jira Board I/O
All reads and writes to the Jira board (issue fetch, transitions, labels, comments) are performed by the Cursor Automation using **Atlassian tools**. The CLI returns a **Jira update plan** (JSON) for the Automation to apply; it does not call Jira itself.

### Cloud Documentation Context
Optional factual digest gathered by the Cloud Agent (AWS Documentation MCP, Azure MCP, or similar) and passed as `IssueSnapshot.additional_context`. Used to improve propose/eval understanding and, for terraform modules, the post-vend board Description. Never overrides naming rules or Keyword Approval.
