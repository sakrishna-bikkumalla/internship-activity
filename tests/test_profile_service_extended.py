from unittest.mock import MagicMock, patch

import pytest

from internship_activity_tracker.services.profile import profile_service


@pytest.fixture
def mock_gl():
    return MagicMock()


def test_extract_username_from_input():
    assert profile_service._extract_username_from_input("jdoe") == "jdoe"
    assert profile_service._extract_username_from_input("https://gitlab.com/jdoe") == "jdoe"
    assert profile_service._extract_username_from_input("") == ""
    assert profile_service._extract_username_from_input(None) == ""


def test_safe_getattr_dict_id():
    obj = MagicMock()
    obj.user = {"id": 123}
    assert profile_service._safe_getattr_dict_id(obj, "user") == 123
    obj.user = "not a dict"
    assert profile_service._safe_getattr_dict_id(obj, "user") is None
    assert profile_service._safe_getattr_dict_id(obj, "missing") is None


def test_get_issue_assignee_ids():
    issue = {"assignee": {"id": 1}, "assignees": [{"id": 2}, {"id": 3}, "invalid"]}
    ids = profile_service._get_issue_assignee_ids(issue)
    assert ids == {1, 2, 3}


def test_issue_is_related_to_user():
    issue = {"author": {"id": 100}, "assignees": [{"id": 101}]}
    assert profile_service._issue_is_related_to_user(issue, 100) is True
    assert profile_service._issue_is_related_to_user(issue, 101) is True
    assert profile_service._issue_is_related_to_user(issue, 999) is False


def test_fetch_user_related_issues_by_state(mock_gl):
    mock_gl._get_paginated.return_value = [{"id": 1, "created_at": "2024-01-01T00:00:00Z"}]
    issues = profile_service._fetch_user_related_issues_by_state(mock_gl, 123)
    assert len(issues) == 1
    assert issues[0]["id"] == 1


def test_get_total_count_from_api(mock_gl):
    mock_gl._get_paginated.return_value = [1, 2, 3]
    assert profile_service._get_total_count_from_api(mock_gl, "/endpoint") == 3
    mock_gl._get_paginated.side_effect = Exception("err")
    assert profile_service._get_total_count_from_api(mock_gl, "/endpoint") is None


def test_get_user_profile(mock_gl):
    mock_gl._get.return_value = [{"id": 1}]
    res = profile_service.get_user_profile(mock_gl, "jdoe")
    assert res == {"id": 1}

    mock_gl._get.return_value = {"id": 2}
    res = profile_service.get_user_profile(mock_gl, "123")
    assert res == {"id": 2}


def test_get_user_counts(mock_gl):
    with patch(
        "internship_activity_tracker.services.profile.profile_service._get_total_count_from_api", return_value=5
    ):
        assert profile_service.get_user_projects_count(mock_gl, 123) == 5
        assert profile_service.get_user_groups_count(mock_gl, 123) == 5
        assert profile_service.get_user_open_mrs_count(mock_gl, 123) == 5


def test_get_user_issues_details(mock_gl):
    issues = [
        {"state": "opened", "created_at": "2024-01-01T10:00:00Z"},
        {"state": "closed", "created_at": "2024-01-01T14:00:00Z"},
    ]
    with patch(
        "internship_activity_tracker.services.profile.profile_service._fetch_user_related_issues_by_state",
        return_value=issues,
    ):
        stats = profile_service.get_user_issues_details(mock_gl, 123)
        assert stats["total"] == 2
        assert stats["open"] == 1
        assert stats["closed"] == 1


def test_check_profile_readme_success(mock_gl):
    mock_gl._get.side_effect = [
        {"default_branch": "main", "web_url": "http://repo"},  # project
        {"content": "..."},  # file
    ]
    res = profile_service.check_profile_readme(mock_gl, "jdoe")
    assert res["exists"] is True
    assert "README.md" in res["url"]


def test_check_profile_readme_fail(mock_gl):
    mock_gl._get.side_effect = Exception("not found")
    res = profile_service.check_profile_readme(mock_gl, "jdoe")
    assert res["exists"] is False
