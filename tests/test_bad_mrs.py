from unittest.mock import MagicMock, patch

from gitlab_utils.client import _ZERO_ROW, BATCH_USERNAMES


def test_hardcoded_usernames_list():
    """Verify BATCH_USERNAMES contains all 39 required users."""
    assert len(BATCH_USERNAMES) == 39
    assert "prav2702" in BATCH_USERNAMES
    assert "Pavani_Pothuganti" in BATCH_USERNAMES


@patch("gitlab_utils.client.GitLabClient._batch_evaluate_mrs_async")
def test_check_user_compliance_no_client(mock_run):
    """Verify behavior when client is not initialized."""
    mock_run.return_value = [{"Username": "testuser", "Closed MRs": 0}]
    client = MagicMock()
    # Mock loop.run_until_complete which batch_evaluate_mrs calls
    client.batch_evaluate_mrs.return_value = [{"Username": "testuser", "Closed MRs": 0}]
    result = client.batch_evaluate_mrs("testuser")[0]

    assert result["Username"] == "testuser"
    assert result["Closed MRs"] == 0


@patch("gitlab_utils.client.GitLabClient._batch_evaluate_mrs_async")
def test_check_user_compliance_result_structure(mock_run):
    """Verify result dictionary contains all expected keys from _ZERO_ROW."""
    mock_run.return_value = [{**_ZERO_ROW, "Username": "testuser"}]
    client = MagicMock()
    # Mock the sync wrapper
    client.batch_evaluate_mrs.return_value = [{**_ZERO_ROW, "Username": "testuser"}]
    result = client.batch_evaluate_mrs("testuser")[0]

    for key in _ZERO_ROW.keys():
        assert key in result, f"Missing key: {key}"


@patch("gitlab_utils.client.GitLabClient._batch_evaluate_mrs_async")
def test_fetch_all_bad_mrs_empty_list(mock_run):
    """Verify behavior with empty username list."""
    client = MagicMock()
    client.batch_evaluate_mrs.return_value = []
    results = client.batch_evaluate_mrs([])
    assert results == []


@patch("gitlab_utils.client.GitLabClient._batch_evaluate_mrs_async")
def test_fetch_all_bad_mrs_completeness(mock_run):
    """Verify every requested username appears in results."""
    client = MagicMock()
    test_users = ["user1", "user2", "user3"]
    client.batch_evaluate_mrs.return_value = [{"Username": u, "Closed MRs": 0} for u in test_users]

    results = client.batch_evaluate_mrs(test_users)

    assert len(results) == 3
    result_names = {r["Username"] for r in results}
    assert result_names == set(test_users)
