"""Jira Cloud REST client."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from repo_vendor.config import Settings, get_settings

logger = logging.getLogger(__name__)


@dataclass
class JiraIssue:
    key: str
    summary: str
    description: str
    status: str
    labels: list[str]


class JiraClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._client = httpx.Client(
            base_url=self.settings.jira_base_url.rstrip("/"),
            auth=(self.settings.jira_email, self.settings.jira_api_token),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=30.0,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> JiraClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def get_issue(self, key: str) -> JiraIssue:
        r = self._client.get(f"/rest/api/3/issue/{key}")
        r.raise_for_status()
        data = r.json()
        fields = data["fields"]
        return JiraIssue(
            key=data["key"],
            summary=fields.get("summary") or "",
            description=_adf_to_text(fields.get("description")),
            status=(fields.get("status") or {}).get("name") or "",
            labels=list(fields.get("labels") or []),
        )

    def add_comment(self, key: str, body: str) -> None:
        if self.settings.dry_run:
            logger.info("DRY_RUN jira comment %s: %s", key, body)
            return
        payload = {
            "body": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": body}],
                    }
                ],
            }
        }
        r = self._client.post(f"/rest/api/3/issue/{key}/comment", json=payload)
        r.raise_for_status()

    def add_label(self, key: str, label: str) -> None:
        if self.settings.dry_run:
            logger.info("DRY_RUN jira label %s += %s", key, label)
            return
        payload = {"update": {"labels": [{"add": label}]}}
        r = self._client.put(f"/rest/api/3/issue/{key}", json=payload)
        r.raise_for_status()

    def remove_label(self, key: str, label: str) -> None:
        if self.settings.dry_run:
            logger.info("DRY_RUN jira label %s -= %s", key, label)
            return
        payload = {"update": {"labels": [{"remove": label}]}}
        r = self._client.put(f"/rest/api/3/issue/{key}", json=payload)
        if r.status_code == 404:
            return
        r.raise_for_status()

    def set_outcome_label(self, key: str, outcome: str) -> None:
        """Replace prior vend outcome labels with success|warning|error."""
        mapping = {
            "success": self.settings.jira_label_success,
            "warning": self.settings.jira_label_warning,
            "error": self.settings.jira_label_error,
        }
        if outcome not in mapping:
            raise ValueError(f"Unknown outcome: {outcome}")
        for name in mapping.values():
            try:
                self.remove_label(key, name)
            except Exception:  # noqa: BLE001
                logger.debug("Could not remove label %s from %s", name, key, exc_info=True)
        self.add_label(key, mapping[outcome])

    def transition_to(self, key: str, status_name: str) -> bool:
        """Transition issue to a status by display name. Returns False if unavailable."""
        if self.settings.dry_run:
            logger.info("DRY_RUN jira transition %s -> %s", key, status_name)
            return True
        r = self._client.get(f"/rest/api/3/issue/{key}/transitions")
        r.raise_for_status()
        transitions = r.json().get("transitions") or []
        target = status_name.lower()
        match = next(
            (
                t
                for t in transitions
                if (t.get("name") or "").lower() == target
                or ((t.get("to") or {}).get("name") or "").lower() == target
            ),
            None,
        )
        if not match:
            logger.warning(
                "No Jira transition to %r for %s; available=%s",
                status_name,
                key,
                [
                    (t.get("name"), (t.get("to") or {}).get("name"))
                    for t in transitions
                ],
            )
            return False
        tr = self._client.post(
            f"/rest/api/3/issue/{key}/transitions",
            json={"transition": {"id": match["id"]}},
        )
        tr.raise_for_status()
        return True

    def is_approved(self, issue: JiraIssue) -> bool:
        status_ok = issue.status.lower() == self.settings.jira_in_review_status.lower()
        label_ok = self.settings.jira_approved_label in issue.labels
        return status_ok and label_ok

    def is_vended(self, issue: JiraIssue) -> bool:
        return self.settings.jira_vended_label in issue.labels


def _adf_to_text(description: object) -> str:
    if description is None:
        return ""
    if isinstance(description, str):
        return description
    if isinstance(description, dict):
        parts: list[str] = []

        def walk(node: object) -> None:
            if isinstance(node, dict):
                if node.get("type") == "text":
                    parts.append(str(node.get("text") or ""))
                for child in node.get("content") or []:
                    walk(child)
            elif isinstance(node, list):
                for child in node:
                    walk(child)

        walk(description)
        return "\n".join(parts)
    return str(description)
