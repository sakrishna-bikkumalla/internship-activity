import pytest
from unittest.mock import MagicMock, patch
from batch_mode.batch_ui import BatchProcessingService

@pytest.fixture
def mock_gl():
    return MagicMock()

@pytest.fixture
def service(mock_gl):
    return BatchProcessingService(mock_gl)

def test_process_project_success(service, mock_gl):
    # Mock dependencies
    with patch("batch_mode.batch_ui.get_project_with_retries") as mock_get:
        proj = MagicMock()
        proj.id = 123
        proj.path_with_namespace = "gp/p1"
        proj.default_branch = "main"
        mock_get.return_value = proj

        with patch("batch_mode.batch_ui.check_project_compliance") as mock_comp:
            mock_comp.return_value = {"license_status": "valid", "license_valid": True, "readme_status": "present", "readme_sections": ["s1"]}

            with patch("batch_mode.batch_ui.list_all_files") as mock_list:
                mock_list.return_value = ["f1.py", "README.md"]

                with patch("batch_mode.batch_ui.classify_repository_files") as mock_class:
                    mock_class.return_value = {"python_files": ["f1.py"], "common_requirements": ["r1.txt"]}

                    res = service.process_project("gp/p1")
                    assert res["project"] == proj
                    assert res["error"] is None

                    # Test create_summary_rows
                    rows = service.create_summary_rows([res])
                    assert len(rows) == 1
                    assert rows[0]["project_id"] == 123
                    assert rows[0]["python_count"] == 1

def test_process_project_failure(service, mock_gl):
    with patch("batch_mode.batch_ui.get_project_with_retries", side_effect=Exception("API Error")):
        res = service.process_project("bad")
        assert res["error"] == "API Error"

        # Test summary rows for error
        rows = service.create_summary_rows([res])
        assert len(rows) == 1
        assert rows[0]["readme_status"] == "error"

def test_process_projects_batch(service):
    with patch.object(BatchProcessingService, "process_project", return_value={"id": 1}):
        res = service.process_projects(["p1", "p2"])
        assert len(res) == 2

def test_create_summary_rows_missing_data(service):
    # Case where results don't have proj/report/class
    res = {"error": None, "project": None}
    rows = service.create_summary_rows([res])
    assert len(rows) == 0
