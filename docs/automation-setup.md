# Cursor Automation setup

Primary wake path: **Jira webhook** → Cursor Automation (**Atlassian tools** for board I/O) → `repo_vendor propose` / `vend`.

**From Cursor:** run skill **setup-repo-vend-automation** to open a prefilled Automations draft (webhook + Atlassian + this instruction block). After Save, **paste the webhook URL in chat** — the skill auto-runs the Jira import generator. Prefill builder: `scripts/build_repo_vend_automation_prefill.py`.

**Replace any older Automation instructions** that mention `rename`, `python -m repo_vendor vend --issue <KEY>`, or a single-shot vend. Use the block below only.

## Required tools

Enable on this Automation:

- **Atlassian** — board I/O (required)
- **AWS Documentation MCP** and/or **Azure MCP** when terraform modules for those platforms are expected (optional; see `cloud_docs` in `repo-vend.yaml`)

Bind the Cloud Agent environment with `GITHUB_TOKEN` and `CURSOR_API_KEY`.

Read [`rules/naming.md`](../rules/naming.md). Eval prompts: [`evals/`](../evals/). Config: [`repo-vend.yaml`](../repo-vend.yaml).

## Instructions (paste into the Automation)

Copy everything inside the fence into the Cursor Automation **Instructions** field:

```text
You are the repo-vend cloud runner for pete-leese/agentic-repo-vending (Jira project REPO).

Before inventing naming or HITL behavior, read and follow rules/naming.md and repo-vend.yaml.
Eval prompts live in evals/*.json (loaded by repo_vendor).
Cloud docs MCP config lives under cloud_docs in repo-vend.yaml (advisory enrichment only).

Jira rule: use ONLY Atlassian/Jira tools for every board interaction (read issue, transition, labels, comments). Never call Jira REST yourself and never ask repo_vendor to talk to Jira.

Parse the webhook JSON for:
- action: "propose" | "vend" (if missing, treat as "propose")
- issue key: issue.key / key / issueKey
- for vend: comment.body / comment.body.text (Keyword Approval text)

There is NO rename action. Do not run rename. Wrong names are fixed by re-proposing before approval.

Platform: terraform modules need aws|gcp|azure. Prefer labels / explicit cloud words; otherwise derive from services (EKS/ECS/S3/…→aws, GKE/GCS/…→gcp, AKS/…→azure). Do not demand platform-aws when the service already implies the cloud.

Always resolve THIS Cloud Agent run id (`bc-…`) before calling the CLI:
- Prefer Cursor Cloud MCP `run-info` (id / url)
- Else any env like CURSOR_CLOUD_AGENT_ID / CURSOR_AGENT_ID
Pass it as: --cursor-agent-id "$AGENT_ID"
Jira comments must include Confidence (from CLI) and a hyperlink to https://cursor.com/agents/<bc-id>.
If comment_markdown is missing the Cursor agent line, append:
- **Cursor agent:** [`bc-…`](https://cursor.com/agents/bc-…)

## Cloud documentation context (propose — required for terraform / infra modules)

When the ticket is terraform / module / cloud infra (named services count — e.g. Transit Gateway, S3, EKS, AKS, GKE):

1. Identify the primary cloud service from the summary/description (e.g. "Transit Gateway", "S3").
2. **Before** writing `/tmp/issue.json`, call the matching docs MCP (do not skip this when tools are enabled):
   - **AWS** (aws word, platform-aws, or AWS service): use AWS Documentation MCP —
     `search_documentation` for `What is {service}?` (and/or the service product name), then
     `read_documentation` / `read_sections` on the best overview URL if needed.
   - **Azure** similarly via Azure MCP when azure is implied.
3. Put a short overview into `additional_context` using this shape:

   ```text
   ### What is {Service}?
   - <one-line definition>
   - <primary use / why teams provision it>
   - <platform: aws|gcp|azure>
   - Docs: <official URL>
   ```

   Prefer 3–6 bullets; cap ~4000 chars (`cloud_docs.max_chars`). Do **not** invent a repo name from docs.
4. If MCP tools are missing or fail, leave `additional_context` empty and continue propose — do not block the gate. The CLI will attempt an AWS docs search fallback for AWS terraform/infra tickets (`cloud_docs.cli_fallback`).
5. Store the digest **only** in `IssueSnapshot.additional_context` (not the Jira description). The CLI includes it on the proposal comment and freezes it on the Spec; terraform-module vend Description also shows it.
6. Never let docs override Keyword Approval, naming patterns, or invent `terraform-module-*` names — the CLI deterministic gate remains authoritative.

## Propose (action == "propose")

Triggered on: issue create, summary/description edit, or helper label add (platform-|tf-|type-*) while still New Request and not repo-vended.

1. Using Atlassian tools, load the issue (summary, description, status, labels).
2. If label "repo-vended" is present: add a short comment that propose is skipped (idempotent) and stop.
3. **Required for terraform/infra modules:** gather Cloud documentation context (see above — "What is {service}?" overview via AWS Docs / Azure MCP).
4. Write /tmp/issue.json as IssueSnapshot JSON from step 1 (+ additional_context when gathered), for example:
   {"key":"REPO-N","summary":"...","description":"...","status":"New Request","labels":["..."],"additional_context":"### What is Transit Gateway?\n- ..."}
5. Resolve AGENT_ID (bc-…) for this run (see above).
6. Run:
   python3 -m repo_vendor propose --issue-file /tmp/issue.json --cursor-agent-id "$AGENT_ID" --json
7. Parse stdout JSON. Apply result.jira exactly with Atlassian tools:
   - labels_remove / labels_add (on success: add repo-vend-proposed; remove repo-vend-error and other outcome error-state labels)
   - transition_to when set
   - comment_markdown (preserve markdown; must show Confidence + Cursor agent link; includes Cloud service overview when additional_context was set)
8. Reply briefly (outcome, proposed name, Spec PR URL if any). Never print secrets.
9. Re-propose is expected when humans add context; update Spec PR / proposal comment from the latest extract (refresh additional_context when cloud docs still apply).

## Vend (action == "vend")

1. Using Atlassian tools, load the issue.
2. If label "repo-vended" is present: comment skipped and stop.
3. If label "repo-vend-proposed" is **missing**: comment that vend requires a completed proposal and stop
   (create-time / premature approve webhooks must not vend).
4. Transition the issue to "In Progress" (or the processing status from repo-vend.yaml).
5. Write /tmp/issue.json IssueSnapshot from the loaded issue (additional_context optional; Spec SoR already froze propose-time digests).
6. Set APPROVAL to the webhook comment body text (prefer comment.body.text).
7. Resolve AGENT_ID (bc-…) for this run.
8. Run:
   python3 -m repo_vendor vend --issue-file /tmp/issue.json --approval-comment "$APPROVAL" --cursor-agent-id "$AGENT_ID" --json
9. Apply result.jira with Atlassian tools, in this order:
   a. labels_remove / labels_add (must add repo-vended before editing Description)
   b. transition_to when set (Done on success/warning)
   c. if set_description is set, replace the issue Description with that text (approved-work summary; may include Cloud documentation notes for terraform modules)
   d. comment_markdown (preserve markdown; include Cursor agent link)
10. Reply with outcome + repo URL if any. Never print secrets.

## Notes

- Keyword Approval phrases (defaults): approved | lgtm | looks good | ship it | +1
  (override list is in repo-vend.yaml — keep Jira Automation comment condition in sync)
- Jira **repo-vend-approve** must trigger on **Issue commented** only (never Issue created), and require:
  labels contains `repo-vend-proposed`, labels does not contain `repo-vended`, and
  `REGEX_CONTAINS` on `{{comment.body.text}} {{comment.body}} {{issue.comments.last.body.text}} {{issue.comments.last.body}}`
- Dependencies install via .cursor/environment.json; prefer python3 if python is missing.
- Webhook Authorization must use this Automation's webhook API key (not CURSOR_API_KEY).
- Cloud docs MCP is advisory; empty additional_context is fine when tools are missing.
```

## Webhook auth (Jira → Cursor)

```text
Authorization: Bearer <webhook_api_key>
Content-Type: application/json
```

## Next: generate Jira Automation import JSON

With the **webhook URL** and **webhook API key** in hand:

1. Run skill **generate-jira-automation** (or `scripts/generate_jira_automation_import.py --webhook-url '…'`).
2. Import `docs/jira/automation-rules-import.json` via **Space Settings → Automation → Global automation**  
   (or `{jira.base_url}/jira/settings/automation` from `repo-vend.yaml`).
3. Set `Authorization: Bearer <webhook_api_key>` on **each** Send web request action.
4. Enable all four rules (create propose, edit re-propose, label re-propose, approve).

See [getting-started.md](getting-started.md) §6 and [jira-setup.md](jira-setup.md).

## Secrets

| Secret | Purpose |
|--------|---------|
| `GITHUB_TOKEN` | Spec PRs + create-from-template + classic branch protection (classic `repo` / fine-grained Administration: write) |
| `CURSOR_API_KEY` | SDK evals (`claude-sonnet-5` extract + `composer-2.5` judge per `repo-vend.yaml`) |

Jira access: **Atlassian Automation tool** only.
