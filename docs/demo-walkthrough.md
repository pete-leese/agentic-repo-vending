# Demo walkthrough

Use this script to show the MVP end-to-end.

## Prep checklist

- [ ] Templates published and marked as GitHub templates
- [ ] Cloud Agent secrets set (`CURSOR_API_KEY`, `GITHUB_TOKEN`, Jira)
- [ ] Cursor Automation webhook URL pasted into Jira Automation
- [ ] Labels `repo-vend-approved` / `repo-vended` available
- [ ] Fresh `CURSOR_API_KEY` (never reuse a key pasted into chat)

## Path A — Happy path (Terraform module)

1. Create Jira issue in KAN:
   - **Summary:** Terraform S3 module for AWS
   - **Description:** `I need a new repo for a terraform module for S3 bucket for my aws platform`
2. Move to **In Review**
3. Add label **`repo-vend-approved`**
4. Expect within ~1–2 minutes:
   - Comment with repo URL for `terraform-module-s3-bucket-aws` (or normalized equivalent)
   - Label **`repo-vended`**
   - Public repo under `pete-leese` created from `template-terraform-repo`
   - `main` protected (PR required)
5. Open the repo — show Actions workflow + pre-commit + sample module

### Talking points

- Free-flowing English was enough (labels optional)
- Eval used **`composer-2`**; orchestration **`composer-2.5`**
- Deterministic gate enforces kebab + pattern

## Path B — Eval failure then fix

1. Create issue: **Summary** `Need a repo` / **Description** `something for infra maybe`
2. In Review + `repo-vend-approved`
3. Expect comment listing missing type / shape / platform / purpose — **no GitHub repo**
4. Edit description to a clear Terraform module request (or add labels `type-terraform`, `tf-module`, `platform-aws`)
5. Re-trigger (re-add label or transition again per your Jira rule)
6. Expect successful vend

## Path C — Python + rename

1. Ticket: `Create a python invoice parser service`
2. Approve → vend → expect `python-invoice-parser` (or similar kebab)
3. Comment: `Please rename to python-invoice-parser-cli`
4. Trigger rename automation (or run locally):

```bash
python -m repo_vendor rename \
  --issue KAN-XX \
  --current-name python-invoice-parser \
  --comment "Please rename to python-invoice-parser-cli"
```

5. Expect re-eval + rename + updated comment

## Path D — Idempotency

Re-fire vend on an already `repo-vended` ticket → agent skips create and reports idempotent skip.

## Dry-run without cloud

```bash
export ALLOW_LLM_FALLBACK=true
export DRY_RUN=true
# Still needs Jira credentials to fetch the issue unless you mock
python -m repo_vendor vend --issue KAN-XX --dry-run
```

Without `CURSOR_API_KEY`, heuristic extract + deterministic gate still run (`ALLOW_LLM_FALLBACK=true`).
