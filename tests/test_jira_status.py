from unittest.mock import MagicMock, patch

from repo_vendor.config import Settings
from repo_vendor.jira_client import JiraClient


def test_transition_to_matches_to_name():
    settings = Settings(JIRA_EMAIL="a@b.c", JIRA_API_TOKEN="x", DRY_RUN=False)
    client = JiraClient(settings)
    mock_get = MagicMock()
    mock_get.raise_for_status = MagicMock()
    mock_get.json.return_value = {
        "transitions": [
            {"id": "21", "name": "Start progress", "to": {"name": "In Progress"}},
            {"id": "31", "name": "Done", "to": {"name": "Done"}},
        ]
    }
    mock_post = MagicMock()
    mock_post.raise_for_status = MagicMock()
    with patch.object(client._client, "get", return_value=mock_get):
        with patch.object(client._client, "post", return_value=mock_post) as post:
            assert client.transition_to("KAN-1", "In Progress") is True
    post.assert_called_once()
    assert post.call_args.kwargs["json"] == {"transition": {"id": "21"}}
    client.close()


def test_set_outcome_label_replaces_prior():
    settings = Settings(
        JIRA_EMAIL="a@b.c",
        JIRA_API_TOKEN="x",
        DRY_RUN=False,
        JIRA_LABEL_SUCCESS="repo-vend-success",
        JIRA_LABEL_WARNING="repo-vend-warning",
        JIRA_LABEL_ERROR="repo-vend-error",
    )
    client = JiraClient(settings)
    with patch.object(client, "remove_label") as remove:
        with patch.object(client, "add_label") as add:
            client.set_outcome_label("KAN-1", "warning")
    assert remove.call_count == 3
    add.assert_called_once_with("KAN-1", "repo-vend-warning")
    client.close()
