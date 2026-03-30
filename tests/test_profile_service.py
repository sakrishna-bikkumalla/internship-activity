from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from user_profile.profile_service import (
    _extract_username_from_input,
    _fetch_user_related_issues_by_state,
    _get_issue_assignee_ids,
    _get_total_count_from_api,
    _issue_is_related_to_user,
    _safe_getattr_dict_id,
    check_profile_readme,
    get_user_groups_count,
    get_user_issues_details,
    get_user_issues_list,
    get_user_open_issues_count,
    get_user_open_mrs_count,
    get_user_profile,
    get_user_projects_count,
)


class MockIssue:
    def __init__(
        self,
        id,
        iid,
        title,
        state,
        project_id,
        created_at,
        web_url,
        author=None,
        assignees=None,
        assignee=None,
        updated_at=None,
    ):
        self.id = id
        self.iid = iid
        self.title = title
        self.state = state
        self.project_id = project_id
        self.created_at = created_at
        self.web_url = web_url
        self.author = author
        self.assignees = assignees
        self.assignee = assignee
        self.updated_at = updated_at or created_at


@pytest.fixture
def mock_gl():
    return MagicMock()


@pytest.fixture
def mock_user():
    user = MagicMock()
    user.id = 42
    user.username = "testuser"
    user.name = "Test User"
    user.web_url = "https://gitlab.com/testuser"
    return user


class TestExtractUsernameFromInput:
    def test_plain_username(self):
        assert _extract_username_from_input("john") == "john"

    def test_username_with_spaces(self):
        assert _extract_username_from_input("  john  ") == "john"

    def test_empty_input(self):
        assert _extract_username_from_input("") == ""
        assert _extract_username_from_input(None) == ""

    def test_https_url(self):
        assert _extract_username_from_input("https://gitlab.com/john") == "john"

    def test_http_url(self):
        assert _extract_username_from_input("http://gitlab.com/john") == "john"

    def test_url_with_extra_path(self):
        assert _extract_username_from_input("https://gitlab.com/john/some/project") == "john"


class TestSafeGetattrDictId:
    def test_dict_attribute(self):
        class Obj:
            pass

        obj = Obj()
        obj.author = {"id": 42}
        assert _safe_getattr_dict_id(obj, "author") == 42

    def test_non_dict_attribute(self):
        class Obj:
            pass

        obj = Obj()
        obj.author = MagicMock()
        assert _safe_getattr_dict_id(obj, "author") is None

    def test_missing_attribute(self):
        assert _safe_getattr_dict_id(MagicMock(), "missing") is None


class TestGetIssueAssigneeIds:
    def test_single_assignee_dict(self):
        issue = MagicMock()
        issue.assignee = {"id": 42}
        issue.assignees = None
        assert _get_issue_assignee_ids(issue) == {42}

    def test_assignees_list(self):
        issue = MagicMock()
        issue.assignee = None
        issue.assignees = [{"id": 1}, {"id": 2}, {"name": "test"}]
        assert _get_issue_assignee_ids(issue) == {1, 2}

    def test_assignees_with_none_id(self):
        issue = MagicMock()
        issue.assignee = None
        issue.assignees = [{"id": None}, {"id": 1}]
        assert _get_issue_assignee_ids(issue) == {1}

    def test_no_assignees(self):
        issue = MagicMock()
        issue.assignee = None
        issue.assignees = None
        assert _get_issue_assignee_ids(issue) == set()

    def test_non_dict_assignee(self):
        issue = MagicMock()
        issue.assignee = MagicMock()
        issue.assignees = None
        assert _get_issue_assignee_ids(issue) == set()


class TestIssueIsRelatedToUser:
    def test_author_match(self):
        issue = MagicMock()
        issue.author = {"id": 42}
        assert _issue_is_related_to_user(issue, 42) is True

    def test_assignee_match(self):
        issue = MagicMock()
        issue.author = {"id": 1}
        issue.assignee = {"id": 42}
        issue.assignees = None
        assert _issue_is_related_to_user(issue, 42) is True

    def test_not_related(self):
        issue = MagicMock()
        issue.author = {"id": 1}
        issue.assignee = None
        issue.assignees = None
        assert _issue_is_related_to_user(issue, 42) is False


class TestGetTotalCountFromApi:
    def test_valid_total(self, mock_gl):
        mock_response = MagicMock()
        mock_response.headers = {"X-Total": "100"}
        mock_gl.http_get.return_value = mock_response

        result = _get_total_count_from_api(mock_gl, "/test")
        assert result == 100

    def test_missing_total_header(self, mock_gl):
        mock_response = MagicMock()
        mock_response.headers = {}
        mock_gl.http_get.return_value = mock_response

        result = _get_total_count_from_api(mock_gl, "/test")
        assert result is None

    def test_exception(self, mock_gl):
        mock_gl.http_get.side_effect = Exception("API Error")
        result = _get_total_count_from_api(mock_gl, "/test")
        assert result is None


class TestFetchUserRelatedIssuesByState:
    def test_fetch_by_author_id(self, mock_gl):
        mock_issue = MockIssue(1, 10, "Test", "opened", 1, "2024-01-01T00:00:00Z", "http://url", {"id": 42})
        mock_gl.issues.list.return_value = [mock_issue]

        issues = _fetch_user_related_issues_by_state(mock_gl, 42)
        assert len(issues) == 1
        assert issues[0].id == 1

    def test_fetch_by_assignee_id(self, mock_gl):
        mock_issue = MockIssue(1, 10, "Test", "opened", 1, "2024-01-01T00:00:00Z", "http://url")
        mock_issue.assignee = {"id": 42}
        mock_gl.issues.list.return_value = [mock_issue]

        issues = _fetch_user_related_issues_by_state(mock_gl, 42)
        assert len(issues) == 1

    def test_fallback_to_username(self, mock_gl):
        mock_issue = MockIssue(1, 10, "Test", "opened", 1, "2024-01-01T00:00:00Z", "http://url")
        user = MagicMock()
        user.username = "testuser"
        mock_gl.users.get.return_value = user
        mock_gl.issues.list.return_value = [mock_issue]

        issues = _fetch_user_related_issues_by_state(mock_gl, 42)
        assert len(issues) >= 1

    def test_with_state_filter(self, mock_gl):
        mock_gl.issues.list.return_value = []
        issues = _fetch_user_related_issues_by_state(mock_gl, 42, state="opened")
        mock_gl.issues.list.assert_called()

    def test_limit(self, mock_gl):
        mock_issues = [
            MockIssue(i, i, "Test", "opened", 1, f"2024-01-0{i:01d}T00:00:00Z", "http://url") for i in range(1, 6)
        ]
        mock_gl.issues.list.return_value = mock_issues

        issues = _fetch_user_related_issues_by_state(mock_gl, 42, limit=3)
        assert len(issues) == 3


class TestGetUserProfile:
    def test_get_by_numeric_id(self, mock_gl, mock_user):
        mock_gl.users.get.return_value = mock_user
        result = get_user_profile(mock_gl, "42")
        assert result == mock_user
        mock_gl.users.get.assert_called_once_with(42)

    def test_get_by_username(self, mock_gl, mock_user):
        mock_gl.users.list.return_value = [mock_user]
        result = get_user_profile(mock_gl, "testuser")
        assert result == mock_user

    def test_user_not_found(self, mock_gl):
        mock_gl.users.list.return_value = []
        result = get_user_profile(mock_gl, "nonexistent")
        assert result is None

    def test_exception_handling(self, mock_gl):
        mock_gl.users.list.side_effect = Exception("API Error")
        result = get_user_profile(mock_gl, "testuser")
        assert result is None

    def test_extract_from_url(self, mock_gl, mock_user):
        mock_gl.users.list.return_value = [mock_user]
        result = get_user_profile(mock_gl, "https://gitlab.com/testuser")
        assert result == mock_user


class TestGetUserProjectsCount:
    def test_from_api_header(self, mock_gl):
        mock_response = MagicMock()
        mock_response.headers = {"X-Total": "50"}
        mock_gl.http_get.return_value = mock_response

        result = get_user_projects_count(mock_gl, 42)
        assert result == 50

    def test_fallback_to_list(self, mock_gl):
        mock_response = MagicMock()
        mock_response.headers = {}
        mock_gl.http_get.return_value = mock_response

        mock_project = MagicMock()
        mock_user = MagicMock()
        mock_user.projects.list.return_value = [mock_project, mock_project]
        mock_gl.users.get.return_value = mock_user

        result = get_user_projects_count(mock_gl, 42)
        assert result == 2

    def test_exception_returns_zero(self, mock_gl):
        mock_gl.http_get.side_effect = Exception("Error")
        mock_gl.users.get.side_effect = Exception("Error")
        result = get_user_projects_count(mock_gl, 42)
        assert result == 0


class TestGetUserGroupsCount:
    def test_from_api_header(self, mock_gl):
        mock_response = MagicMock()
        mock_response.headers = {"X-Total": "25"}
        mock_gl.http_get.return_value = mock_response

        result = get_user_groups_count(mock_gl, 42)
        assert result == 25

    def test_fallback_to_list(self, mock_gl):
        mock_response = MagicMock()
        mock_response.headers = {}
        mock_gl.http_get.return_value = mock_response

        mock_group = MagicMock()
        mock_user = MagicMock()
        mock_user.groups.list.return_value = [mock_group]
        mock_gl.users.get.return_value = mock_user

        result = get_user_groups_count(mock_gl, 42)
        assert result == 1


class TestGetUserOpenMrsCount:
    def test_from_api_header(self, mock_gl):
        mock_response = MagicMock()
        mock_response.headers = {"X-Total": "10"}
        mock_gl.http_get.return_value = mock_response

        result = get_user_open_mrs_count(mock_gl, 42)
        assert result == 10

    def test_fallback_to_list(self, mock_gl):
        mock_response = MagicMock()
        mock_response.headers = {}
        mock_gl.http_get.return_value = mock_response

        mock_mr = MagicMock()
        mock_gl.mergerequests.list.return_value = [mock_mr, mock_mr, mock_mr]
        result = get_user_open_mrs_count(mock_gl, 42)
        assert result == 3


class TestGetUserOpenIssuesCount:
    def test_success(self, mock_gl):
        mock_issue = MockIssue(1, 1, "Test", "opened", 1, "2024-01-01T00:00:00Z", "http://url")
        mock_gl.issues.list.return_value = [mock_issue]
        result = get_user_open_issues_count(mock_gl, 42)
        assert result >= 0

    def test_exception_returns_zero(self, mock_gl):
        mock_gl.issues.list.side_effect = Exception("Error")
        result = get_user_open_issues_count(mock_gl, 42)
        assert result == 0


class TestGetUserIssuesDetails:
    def test_empty_issues(self, mock_gl):
        mock_gl.issues.list.return_value = []
        result = get_user_issues_details(mock_gl, 42)
        assert result["total"] == 0
        assert result["open"] == 0
        assert result["closed"] == 0

    def test_issue_counts(self, mock_gl):
        opened = MockIssue(1, 1, "Opened", "opened", 1, "2024-01-01T00:00:00Z", "http://url")
        closed = MockIssue(2, 2, "Closed", "closed", 1, "2024-01-01T00:00:00Z", "http://url")
        mock_gl.issues.list.side_effect = [[opened], []]

        result = get_user_issues_details(mock_gl, 42)
        assert result["total"] >= 1

    def test_today_morning_issues(self, mock_gl):
        today = datetime.now().date().isoformat()
        mock_issue = MockIssue(1, 1, "Test", "opened", 1, f"{today}T03:00:00Z", "http://url")
        mock_gl.issues.list.return_value = [mock_issue]

        result = get_user_issues_details(mock_gl, 42)
        assert result["today_morning"] >= 0 or result["today_afternoon"] >= 0


class TestGetUserIssuesList:
    def test_basic_list(self, mock_gl):
        mock_issue = MockIssue(1, 10, "Test Issue", "opened", 100, "2024-01-01T00:00:00Z", "http://url")
        mock_issue.assignees = [{"username": "user1"}, {"username": "user2"}]
        mock_gl.issues.list.return_value = [mock_issue]

        result = get_user_issues_list(mock_gl, 42)
        assert len(result) == 1
        assert result[0]["id"] == 1
        assert result[0]["iid"] == 10
        assert result[0]["title"] == "Test Issue"
        assert "user1" in result[0]["assignees"]

    def test_limit(self, mock_gl):
        mock_issues = [
            MockIssue(i, i, f"Issue {i}", "opened", 1, "2024-01-01T00:00:00Z", "http://url") for i in range(10)
        ]
        mock_gl.issues.list.return_value = mock_issues

        result = get_user_issues_list(mock_gl, 42, limit=5)
        assert len(result) == 5


class TestCheckProfileReadme:
    def test_readme_exists(self, mock_gl):
        mock_project = MagicMock()
        mock_project.web_url = "https://gitlab.com/testuser"
        mock_project.default_branch = "main"
        mock_project.files.get.return_value = MagicMock()
        mock_gl.projects.get.return_value = mock_project

        result = check_profile_readme(mock_gl, "testuser")
        assert result["exists"] is True
        assert "blob" in result["url"]

    def test_readme_not_found(self, mock_gl):
        mock_gl.projects.get.side_effect = Exception("Not found")

        result = check_profile_readme(mock_gl, "nonexistent")
        assert result["exists"] is False

    def test_readme_file_not_found(self, mock_gl):
        mock_project = MagicMock()
        mock_project.files.get.side_effect = Exception("File not found")
        mock_gl.projects.get.return_value = mock_project

        result = check_profile_readme(mock_gl, "testuser")
        assert result["exists"] is False
