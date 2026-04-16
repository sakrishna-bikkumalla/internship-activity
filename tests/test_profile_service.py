from unittest.mock import MagicMock

import pytest

from gitlab_compliance_checker.services.profile.profile_service import (
    _extract_username_from_input,
    _fetch_user_related_issues_by_state,
    _get_issue_assignee_ids,
    _get_total_count_from_api,
    _issue_is_related_to_user,
    check_profile_readme,
    get_user_issues_details,
    get_user_issues_list,
    get_user_open_mrs_count,
    get_user_profile,
    get_user_projects_count,
)


@pytest.fixture
def mock_client():
    return MagicMock()


@pytest.fixture
def mock_user_dict():
    return {
        "id": 42,
        "username": "testuser",
        "name": "Test User",
        "web_url": "https://gitlab.com/testuser",
    }


class TestExtractUsernameFromInput:
    def test_plain_username(self):
        assert _extract_username_from_input("john") == "john"

    def test_https_url(self):
        assert _extract_username_from_input("https://gitlab.com/john") == "john"


class TestGetIssueAssigneeIds:
    def test_single_assignee_dict(self):
        issue = {"assignee": {"id": 42}}
        assert _get_issue_assignee_ids(issue) == {42}

    def test_assignees_list(self):
        issue = {"assignees": [{"id": 1}, {"id": 2}]}
        assert _get_issue_assignee_ids(issue) == {1, 2}


class TestIssueIsRelatedToUser:
    def test_author_match(self):
        issue = {"author": {"id": 42}}
        assert _issue_is_related_to_user(issue, 42) is True


class TestGetTotalCountFromApi:
    def test_valid_total(self, mock_client):
        mock_client._get_paginated.return_value = [None] * 100

        result = _get_total_count_from_api(mock_client, "/test")
        assert result == 100


class TestFetchUserRelatedIssuesByState:
    def test_fetch_by_author_id(self, mock_client):
        mock_issue = {"id": 1, "created_at": "2024-01-01T00:00:00Z", "author": {"id": 42}}
        mock_client._get_paginated.return_value = [mock_issue]

        issues = _fetch_user_related_issues_by_state(mock_client, 42)
        assert len(issues) == 1
        assert issues[0]["id"] == 1


class TestGetUserProfile:
    def test_get_by_numeric_id(self, mock_client, mock_user_dict):
        mock_client._get.return_value = mock_user_dict
        result = get_user_profile(mock_client, "42")
        assert result == mock_user_dict
        mock_client._get.assert_called_with("/users/42")

    def test_get_by_username(self, mock_client, mock_user_dict):
        mock_client._get.return_value = [mock_user_dict]
        result = get_user_profile(mock_client, "testuser")
        assert result == mock_user_dict


class TestGetUserProjectsCount:
    def test_success(self, mock_client):
        mock_client._get_paginated.return_value = [None] * 50

        result = get_user_projects_count(mock_client, 42)
        assert result == 50


class TestGetUserOpenMrsCount:
    def test_success(self, mock_client):
        mock_client._get_paginated.return_value = [None] * 10

        result = get_user_open_mrs_count(mock_client, 42)
        assert result == 10


class TestGetUserIssuesDetails:
    def test_issue_counts(self, mock_client):
        issues = [
            {"id": 1, "state": "opened", "created_at": "2024-01-01T00:00:00Z"},
            {"id": 2, "state": "closed", "created_at": "2024-01-01T00:00:00Z"},
        ]
        mock_client._get_paginated.return_value = issues

        result = get_user_issues_details(mock_client, 42)
        assert result["total"] == 2
        assert result["open"] == 1
        assert result["closed"] == 1


class TestGetUserIssuesList:
    def test_basic_list(self, mock_client):
        issues = [
            {
                "id": 1,
                "iid": 10,
                "title": "Test",
                "state": "opened",
                "project_id": 100,
                "created_at": "2024-01-01T00:00:00Z",
                "web_url": "http://url",
                "assignees": [{"username": "user1"}],
            }
        ]
        mock_client._get_paginated.return_value = issues

        result = get_user_issues_list(mock_client, 42)
        assert len(result) == 1
        assert result[0]["id"] == 1
        assert "user1" in result[0]["assignees"]


class TestCheckProfileReadme:
    def test_readme_exists(self, mock_client):
        mock_client._get.side_effect = [
            {"web_url": "http://url", "default_branch": "main"},  # Project info
            {"name": "README.md"},  # File info
        ]
        result = check_profile_readme(mock_client, "testuser")
        assert result["exists"] is True
        assert "blob" in result["url"]

    def test_readme_not_found(self, mock_client):
        mock_client._get.side_effect = Exception("Not found")
        result = check_profile_readme(mock_client, "nonexistent")
        assert result["exists"] is False
