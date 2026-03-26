from unittest.mock import MagicMock, patch

import pytest

from modes import bad_mrs_batch


@pytest.fixture
def mock_client():
    m = MagicMock()
    m.client = MagicMock()
    return m

def mock_columns(spec):
    if isinstance(spec, list):
        n = len(spec)
    else:
        n = spec
    return [MagicMock() for _ in range(n)]

def test_render_bad_mrs_batch_ui_generate_success(mock_client):
    # Setup: "Generate Report" is clicked, "Fetch User" is not.
    mock_btn = MagicMock(return_value=True)
    with patch("streamlit.button", mock_btn):
        with patch("streamlit.spinner"):
            rows = [
                {
                    "Username": "user1", "Closed MRs": 10, "No Desc": 1, "Improper Desc": 2,
                    "No Issues": 3, "No Time Spent": 4, "No Unit Tests": 5, "Failed Pipeline": 6,
                    "No Semantic Commits": 7, "No Internal Review": 8, "Merge > 2 Days": 9, "Merge > 1 Week": 0
                }
            ]
            with patch("modes.bad_mrs_batch.fetch_all_bad_mrs", return_value=rows):
                with patch("streamlit.columns", side_effect=mock_columns):
                    with patch("streamlit.dataframe"):
                        with patch("streamlit.download_button"):
                            bad_mrs_batch.render_bad_mrs_batch_ui(mock_client)

def test_render_bad_mrs_batch_ui_not_initialized():
    with patch("streamlit.button", return_value=True):
        with patch("streamlit.error") as mock_err:
            bad_mrs_batch.render_bad_mrs_batch_ui(None)
            mock_err.assert_called_with("GitLab client not initialized. Check URL and Token in the sidebar.")

def test_render_bad_mrs_batch_ui_single_user_success(mock_client):
    # Setup: "Generate Report" not clicked, "Fetch User" clicked.
    # st.button is used for "Generate Report"
    # col2.button is used for "Fetch User"
    with patch("streamlit.button", return_value=False):
        with patch("streamlit.columns") as mock_cols:
            col1, col2 = MagicMock(), MagicMock()
            mock_cols.side_effect = [[col1, col2], [MagicMock()]*4, [MagicMock()]*3, [MagicMock()]*3, [MagicMock()]*3]
            col2.button.return_value = True # Fetch User clicked

            with patch("streamlit.text_input", return_value="john"):
                with patch("streamlit.spinner"):
                    res = {
                        "Username": "john", "Closed MRs": 5, "No Desc": 0, "Improper Desc": 0,
                        "No Issues": 0, "No Time Spent": 0, "No Unit Tests": 0, "Failed Pipeline": 0,
                        "No Semantic Commits": 0, "No Internal Review": 0, "Merge > 2 Days": 0, "Merge > 1 Week": 0
                    }
                    with patch("modes.bad_mrs_batch.fetch_all_bad_mrs", return_value=[res]):
                        with patch("streamlit.success"):
                            with patch("streamlit.metric"):
                                bad_mrs_batch.render_bad_mrs_batch_ui(mock_client)

def test_render_bad_mrs_batch_ui_single_user_empty(mock_client):
    with patch("streamlit.button", return_value=False):
        with patch("streamlit.columns") as mock_cols:
            col1, col2 = MagicMock(), MagicMock()
            mock_cols.return_value = [col1, col2]
            col2.button.return_value = True

            col1.text_input.return_value = ""
            with patch("streamlit.warning") as mock_warn:
                bad_mrs_batch.render_bad_mrs_batch_ui(mock_client)
                mock_warn.assert_called_with("Please enter a username first.")

def test_render_bad_mrs_batch_ui_single_user_no_data(mock_client):
    with patch("streamlit.button", return_value=False):
        with patch("streamlit.columns") as mock_cols:
            col1, col2 = MagicMock(), MagicMock()
            mock_cols.side_effect = [[col1, col2], [MagicMock(), MagicMock()]]
            col2.button.return_value = True

            col1.text_input.return_value = "unknown"
            with patch("modes.bad_mrs_batch.fetch_all_bad_mrs", return_value=[]):
                with patch("streamlit.warning") as mock_warn:
                    bad_mrs_batch.render_bad_mrs_batch_ui(mock_client)
                    mock_warn.assert_called_with("No data found for user 'unknown'.")

def test_render_bad_mrs_batch_ui_single_user_error(mock_client):
    with patch("streamlit.button", return_value=False):
        with patch("streamlit.columns") as mock_cols:
            col1, col2 = MagicMock(), MagicMock()
            mock_cols.return_value = [col1, col2]
            col2.button.return_value = True

            col1.text_input.return_value = "john"
            with patch("modes.bad_mrs_batch.fetch_all_bad_mrs", side_effect=Exception("API Fail")):
                with patch("streamlit.error") as mock_err:
                     with patch("streamlit.spinner"):
                        bad_mrs_batch.render_bad_mrs_batch_ui(mock_client)
                        mock_err.assert_called_with("Error fetching data for john: API Fail")
