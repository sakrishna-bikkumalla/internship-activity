import pytest
from unittest.mock import MagicMock, patch
from issues import issue_ui

def test_render_issue_compliance_ui():
    with patch("streamlit.columns") as mock_cols:
        col1, col2 = MagicMock(), MagicMock()
        mock_cols.return_value = [col1, col2]

        # Scenario 1: Issue missing, MR present
        report = {
            "issue_templates_folder": False,
            "issue_template_files": [],
            "merge_request_templates_folder": True,
            "merge_request_template_files": ["feature.md"]
        }
        issue_ui.render_issue_compliance_ui(report)

        # Scenario 2: Issue present, MR missing
        report2 = {
            "issue_templates_folder": True,
            "issue_template_files": ["bug.md"],
            "merge_request_templates_folder": False,
            "merge_request_template_files": []
        }
        issue_ui.render_issue_compliance_ui(report2)
        assert mock_cols.call_count == 2

def test_render_issue_suggestions():
    with patch("streamlit.markdown") as mock_md:
        with patch("streamlit.image", side_effect=Exception("no image")):
            # Case both missing
            issue_ui.render_issue_suggestions({})
            assert mock_md.call_count >= 3

        # Case both present (no suggestions)
        mock_md.reset_mock()
        issue_ui.render_issue_suggestions({"issue_templates_folder": True, "merge_request_templates_folder": True})
        mock_md.assert_not_called()

def test_render_issue_metrics_ui():
    metrics = {
        "open_issues": 10,
        "assigned_issues": 9,
        "unassigned_issues": 1,
        "assignment_percentage": 90.0
    }
    with patch("streamlit.columns") as mock_cols:
        mock_cols.return_value = [MagicMock(), MagicMock(), MagicMock()]
        with patch("streamlit.metric") as mock_metric:
            issue_ui.render_issue_metrics_ui(metrics)
            assert mock_metric.call_count == 3

    # Test different health levels
    with patch("streamlit.columns") as mock_cols:
        mock_cols.return_value = [MagicMock(), MagicMock(), MagicMock()]
        with patch("streamlit.metric"), patch("streamlit.success") as mock_success:
            issue_ui.render_issue_metrics_ui({"assignment_percentage": 90})
            mock_success.assert_called_once()

        with patch("streamlit.metric"), patch("streamlit.info") as mock_info:
            issue_ui.render_issue_metrics_ui({"assignment_percentage": 70})
            mock_info.assert_called_once()

        with patch("streamlit.metric"), patch("streamlit.warning") as mock_warn:
            issue_ui.render_issue_metrics_ui({"assignment_percentage": 50})
            mock_warn.assert_called_once()

        with patch("streamlit.metric"), patch("streamlit.error") as mock_err:
            issue_ui.render_issue_metrics_ui({"assignment_percentage": 10})
            mock_err.assert_called_once()

def test_render_issue_summary_card():
    summary = {
        "compliance_score": 90,
        "metrics": {"open_issues": 10, "assigned_issues": 10}
    }
    with patch("streamlit.markdown") as mock_md:
        with patch("streamlit.expander") as mock_exp:
            # Mock expander as context manager
            mock_exp.return_value.__enter__.return_value = MagicMock()
            with patch("streamlit.columns") as mock_cols:
                mock_cols.return_value = [MagicMock(), MagicMock()]
                issue_ui.render_issue_summary_card(summary)
                assert mock_md.call_count >= 1

    # Test different score colors
    for score in [90, 75, 55, 10]:
        with patch("streamlit.markdown"), patch("streamlit.expander") as mock_exp:
            mock_exp.return_value.__enter__.return_value = MagicMock()
            with patch("streamlit.columns") as mock_cols:
                mock_cols.return_value = [MagicMock(), MagicMock()]
                issue_ui.render_issue_summary_card({"compliance_score": score})
