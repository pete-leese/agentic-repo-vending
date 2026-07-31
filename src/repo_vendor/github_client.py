"""GitHub API client for template-based repo creation and guardrails."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from repo_vendor.config import Settings, get_settings

logger = logging.getLogger(__name__)


@dataclass
class CreatedRepo:
    name: str
    html_url: str
    full_name: str


class GitHubClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._client = httpx.Client(
            base_url="https://api.github.com",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.settings.github_token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=60.0,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> GitHubClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def repo_exists(self, name: str) -> bool:
        r = self._client.get(f"/repos/{self.settings.github_owner}/{name}")
        if r.status_code == 404:
            return False
        r.raise_for_status()
        return True

    def create_from_template(self, *, template: str, name: str, description: str = "") -> CreatedRepo:
        if self.settings.dry_run:
            url = f"https://github.com/{self.settings.github_owner}/{name}"
            logger.info("DRY_RUN create from %s -> %s", template, url)
            return CreatedRepo(name=name, html_url=url, full_name=f"{self.settings.github_owner}/{name}")

        payload = {
            "owner": self.settings.github_owner,
            "name": name,
            "description": description or f"Vended from {template}",
            "include_all_branches": False,
            "private": False,
        }
        r = self._client.post(
            f"/repos/{self.settings.github_owner}/{template}/generate",
            json=payload,
        )
        if r.status_code >= 400:
            logger.error("GitHub create failed: %s %s", r.status_code, r.text)
        r.raise_for_status()
        data = r.json()
        return CreatedRepo(
            name=data["name"],
            html_url=data["html_url"],
            full_name=data["full_name"],
        )

    def protect_main(self, name: str) -> None:
        """Enforce no direct pushes to main (PR required)."""
        if self.settings.dry_run:
            logger.info("DRY_RUN branch protection main on %s", name)
            return
        payload = {
            "required_status_checks": None,
            "enforce_admins": True,
            "required_pull_request_reviews": {
                "required_approving_review_count": 1,
                "dismiss_stale_reviews": True,
            },
            "restrictions": None,
            "allow_force_pushes": False,
            "allow_deletions": False,
        }
        r = self._client.put(
            f"/repos/{self.settings.github_owner}/{name}/branches/main/protection",
            json=payload,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.settings.github_token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        # Personal accounts may need classic PAT with repo admin; log soft failure
        if r.status_code >= 400:
            logger.warning(
                "Could not set branch protection on %s: %s %s",
                name,
                r.status_code,
                r.text,
            )
            return
        r.raise_for_status()

    def rename_repo(self, current_name: str, new_name: str) -> CreatedRepo:
        if self.settings.dry_run:
            url = f"https://github.com/{self.settings.github_owner}/{new_name}"
            logger.info("DRY_RUN rename %s -> %s", current_name, new_name)
            return CreatedRepo(
                name=new_name,
                html_url=url,
                full_name=f"{self.settings.github_owner}/{new_name}",
            )
        r = self._client.patch(
            f"/repos/{self.settings.github_owner}/{current_name}",
            json={"name": new_name},
        )
        r.raise_for_status()
        data = r.json()
        return CreatedRepo(
            name=data["name"],
            html_url=data["html_url"],
            full_name=data["full_name"],
        )

    def ensure_template_flag(self, name: str) -> None:
        if self.settings.dry_run:
            logger.info("DRY_RUN mark %s as template", name)
            return
        r = self._client.patch(
            f"/repos/{self.settings.github_owner}/{name}",
            json={"is_template": True},
        )
        r.raise_for_status()
