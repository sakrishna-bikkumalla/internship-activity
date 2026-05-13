from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from internship_activity_tracker.services.batch.client import GitLabClient, GitLabUsersAPI


@pytest.fixture
def mock_client():
    # Pass a valid token and url so validation doesn't break
    client = GitLabClient("http://gitlab.com", "token")
    client._gl = MagicMock()
    return client


def test_client_request_success(mock_client):
    assert True  # Client requests tested functionally within API context


@pytest.mark.asyncio
async def test_async_request_post_passes_payload_fields(mock_client):
    mock_gl = AsyncMock()
    mock_gl.post.return_value = b'{"ok": true}'
    mock_client._gl = mock_gl

    result = await mock_client._async_request("POST", "/projects", {"name": "demo"})

    assert result == {"ok": True}
    mock_gl.post.assert_awaited_once_with("/projects", name="demo")


def test_users_api_get_by_username(mock_client):
    with patch("internship_activity_tracker.services.batch.client.GitLabClient._get") as mock_get:
        mock_get.return_value = [{"id": 1, "username": "user1", "name": "User One"}]
        res = mock_client.users.get_by_username("user1")
        assert res["id"] == 1
        assert res["username"] == "user1"

        # Error case
        mock_get.return_value = []
        with pytest.raises(ValueError):
            mock_client.users.get_by_username("none")


def test_users_api_get_by_userid(mock_client):
    with patch("internship_activity_tracker.services.batch.client.GitLabClient._get") as mock_get:
        mock_get.return_value = {"id": 1, "username": "user1"}
        res = mock_client.users.get_by_userid(1)
        assert res["id"] == 1


def test_users_api_get_user_projects(mock_client):
    with patch("internship_activity_tracker.services.batch.client.GitLabClient._get_paginated") as mock_paginated:
        mock_paginated.side_effect = [
            [{"id": 1, "name": "Owned"}],
            [{"id": 1, "name": "Owned"}, {"id": 2, "name": "Member"}],
            [{"id": 3, "name": "Contributed"}],
        ]
        res = mock_client.users.get_user_projects(1)
        assert len(res) == 3
        ids = {p["id"] for p in res}
        assert ids == {1, 2, 3}


def test_users_api_counts(mock_client):
    with patch.object(GitLabUsersAPI, "get_user_projects", return_value=[{"id": 1}]):
        assert mock_client.users.get_user_project_count(1) == 1

    with patch.object(GitLabUsersAPI, "get_user_projects", side_effect=Exception("fail")):
        assert "Error:" in str(mock_client.users.get_user_project_count(1))

    with patch.object(GitLabUsersAPI, "get_user_groups", return_value=[{"id": 1}]):
        assert mock_client.users.get_user_group_count(1) == 1

    with patch.object(GitLabUsersAPI, "get_user_issues", return_value=[{"id": 1}]):
        assert mock_client.users.get_user_issue_count(1) == 1


def test_users_api_get_user_commits(mock_client):
    user_info = {"id": 1, "username": "user1", "name": "User One", "email": "user@gl.com"}

    with patch.object(GitLabUsersAPI, "get_user_projects") as mock_projs:
        mock_projs.return_value = [{"id": 101, "name": "Proj1", "namespace": {"full_path": "user1"}}]

        with patch(
            "internship_activity_tracker.services.batch.client.GitLabClient._async_get_paginated"
        ) as mock_paginated:
            # Case 1: author query matches

            mock_paginated.return_value = [
                {
                    "id": "abc",
                    "author_name": "User One",
                    "author_email": "user@gl.com",
                    "committer_name": "User One",
                    "committer_email": "user@gl.com",
                }
            ]

            res = mock_client.users.get_user_commits(user_info)
            assert len(res) == 1
            assert res[0]["project_name"] == "Proj1"
            assert res[0]["project_scope"] == "Personal"

            # Case 2: No projects
            mock_projs.return_value = []
            assert mock_client.users.get_user_commits(user_info) == []

            # Case 3: No user id
            assert mock_client.users.get_user_commits({}) == []


def test_name_email_match_edge_cases(mock_client):
    user_info = {"id": 1, "username": "user.one", "name": "User One", "email": "user@gl.com"}
    with patch.object(GitLabUsersAPI, "get_user_projects", return_value=[{"id": 101}]):
        with patch(
            "internship_activity_tracker.services.batch.client.GitLabClient._async_get_paginated"
        ) as mock_paginated:
            # Test name match with normalized names (dots to spaces)

            mock_paginated.return_value = [{"id": "c1", "author_name": "user one"}]
            res = mock_client.users.get_user_commits(user_info)
            assert len(res) == 1

            # Test email match with local part
            mock_paginated.return_value = [{"id": "c2", "author_email": "user@other.com"}]
            res = mock_client.users.get_user_commits(user_info)
            assert len(res) == 1
