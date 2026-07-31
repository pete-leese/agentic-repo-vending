# ADR 0001: Jira Automation webhook to Cursor Cloud Automation

## Status

Superseded in part by [ADR 0003](0003-two-phase-propose-keyword-approve-sdd.md) (two-phase propose + Keyword Approval). The webhook transport decision remains accepted.

## Context

Cursor Automations have no native Jira trigger. The workflow must start from Jira without requiring a laptop.

## Decision

Use Jira Automation to POST an HTTP webhook to a Cursor Automation webhook trigger. The cloud agent then runs the CLI for that issue key.

## Consequences

- Near real-time (no cron lag).
- Requires one-time setup of Jira Automation + Cursor webhook URL/auth.
- Payload must include the Jira issue key (and `action` for propose vs vend).
