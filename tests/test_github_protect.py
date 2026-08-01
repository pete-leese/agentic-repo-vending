"""Tests for classic branch protection + branch wait helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx

from repo_vendor.config import Settings
from repo_vendor.github_client import GitHubClient


def _settings(**kwargs: object) -> Settings:
    base = {
        "GITHUB_TOKEN": "test-token",
        "GITHUB_OWNER": "pete-leese",
        "CONTROL_PLANE_REPO": "agentic-repo-vending",
        "DRY_RUN": False,
        "ALLOW_LLM_FALLBACK": True,
    }
    base.update(kwargs)
    return Settings(**base)


def test_wait_for_branch_succeeds_after_404():
    client = GitHubClient(_settings())
    responses = [
        httpx.Response(404, json={"message": "Branch not found"}),
        httpx.Response(200, json={"name": "main"}),
    ]
    mock_get = MagicMock(side_effect=responses)
    client._client.get = mock_get  # type: ignore[method-assign]
    with patch("repo_vendor.github_client.time.sleep"):
        assert client.wait_for_branch("demo-repo", "main", attempts=3, delay_s=0) is True
    assert mock_get.call_count == 2
    client.close()


def test_protect_main_uses_classic_endpoint_and_payload():
    client = GitHubClient(_settings())
    client.wait_for_branch = MagicMock(return_value=True)  # type: ignore[method-assign]
    put = MagicMock(return_value=httpx.Response(200, json={"url": "ok"}))
    client._client.put = put  # type: ignore[method-assign]

    assert client.protect_main("demo-repo") is True

    put.assert_called_once()
    args, kwargs = put.call_args
    assert args[0] == "/repos/pete-leese/demo-repo/branches/main/protection"
    assert "/rulesets" not in args[0]
    payload = kwargs["json"]
    assert payload["required_status_checks"] is None
    assert payload["restrictions"] is None
    assert payload["enforce_admins"] is True
    assert payload["required_pull_request_reviews"]["required_approving_review_count"] == 1
    assert payload["required_pull_request_reviews"]["require_code_owner_reviews"] is False
    assert "luke-cage-preview" in kwargs["headers"]["Accept"]
    client.close()


def test_protect_main_false_when_branch_never_ready():
    client = GitHubClient(_settings())
    client.wait_for_branch = MagicMock(return_value=False)  # type: ignore[method-assign]
    put = MagicMock()
    client._client.put = put  # type: ignore[method-assign]
    assert client.protect_main("demo-repo") is False
    put.assert_not_called()
    client.close()


def test_protect_main_retries_404_then_succeeds():
    client = GitHubClient(_settings())
    client.wait_for_branch = MagicMock(return_value=True)  # type: ignore[method-assign]
    put = MagicMock(
        side_effect=[
            httpx.Response(404, json={"message": "Branch not found"}),
            httpx.Response(200, json={"url": "ok"}),
        ]
    )
    client._client.put = put  # type: ignore[method-assign]
    with patch("repo_vendor.github_client.time.sleep"):
        assert client.protect_main("demo-repo") is True
    assert put.call_count == 2
    client.close()


def test_protect_main_false_on_403():
    client = GitHubClient(_settings())
    client.wait_for_branch = MagicMock(return_value=True)  # type: ignore[method-assign]
    put = MagicMock(
        return_value=httpx.Response(
            403,
            json={"message": "Resource not accessible by personal access token"},
        )
    )
    client._client.put = put  # type: ignore[method-assign]
    assert client.protect_main("demo-repo") is False
    put.assert_called_once()
    client.close()
