# Domain glossary

Ubiquitous language for agentic repo vending. No implementation detail.

## Terms

### Repo Vend Request
A Jira ticket that asks for a new GitHub repository to be created. Expressed via free-flowing description and/or labels.

### Human Approval
The gate that allows vending: the ticket is in **In Review** and carries the label **`repo-vend-approved`**.

### Repo Template
A GitHub template repository used as the basis for a vended repo. MVP templates: **Terraform Repo Template** and **Python Repo Template**.

### Terraform Repo Template
The public template named `template-terraform-repo`, used when the request is for Terraform work.

### Python Repo Template
The public template named `template-python-repo`, used when the request is for Python work.

### Vended Repo
A new public GitHub repository created from a Repo Template after evals pass.

### Repo Name
The final GitHub repository name, always in **kebab-case**. Snake_case, spaces, and mixed case are normalized to kebab-case before checks.

### Terraform Module Name
Pattern: `terraform-module-<name>-<platform>` (example: `terraform-module-s3-bucket-aws`).

### Terraform Root Name
Pattern: `terraform-<name>` for non-module (root) projects (example: `terraform-eks-gitops-management`).

### Python Repo Name
Pattern: `python-<purpose-kebab>` (example: `python-invoice-parser`).

### Eval Check
A judgment that the proposed Repo Name and chosen Repo Template match the Repo Vend Request. Uses a model distinct from the orchestrator, plus deterministic naming rules. Both must pass.

### Deterministic Gate
Non-LLM rules (kebab-case and naming patterns, template mapping). A failure here blocks vending even if the LLM eval judge passes.

### Rename Request
After a successful vend, a human may comment a new desired name. The system re-runs Eval Checks and renames the Vended Repo if checks pass.

### Repo Vended Marker
The Jira label **`repo-vended`**, applied after a successful create. Prevents duplicate vending (idempotency).
