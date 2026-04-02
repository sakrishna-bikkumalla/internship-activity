from unittest.mock import patch

import pytest

from gitlab_compliance_checker.services.batch.client import GitLabClient, GitLabUsersAPI


@pytest.fixture
def mock_client():
    return GitLabClient("http://gitlab.com", "token")


def test_client_request_success(mock_client):
    with patch("gitlab_compliance_checker.services.batch.client.gitlab.Gitlab.http_get") as mock_get:
        mock_get.return_value = {"id": 1}

        res = mock_client._get("/test")
        assert res == {"id": 1}
        mock_get.assert_called_once()


def test_client_request_204(mock_client):
    with patch("gitlab_compliance_checker.services.batch.client.gitlab.Gitlab.http_get") as mock_get:
        mock_get.return_value = None

        res = mock_client._get("/test")
        assert res is None


def test_client_get_paginated(mock_client):
    with patch("gitlab_compliance_checker.services.batch.client.gitlab.Gitlab.http_get") as mock_get:
        # Page 1: 100 items, Page 2: 50 items
        mock_get.side_effect = [list(range(100)), list(range(50)), []]

        res = mock_client._get_paginated("/test", per_page=100)
        assert len(res) == 150
        assert mock_get.call_count == 2


def test_users_api_get_by_username(mock_client):
    with patch("gitlab_compliance_checker.services.batch.client.GitLabClient._get") as mock_get:
        mock_get.return_value = [{"id": 1, "username": "user1", "name": "User One"}]
        res = mock_client.users.get_by_username("user1")
        assert res["id"] == 1
        assert res["username"] == "user1"

        # Error case
        mock_get.return_value = []
        with pytest.raises(ValueError):
            mock_client.users.get_by_username("none")


def test_users_api_get_by_userid(mock_client):
    with patch("gitlab_compliance_checker.services.batch.client.GitLabClient._get") as mock_get:
        mock_get.return_value = {"id": 1, "username": "user1"}
        res = mock_client.users.get_by_userid(1)
        assert res["id"] == 1


def test_users_api_get_user_projects(mock_client):
    with patch("gitlab_compliance_checker.services.batch.client.GitLabClient._get_paginated") as mock_paginated:
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

    with patch.object(GitLabUsersAPI, "get_user_groups", side_effect=Exception("fail")):
        assert "Error:" in str(mock_client.users.get_user_group_count(1))

    with patch.object(GitLabUsersAPI, "get_user_issues", return_value=[{"id": 1}]):
        assert mock_client.users.get_user_issue_count(1) == 1

    with patch.object(GitLabUsersAPI, "get_user_issues", side_effect=Exception("fail")):
        assert "Error:" in str(mock_client.users.get_user_issue_count(1))

    with patch.object(GitLabUsersAPI, "get_user_merge_requests", return_value=[{"id": 1}]):
        assert mock_client.users.get_user_mr_count(1) == 1

    with patch.object(GitLabUsersAPI, "get_user_merge_requests", side_effect=Exception("fail")):
        assert "Error:" in str(mock_client.users.get_user_mr_count(1))


def test_users_api_get_user_commits(mock_client):
    user_info = {"id": 1, "username": "user1", "name": "User One", "email": "user@gl.com"}

    with patch.object(GitLabUsersAPI, "get_user_projects") as mock_projs:
        mock_projs.return_value = [{"id": 101, "name": "Proj1", "namespace": {"full_path": "user1"}}]

        with patch.object(GitLabClient, "_get_paginated") as mock_paginated:
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


def test_users_api_get_user_commits_fallback(mock_client):
    user_info = {"id": 1, "username": "user1", "name": "User One"}
    with patch.object(GitLabUsersAPI, "get_user_projects") as mock_projs:
        mock_projs.return_value = [{"id": 101, "name": "Proj1"}]
        with patch.object(GitLabClient, "_get_paginated") as mock_paginated:
            # author_queries = ["User One", "user1"]
            # Loop calls _get_paginated twice (gets [] and [])
            # Fallback calls _get_paginated once
            mock_paginated.side_effect = [[], [], [{"id": "xyz", "author_name": "user1"}]]

            res = mock_client.users.get_user_commits(user_info)
            assert len(res) == 1
            assert res[0]["id"] == "xyz"


def test_users_api_get_user_commits_extended(mock_client):
    user_info = {"id": 1, "username": "user1"}
    with patch.object(GitLabUsersAPI, "get_user_projects") as mock_projs:
        # Case: project with no ID (line 231)
        mock_projs.return_value = [{"name": "NoID"}]
        assert mock_client.users.get_user_commits(user_info) == []

        # Case: commit with no author match (line 277)
        mock_projs.return_value = [{"id": 101}]
        with patch.object(GitLabClient, "_get_paginated") as mock_paginated:
            mock_paginated.return_value = [{"id": "abc", "author_name": "other"}]
            assert mock_client.users.get_user_commits(user_info) == []


def test_client_paginated_break(mock_client):
    with patch("gitlab.Gitlab.http_get") as mock_get:
        # Case: not a list
        mock_get.return_value = {"error": "bad"}
        assert mock_client._get_paginated("/test") == []


def test_normalize_user_none(mock_client):
    assert mock_client.users._normalize_user(None) is None


def test_get_user_projects_exception(mock_client):
    with patch("gitlab_compliance_checker.services.batch.client.GitLabClient._get_paginated") as mock_paginated:
        # First two succeed, third fails (line 108)
        mock_paginated.side_effect = [[], [], Exception("Limit")]
        res = mock_client.users.get_user_projects(1)
        assert res == []


def test_direct_api_calls(mock_client):
    with patch("gitlab_compliance_checker.services.batch.client.GitLabClient._get_paginated") as mock_paginated:
        mock_paginated.return_value = [{"id": 1}]
        assert mock_client.users.get_user_groups(1) == [{"id": 1}]
        assert mock_client.users.get_user_issues(1) == [{"id": 1}]
        assert mock_client.users.get_user_merge_requests(1) == [{"id": 1}]


def test_name_email_match_edge_cases(mock_client):
    user_info = {"id": 1, "username": "user.one", "name": "User One", "email": "user@gl.com"}
    with patch.object(GitLabUsersAPI, "get_user_projects", return_value=[{"id": 101}]):
        with patch.object(GitLabClient, "_get_paginated") as mock_paginated:
            # Test name match with normalized names (dots to spaces)
            mock_paginated.return_value = [{"id": "c1", "author_name": "user one"}]
            res = mock_client.users.get_user_commits(user_info)
            assert len(res) == 1

            # Test email match with local part
            mock_paginated.return_value = [{"id": "c2", "author_email": "user@other.com"}]
            res = mock_client.users.get_user_commits(user_info)
            assert len(res) == 1  # matches 'user' from email local part or name_candidates


def test_users_api_get_user_commits_exception(mock_client):
    user_info = {"id": 1}
    with patch.object(GitLabUsersAPI, "get_user_projects") as mock_projs:
        mock_projs.return_value = [{"id": 101}]
        with patch.object(GitLabClient, "_get_paginated", side_effect=Exception("API limit")):
            res = mock_client.users.get_user_commits(user_info)
            assert res == []
