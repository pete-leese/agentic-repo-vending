# ADR 0003: Prefer cron scan over Jira webhook for default trigger

## Status

Accepted

## Context

Cursor Automations have no native Jira trigger. A Jira Automation → webhook path works but is high friction for demos. Atlassian MCP cannot wake a Cloud Agent. Cursor-in-Jira (assign `@Cursor`) is lowest friction but Teams/Enterprise-only.

## Decision

Document three wake paths and default new setups to **scheduled `repo_vendor scan`** (JQL for In Review + `repo-vend-approved` without `repo-vended`). Keep webhook as an optional low-latency path. Treat MCP as runtime Jira tooling, not a trigger.

## Consequences

- Simpler onboarding: one Cursor Automation, no Jira Automation required.
- Vend latency bounded by cron interval.
- Webhook URL still valid for users who already configured Path C.
