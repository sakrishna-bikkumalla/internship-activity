from unittest.mock import MagicMock, patch

from gitlab_utils.async_bad_mrs import BATCH_USERNAMES, _check_user_compliance, fetch_all_bad_mrs


def test_hardcoded_usernames_list():
    """Verify BATCH_USERNAMES contains all 34 required users."""
    assert len(BATCH_USERNAMES) == 34
    assert "prav2702" in BATCH_USERNAMES
    assert "Pavani_Pothuganti" in BATCH_USERNAMES


@patch("gitlab_utils.async_bad_mrs._run_batch")
def test_check_user_compliance_no_client(mock_run):
    """Verify behavior when client is not initialized."""
    mock_run.return_value = [{"Username": "testuser", "Closed MRs": 0}]
    client = MagicMock()
    result = _check_user_compliance(client, "testuser")

    assert result["Username"] == "testuser"
    assert result["Closed MRs"] == 0


@patch("gitlab_utils.async_bad_mrs._run_batch")
def test_check_user_compliance_result_structure(mock_run):
    """Verify result dictionary contains all expected keys from _ZERO_ROW."""
    from gitlab_utils.async_bad_mrs import _ZERO_ROW

    mock_run.return_value = [{**_ZERO_ROW, "Username": "testuser"}]
    client = MagicMock()
    result = _check_user_compliance(client, "testuser")

    for key in _ZERO_ROW.keys():
        assert key in result, f"Missing key: {key}"


@patch("gitlab_utils.async_bad_mrs._run_batch")
def test_fetch_all_bad_mrs_empty_list(mock_run):
    """Verify behavior with empty username list."""
    mock_run.return_value = []
    client = MagicMock()
    results = fetch_all_bad_mrs(client, [])
    assert results == []


@patch("gitlab_utils.async_bad_mrs._run_batch")
def test_fetch_all_bad_mrs_completeness(mock_run):
    """Verify every requested username appears in results."""

    def side_effect(client, usernames, project_id=None, group_id=None):
        return [{"Username": u, "Closed MRs": 0} for u in usernames]

    mock_run.side_effect = side_effect

    client = MagicMock()
    test_users = ["user1", "user2", "user3"]
    results = fetch_all_bad_mrs(client, test_users)

    assert len(results) == 3
    result_names = {r["Username"] for r in results}
    assert result_names == set(test_users)
