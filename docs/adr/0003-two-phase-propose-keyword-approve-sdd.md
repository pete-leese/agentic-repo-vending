# ADR 0003: Two-phase propose, keyword approve, hybrid SDD

## Status

Accepted

## Context

The previous flow vended as soon as a ticket hit a HITL label/status gate in one agent run. That made approval coarse (approve-to-create without seeing the resolved name/template) and encouraged post-create rename. Comment *likes* are not a reliable Jira Automation trigger.

## Decision

1. **Propose on create:** Jira Automation fires when an issue is **created** in status **New Request** (`action: propose`). The agent runs evals and posts a structured proposal comment. On eval pass it also opens a PR adding `requests/<ISSUE-KEY>.yaml` (hybrid SDD).
2. **Keyword approval only:** A second rule fires on **issue commented** when the body matches `(?i)\b(approved|lgtm|looks good|ship it|\+1)\b` (`action: vend`). Comment reactions/likes are explicitly out of scope.
3. **Vend from frozen Spec:** On approve, merge the SDD PR (if open) and create-from-template using the YAML on `main`, not a fresh re-extract of the ticket.
4. **No post-create rename:** Wrong name → edit ticket and re-propose before approve, or open a new request after create.

## Consequences

- Humans see name, template, and eval outcome before any GitHub create.
- Spec files under `requests/` are the system of record after merge; ticket text drift after propose does not change the vend.
- Two Jira Automation rules and a Cursor Automation that branches on `action`.
- Control-plane repo needs token rights to open/merge PRs for `requests/*`.
