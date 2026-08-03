---
name: setup-repo-vend-automation
description: >-
  Create or refresh the Cursor Webhook Automation for agentic-repo-vending
  (propose/vend), then automatically generate importable Jira Automation JSON
  when the user pastes the webhook URL. Use when the user asks to set up the
  Cursor Automation from Cursor, open a prefilled Automations draft, wire
  Jira→Cursor end-to-end, or run setup-repo-vend-automation.
disable-model-invocation: false
---

# Setup repo-vend Cursor Automation

## What is possible

Cursor can **open a prefilled Automations draft** from chat (`open_automation`).  
It **cannot** fully save the Automation or return the webhook URL/API key without the UI — those appear only **after the user clicks Save** in the Automations editor.

**End-to-end flow (one skill):** prefill → open editor → user Saves → user pastes webhook URL in chat → **automatically** run the same steps as skill **generate-jira-automation** (no second skill invoke).

## Instructions

### Phase A — Prefill and open the Automations editor

1. Confirm finish path: `cursor-app-control` / `open_automation` must be available (Agents Window). If missing, say: use this skill in the **Agents Window**, and fall back to pasting instructions from `docs/automation-setup.md` manually at cursor.com/automations.

2. Build prefill JSON from the repo (instructions come from `docs/automation-setup.md`):

```bash
python3 scripts/build_repo_vend_automation_prefill.py
```

3. Show a short draft table (plain language):

| Field | Value |
|-------|--------|
| Name | repo-vend |
| Trigger | Incoming HTTP webhook |
| Tools | Atlassian MCP (+ optional AWS Docs / Azure MCP from `cloud_docs` in `repo-vend.yaml`) |
| Repo / branch | From prefill `gitConfig` (usually pete-leese/agentic-repo-vending @ main) |
| Instructions | From docs/automation-setup.md (propose/vend only; no rename; optional cloud-docs enrichment) |
| To finish in editor | Save; copy webhook URL + webhook API key; bind Cloud Agent env; confirm Atlassian + cloud-docs MCPs |

4. Ask: “Does this look correct? Ready for me to open the Automations editor?”

5. On yes, call **`open_automation`** with `prefillWorkflowData` set to the JSON object from step 2 (parse the script stdout). Do not invent webhook URLs.

6. Immediately after opening the editor, tell the user clearly:

> Save the Automation, then **paste the Webhook URL here** (the `https://api2.cursor.sh/automations/webhook/…` value).  
> I’ll generate the Jira import JSON automatically from that URL.  
> Also copy the **Webhook API key** — you’ll need it for the `Authorization: Bearer …` header in Jira (not `CURSOR_API_KEY`).

Do **not** wait for them to run **generate-jira-automation**. This skill continues into Phase B as soon as a valid URL appears in chat.

### Phase B — Auto-generate Jira import (on URL paste)

7. Treat the **next message that contains** a URL matching  
   `https://api2.cursor.sh/automations/webhook/<id>`  
   as the handoff signal. Do not invent or substitute example URLs.

8. **Without asking them to invoke another skill**, follow [`.agents/skills/generate-jira-automation/SKILL.md`](../generate-jira-automation/SKILL.md) from step 2 onward (run the generator, print import + Authorization instructions). In short:

```bash
python3 scripts/generate_jira_automation_import.py --webhook-url '<PASTED_URL>'
```

9. From the script JSON stdout, print:
   - Generated path (`out`, usually `docs/jira/automation-rules-import.json`)
   - Import: **Space Settings → Automation → Global automation**, or `{jira.base_url}/jira/settings/automation` from `repo-vend.yaml`
   - For **each** Send web request POST: `Authorization: Bearer <webhook_api_key>` (placeholder in JSON is `REPLACE_WITH_CURSOR_WEBHOOK_API_KEY`)
   - Enable all four rules; disable any old one-shot vend rule

10. If they paste only the API key (no URL), ask again for the webhook URL. If they already have an Automation and only need JSON, they may paste the URL immediately — skip Phase A open if they say so, and jump to Phase B.

11. Do not commit real Bearer tokens.

## MCP name note

Prefill uses MCP `serverName` **`Atlassian`** by default, plus enabled `cloud_docs.providers.*.mcp_server` names from `repo-vend.yaml`. If the Automations editor shows different catalog names, re-run:

```bash
python3 scripts/build_repo_vend_automation_prefill.py \
  --atlassian-server-name '<exact catalog name>' \
  --mcp-server '<aws-docs-catalog-name>' \
  --mcp-server '<azure-catalog-name>'
```

and open the editor again. Only dashboard-eligible MCP servers can be prefilled.

## Related

- Instructions source: `docs/automation-setup.md`
- Chained skill (URL → JSON): `generate-jira-automation` (invoked automatically here; standalone if URL already known)
- Export pitfalls: `.cursor/rules/jira-automation-export.mdc`
