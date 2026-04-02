from unittest.mock import MagicMock, patch

from gitlab_compliance_checker.services.batch.batch_service import process_single_project


class TestBatchService:
    """Tests for batch_mode/batch_service.py - process_single_project function."""

    @patch("gitlab_compliance_checker.services.batch.batch_service.run_project_compliance_checks")
    def test_process_single_project_success(self, mock_run):
        """Test that process_single_project returns the report on success."""
        gl_client = MagicMock()
        mock_report = {"dx_score": 85, "tools": {"project_type": "Python"}}
        mock_run.return_value = mock_report

        result = process_single_project(gl_client, "123", include_details=True)
        assert result == mock_report
        mock_run.assert_called_once()

    @patch("gitlab_compliance_checker.services.batch.batch_service.run_project_compliance_checks")
    def test_process_single_project_without_details(self, mock_run):
        """Test process_single_project without details flag."""
        gl_client = MagicMock()
        mock_report = {"dx_score": 85, "tools": {"project_type": "Python"}}
        mock_run.return_value = mock_report

        result = process_single_project(gl_client, "456", include_details=False)
        assert result == {"project_id": "456", "dx_score": 85, "project_type": "Python"}

    @patch("gitlab_compliance_checker.services.batch.batch_service.run_project_compliance_checks")
    def test_process_single_project_error(self, mock_run):
        """Test process_single_project handling error."""
        gl_client = MagicMock()
        mock_run.side_effect = Exception("API Error")

        result = process_single_project(gl_client, "789")
        assert "error" in result
        assert result["error"] == "API Error"
        assert result["dx_score"] == 0
