# ADR 0001: Jira Automation webhook to Cursor Cloud Automation

## Status

Accepted

## Context

Cursor Automations have no native Jira trigger. The workflow must start when a ticket is In Review and labeled `repo-vend-approved`, without requiring a laptop.

## Decision

Use Jira Automation to POST an HTTP webhook to a Cursor Automation webhook trigger whenever the HITL gate is satisfied. The cloud agent then runs the PydanticAI CLI for that issue key.

## Consequences

- Near real-time vending (no cron lag).
- Requires one-time setup of Jira Automation + Cursor webhook URL/auth.
- Payload must include the Jira issue key.
