---
name: generate-jira-automation
description: >-
  Generate an importable Jira Automation JSON for the two-phase propose/vend
  flow from a Cursor Automation webhook URL and repo-vend.yaml. Use when the
  user asks to generate/export Jira automation rules, wire a Cursor webhook into
  Jira, or produce docs/jira/*.json for import.
disable-model-invocation: false
---

# Generate Jira Automation import JSON

## Instructions

1. **Ask the user** for their Cursor Automation **webhook URL** (the full HTTPS URL from the Automation’s webhook trigger after Save).  
   - Do **not** invent or paste example webhook URLs or IDs into chat or into this skill’s outputs.  
   - Accept only a URL matching `https://api2.cursor.sh/automations/webhook/<id>`.

2. From the repo root, run:

```bash
python3 scripts/generate_jira_automation_import.py --webhook-url '<USER_PROVIDED_URL>'
```

   Optional: `--out docs/jira/automation-rules-import.json` (default).

3. Read the script’s JSON stdout for `out`, `automation_settings_url`, and `base_url` (derived from [`repo-vend.yaml`](../../repo-vend.yaml) `jira.base_url`).

4. Tell the user clearly (use their real paths/URLs from the script output):

### Generated file
- Path: the `out` value (usually `docs/jira/automation-rules-import.json`)
- Rules: `repo-vend-propose` (issue created → propose) and `repo-vend-approve` (Keyword Approval comment → vend)

### Authorization header (required after import)
For **each** rule’s **Send web request** (POST) action:
1. Open the rule → **Send web request**
2. Set header **`Authorization`** to:

```text
Bearer <webhook_api_key_from_this_Cursor_Automation>
```

Use the **webhook API key** shown for that Cursor Automation (not the global Cloud Agent `CURSOR_API_KEY`).  
The generated JSON uses placeholder `Bearer REPLACE_WITH_CURSOR_WEBHOOK_API_KEY` — replace it in Jira after import (or before import if editing the file).

### How to import
1. Open **Space Settings → Automation → Global automation**, **or** go directly to:

```text
{jira.base_url from repo-vend.yaml}/jira/settings/automation
```

   Example shape (site from config): `{base_url}/jira/settings/automation`

2. **⋯ → Import rules** (or **Import flows**), upload the generated JSON.
3. Select both rules, finish import (they arrive **disabled**).
4. Set the **Authorization** Bearer on both Send web request actions.
5. **Enable** both rules; disable/delete any superseded one-shot vend rule.
6. Follow [`.cursor/rules/jira-automation-export.mdc`](../../.cursor/rules/jira-automation-export.mdc) if hand-editing the JSON (valid UUIDs, `CONTAINS_NONE` not invented operators).

5. Do not commit real Bearer tokens. The placeholder in JSON is fine to commit; keys are not.

## Examples

User: “Generate Jira automation JSON for my Cursor webhook”

Agent: asks for webhook URL → runs script → prints file path + Authorization warning + import URL from `repo-vend.yaml`.
