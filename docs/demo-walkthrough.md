# Demo walkthrough

## Prep checklist

- [ ] Templates published (`./scripts/publish_templates.sh`)
- [ ] Secrets: `CURSOR_API_KEY`, `GITHUB_TOKEN`
- [ ] Cursor Webhook Automation + Atlassian tool (skill **setup-repo-vend-automation**, or [automation-setup.md](automation-setup.md))
- [ ] Jira rules imported via skill / `scripts/generate_jira_automation_import.py` (or **generate-jira-automation**)
- [ ] Both rules’ **Send web request** have `Authorization: Bearer <webhook_api_key>`
- [ ] Labels `repo-vend-proposed` / `repo-vended` available

## Path A — Happy path (Terraform module)

1. Create Jira issue in **New Request**:
   - **Summary:** Terraform S3 module for AWS
   - **Description:** `I need a new repo for a terraform module for S3 bucket for my aws platform`
2. Expect propose comment: evals PASSED, proposed name, template, Spec PR link
3. Reply to the proposal with **`lgtm`** (threaded reply OK) — or a new top-level comment with the same keyword
4. Expect: Spec PR merged, public repo created, `repo-vended`, **Done**

## Path B — Eval failure then fix

1. Create issue: **Summary** `Need a repo` / **Description** `something for infra maybe`
2. Expect proposal **failed** comment — **no Spec PR**
3. Edit description (or add labels), create a **new** ticket or re-fire propose
4. Approve with `lgtm` after a green proposal

## Path C — Python

1. Ticket: `Create a python invoice parser service` in New Request
2. Propose → expect `python-invoice-parser` (or similar)
3. Reply `approved` → vend
4. No rename path — wrong name means re-propose before approve

## Path D — Idempotency

Re-fire vend on an already `repo-vended` ticket → skip create.

## Dry-run locally

```bash
export ALLOW_LLM_FALLBACK=true
export DRY_RUN=true
cat > /tmp/issue.json <<'EOF'
{"key":"KAN-XX","summary":"python logging helper","description":"A small python utility","status":"New Request","labels":["type-python"]}
EOF
python -m repo_vendor propose --issue-file /tmp/issue.json --json --dry-run
```
