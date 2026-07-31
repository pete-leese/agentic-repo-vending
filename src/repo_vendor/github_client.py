"""GitHub API client: template create, branch protection, Spec Request PRs."""

from __future__ import annotations

import base64
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


@dataclass
class PullRequestInfo:
    number: int
    html_url: str
    merged: bool
    state: str
    head_ref: str


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

    @property
    def _control(self) -> str:
        return f"{self.settings.github_owner}/{self.settings.control_plane_repo}"

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
            return CreatedRepo(
                name=name, html_url=url, full_name=f"{self.settings.github_owner}/{name}"
            )

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

    def protect_main(self, name: str) -> bool:
        """Enforce no direct pushes to main (PR required). Returns True if applied."""
        if self.settings.dry_run:
            logger.info("DRY_RUN branch protection main on %s", name)
            return True
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
        )
        if r.status_code >= 400:
            logger.warning(
                "Could not set branch protection on %s: %s %s",
                name,
                r.status_code,
                r.text,
            )
            return False
        r.raise_for_status()
        return True

    def ensure_template_flag(self, name: str) -> None:
        if self.settings.dry_run:
            logger.info("DRY_RUN mark %s as template", name)
            return
        r = self._client.patch(
            f"/repos/{self.settings.github_owner}/{name}",
            json={"is_template": True},
        )
        r.raise_for_status()

    def _default_branch(self) -> str:
        r = self._client.get(f"/repos/{self._control}")
        r.raise_for_status()
        return str(r.json().get("default_branch") or "main")

    def _ref_sha(self, ref: str) -> str:
        r = self._client.get(f"/repos/{self._control}/git/ref/heads/{ref}")
        r.raise_for_status()
        return str(r.json()["object"]["sha"])

    def create_branch(self, branch: str, from_branch: str | None = None) -> None:
        if self.settings.dry_run:
            logger.info("DRY_RUN create branch %s", branch)
            return
        base = from_branch or self._default_branch()
        sha = self._ref_sha(base)
        r = self._client.post(
            f"/repos/{self._control}/git/refs",
            json={"ref": f"refs/heads/{branch}", "sha": sha},
        )
        if r.status_code == 422 and "already exists" in r.text.lower():
            return
        r.raise_for_status()

    def put_file(
        self,
        *,
        path: str,
        content: str,
        branch: str,
        message: str,
        repo: str | None = None,
    ) -> None:
        """Create or update a file on the control-plane repo (default) or another repo name."""
        full = f"{self.settings.github_owner}/{repo}" if repo else self._control
        if self.settings.dry_run:
            logger.info("DRY_RUN put file %s on %s@%s", path, full, branch)
            return
        encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
        payload: dict = {
            "message": message,
            "content": encoded,
            "branch": branch,
        }
        existing = self._client.get(
            f"/repos/{full}/contents/{path}",
            params={"ref": branch},
        )
        if existing.status_code == 200:
            payload["sha"] = existing.json()["sha"]
        r = self._client.put(f"/repos/{full}/contents/{path}", json=payload)
        r.raise_for_status()

    def write_vended_readme(
        self,
        *,
        repo_name: str,
        content: str,
        branch: str = "main",
    ) -> bool:
        """Replace README.md on a newly vended repo. Returns False on soft failure."""
        try:
            self.put_file(
                path="README.md",
                content=content,
                branch=branch,
                message="Initialize project README after vend",
                repo=repo_name,
            )
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not update README on %s: %s", repo_name, exc)
            return False

    def create_pull_request(
        self,
        *,
        title: str,
        body: str,
        head: str,
        base: str | None = None,
    ) -> PullRequestInfo:
        if self.settings.dry_run:
            url = f"https://github.com/{self._control}/pull/0"
            logger.info("DRY_RUN open PR %s -> %s", head, base or "main")
            return PullRequestInfo(
                number=0, html_url=url, merged=False, state="open", head_ref=head
            )
        base_branch = base or self._default_branch()
        r = self._client.post(
            f"/repos/{self._control}/pulls",
            json={"title": title, "body": body, "head": head, "base": base_branch},
        )
        if r.status_code == 422:
            # PR may already exist for this head — refresh title/body on re-propose
            existing = self.find_open_pr(head_ref=head)
            if existing:
                return self.update_pull_request(
                    existing.number, title=title, body=body
                )
        r.raise_for_status()
        data = r.json()
        return PullRequestInfo(
            number=int(data["number"]),
            html_url=str(data["html_url"]),
            merged=bool(data.get("merged")),
            state=str(data.get("state") or "open"),
            head_ref=head,
        )

    def update_pull_request(
        self,
        number: int,
        *,
        title: str | None = None,
        body: str | None = None,
    ) -> PullRequestInfo:
        if self.settings.dry_run:
            return PullRequestInfo(
                number=number,
                html_url=f"https://github.com/{self._control}/pull/{number}",
                merged=False,
                state="open",
                head_ref="",
            )
        payload: dict[str, str] = {}
        if title is not None:
            payload["title"] = title
        if body is not None:
            payload["body"] = body
        if payload:
            r = self._client.patch(
                f"/repos/{self._control}/pulls/{number}",
                json=payload,
            )
            r.raise_for_status()
            data = r.json()
        else:
            get_r = self._client.get(f"/repos/{self._control}/pulls/{number}")
            get_r.raise_for_status()
            data = get_r.json()
        return PullRequestInfo(
            number=int(data["number"]),
            html_url=str(data["html_url"]),
            merged=bool(data.get("merged")),
            state=str(data.get("state") or "open"),
            head_ref=str(data.get("head", {}).get("ref") or ""),
        )

    def find_open_pr(self, *, head_ref: str) -> PullRequestInfo | None:
        head = f"{self.settings.github_owner}:{head_ref}"
        r = self._client.get(
            f"/repos/{self._control}/pulls",
            params={"state": "open", "head": head},
        )
        r.raise_for_status()
        items = r.json()
        if not items:
            return None
        data = items[0]
        return PullRequestInfo(
            number=int(data["number"]),
            html_url=str(data["html_url"]),
            merged=False,
            state="open",
            head_ref=head_ref,
        )

    def merge_pull_request(self, number: int) -> PullRequestInfo:
        if self.settings.dry_run:
            logger.info("DRY_RUN merge PR #%s", number)
            return PullRequestInfo(
                number=number,
                html_url=f"https://github.com/{self._control}/pull/{number}",
                merged=True,
                state="closed",
                head_ref="",
            )
        r = self._client.put(
            f"/repos/{self._control}/pulls/{number}/merge",
            json={"merge_method": "squash"},
        )
        if r.status_code == 405:
            # already merged
            get_r = self._client.get(f"/repos/{self._control}/pulls/{number}")
            get_r.raise_for_status()
            data = get_r.json()
            return PullRequestInfo(
                number=number,
                html_url=str(data["html_url"]),
                merged=bool(data.get("merged")),
                state=str(data.get("state") or "closed"),
                head_ref=str(data.get("head", {}).get("ref") or ""),
            )
        r.raise_for_status()
        get_r = self._client.get(f"/repos/{self._control}/pulls/{number}")
        get_r.raise_for_status()
        data = get_r.json()
        return PullRequestInfo(
            number=number,
            html_url=str(data["html_url"]),
            merged=True,
            state="closed",
            head_ref=str(data.get("head", {}).get("ref") or ""),
        )

    def get_file_text(self, path: str, *, ref: str | None = None) -> str:
        if self.settings.dry_run:
            raise FileNotFoundError(f"DRY_RUN: no remote file {path}")
        params = {"ref": ref} if ref else None
        r = self._client.get(f"/repos/{self._control}/contents/{path}", params=params)
        if r.status_code == 404:
            raise FileNotFoundError(path)
        r.raise_for_status()
        data = r.json()
        if data.get("encoding") == "base64":
            return base64.b64decode(data["content"]).decode("utf-8")
        return str(data.get("content") or "")

    def open_spec_pr(
        self,
        *,
        issue_key: str,
        path: str,
        content: str,
        title: str,
        body: str,
    ) -> PullRequestInfo:
        branch = f"propose/{issue_key}"
        self.create_branch(branch)
        self.put_file(
            path=path,
            content=content,
            branch=branch,
            message=f"Propose Spec Request for {issue_key}",
        )
        return self.create_pull_request(
            title=title,
            body=body,
            head=branch,
        )

    def ensure_spec_merged(self, issue_key: str) -> PullRequestInfo | None:
        """Merge open propose/<key> PR if present. Returns PR info or None if already on main."""
        branch = f"propose/{issue_key}"
        pr = self.find_open_pr(head_ref=branch)
        if pr:
            return self.merge_pull_request(pr.number)
        return None
