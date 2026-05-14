from unittest.mock import MagicMock, patch

import pytest

from internship_activity_tracker.infrastructure.gitlab.retry_helper import get_project_with_retries


def test_get_project_with_retries_success():
    mock_client = MagicMock()
    mock_client._get.return_value = {"id": 123, "name": "test-project"}

    result = get_project_with_retries(mock_client, "group/project")

    assert result == {"id": 123, "name": "test-project"}
    mock_client._get.assert_called_once_with("/projects/group%2Fproject")


def test_get_project_with_retries_failure_then_success():
    mock_client = MagicMock()
    # First call fails, second succeeds
    mock_client._get.side_effect = [Exception("Transient error"), {"id": 123}]

    with patch("time.sleep", return_value=None):  # Skip actual sleeping
        result = get_project_with_retries(mock_client, 123, retries=3)

    assert result == {"id": 123}
    assert mock_client._get.call_count == 2


def test_get_project_with_retries_404_raises_immediately():
    mock_client = MagicMock()
    mock_client._get.side_effect = Exception("404 Not Found")

    with pytest.raises(Exception) as excinfo:
        get_project_with_retries(mock_client, "missing/project")

    assert "404" in str(excinfo.value)
    mock_client._get.assert_called_once()  # Should not retry on 404


def test_get_project_with_retries_all_fail():
    mock_client = MagicMock()
    mock_client._get.side_effect = Exception("Connection error")

    with patch("time.sleep", return_value=None):
        with pytest.raises(Exception) as excinfo:
            get_project_with_retries(mock_client, "fail/project", retries=2)

    assert "Connection error" in str(excinfo.value)
    assert mock_client._get.call_count == 2
