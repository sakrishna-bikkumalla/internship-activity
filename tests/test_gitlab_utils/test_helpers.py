from unittest.mock import MagicMock

import pytest

from internship_activity_tracker.infrastructure.gitlab.projects import extract_path_from_url
from internship_activity_tracker.infrastructure.gitlab.retry_helper import get_project_with_retries


def test_extract_path_from_url():
    assert extract_path_from_url("https://gitlab.com/group/project") == "group/project"
    assert extract_path_from_url("https://gitlab.com/group/project.git") == "group/project"
    assert extract_path_from_url("group/project") == "group/project"
    assert extract_path_from_url("  group/project  ") == "group/project"
    assert extract_path_from_url("") == ""


def test_get_project_with_retries_success():
    mock_client = MagicMock()
    mock_client._get.return_value = {"id": 123, "name": "test-project"}

    result = get_project_with_retries(mock_client, "group/project")

    assert result == {"id": 123, "name": "test-project"}
    mock_client._get.assert_called()


def test_get_project_with_retries_404():
    mock_client = MagicMock()
    mock_client._get.side_effect = Exception("404 Not Found")

    with pytest.raises(Exception) as excinfo:
        get_project_with_retries(mock_client, "missing/project")
    assert "404" in str(excinfo.value)
