from unittest.mock import MagicMock, patch

import pytest

from Projects.classification import get_project_file_classification
from Projects.compliance_checks import get_project_compliance_report
from Projects.compliance_service import run_project_compliance_checks
from Projects.file_classifier import classify_files
from Projects.license_checker import check_license
from Projects.readme_checker import check_readme
from Projects.templates_checker import check_templates


@pytest.fixture
def mock_gl():
    return MagicMock()


@pytest.fixture
def mock_project():
    project = MagicMock()
    project.repository_tree.return_value = [
        {"name": "README.md", "path": "README.md"},
        {"name": "LICENSE", "path": "LICENSE"},
        {"name": "main.py", "path": "main.py"},
        {"name": "utils.py", "path": "utils.py"},
        {"name": "template.html", "path": "templates/template.html"},
        {"name": "style.css", "path": "css/style.css"},
    ]
    return project


class TestClassifyFiles:
    """Tests for file_classifier.py - classify_files function."""

    def test_classify_files_with_extensions(self, mock_gl, mock_project):
        mock_gl.projects.get.return_value = mock_project

        result = classify_files(mock_gl, 123)

        assert "py" in result
        assert "md" in result
        assert "css" in result
        assert result["py"] == 2
        assert result["md"] == 1

    def test_classify_files_no_extensions(self, mock_gl):
        mock_project = MagicMock()
        mock_project.repository_tree.return_value = [
            {"name": "README"},
            {"name": "Makefile"},
        ]
        mock_gl.projects.get.return_value = mock_project

        result = classify_files(mock_gl, 123)

        assert result == {}

    def test_classify_files_exception_handling(self, mock_gl):
        mock_gl.projects.get.side_effect = Exception("API Error")

        result = classify_files(mock_gl, 123)

        assert "error" in result
        assert "API Error" in result["error"]


class TestCheckLicense:
    """Tests for license_checker.py - check_license function."""

    def test_license_exists(self, mock_gl, mock_project):
        mock_gl.projects.get.return_value = mock_project

        result = check_license(mock_gl, 123)

        assert result["exists"] is True
        assert result["status"] == "LICENSE present"

    def test_license_missing(self, mock_gl):
        mock_project = MagicMock()
        mock_project.repository_tree.return_value = [
            {"name": "README.md"},
        ]
        mock_gl.projects.get.return_value = mock_project

        result = check_license(mock_gl, 123)

        assert result["exists"] is False
        assert result["status"] == "LICENSE missing"

    def test_license_case_insensitive(self, mock_gl):
        mock_project = MagicMock()
        mock_project.repository_tree.return_value = [
            {"name": "license"},
        ]
        mock_gl.projects.get.return_value = mock_project

        result = check_license(mock_gl, 123)

        assert result["exists"] is True

    def test_license_exception(self, mock_gl):
        mock_gl.projects.get.side_effect = Exception("API Error")

        result = check_license(mock_gl, 123)

        assert result["exists"] is False
        assert "Error:" in result["status"]


class TestCheckReadme:
    """Tests for readme_checker.py - check_readme function."""

    def test_readme_exists(self, mock_gl, mock_project):
        mock_gl.projects.get.return_value = mock_project

        result = check_readme(mock_gl, 123)

        assert result["exists"] is True
        assert result["status"] == "README present"

    def test_readme_missing(self, mock_gl):
        mock_project = MagicMock()
        mock_project.repository_tree.return_value = [
            {"name": "LICENSE"},
        ]
        mock_gl.projects.get.return_value = mock_project

        result = check_readme(mock_gl, 123)

        assert result["exists"] is False
        assert result["status"] == "Missing README"

    def test_readme_case_insensitive(self, mock_gl):
        mock_project = MagicMock()
        mock_project.repository_tree.return_value = [
            {"name": "readme.md"},
            {"name": "README"},
        ]
        mock_gl.projects.get.return_value = mock_project

        result = check_readme(mock_gl, 123)

        assert result["exists"] is True

    def test_readme_exception(self, mock_gl):
        mock_gl.projects.get.side_effect = Exception("API Error")

        result = check_readme(mock_gl, 123)

        assert result["exists"] is False
        assert "Error:" in result["status"]


class TestCheckTemplates:
    """Tests for templates_checker.py - check_templates function."""

    def test_templates_exist(self, mock_gl, mock_project):
        mock_gl.projects.get.return_value = mock_project

        result = check_templates(mock_gl, 123)

        assert result["exists"] is True
        assert result["status"] == "Templates present"

    def test_templates_missing(self, mock_gl):
        mock_project = MagicMock()
        mock_project.repository_tree.return_value = [
            {"name": "README.md", "path": "README.md"},
        ]
        mock_gl.projects.get.return_value = mock_project

        result = check_templates(mock_gl, 123)

        assert result["exists"] is False
        assert result["status"] == "Templates missing"

    def test_templates_case_insensitive(self, mock_gl):
        mock_project = MagicMock()
        mock_project.repository_tree.return_value = [
            {"name": "file.md", "path": "TEMPLATE/readme.md"},
        ]
        mock_gl.projects.get.return_value = mock_project

        result = check_templates(mock_gl, 123)

        assert result["exists"] is True

    def test_templates_exception(self, mock_gl):
        mock_gl.projects.get.side_effect = Exception("API Error")

        result = check_templates(mock_gl, 123)

        assert result["exists"] is False
        assert "Error:" in result["status"]


class TestComplianceService:
    """Tests for compliance_service.py - run_project_compliance_checks function."""

    @patch("Projects.compliance_service.check_templates")
    @patch("Projects.compliance_service.check_license")
    @patch("Projects.compliance_service.check_readme")
    @patch("Projects.compliance_service.classify_files")
    def test_run_compliance_checks_all_present(self, mock_classify, mock_readme, mock_license, mock_templates, mock_gl):
        mock_classify.return_value = {"py": 5}
        mock_readme.return_value = {"exists": True, "status": "README present"}
        mock_license.return_value = {"exists": True, "status": "LICENSE present"}
        mock_templates.return_value = {"exists": True, "status": "Templates present"}

        result = run_project_compliance_checks(mock_gl, 123)

        assert "readme" in result
        assert "license" in result
        assert "templates" in result
        assert "file_types" in result
        assert result["file_types"] == {"py": 5}

    @patch("Projects.compliance_service.check_templates")
    @patch("Projects.compliance_service.check_license")
    @patch("Projects.compliance_service.check_readme")
    @patch("Projects.compliance_service.classify_files")
    def test_run_compliance_checks_some_missing(
        self, mock_classify, mock_readme, mock_license, mock_templates, mock_gl
    ):
        mock_classify.return_value = {}
        mock_readme.return_value = {"exists": False, "status": "Missing README"}
        mock_license.return_value = {"exists": False, "status": "LICENSE missing"}
        mock_templates.return_value = {"exists": False, "status": "Templates missing"}

        result = run_project_compliance_checks(mock_gl, 123)

        assert result["readme"]["exists"] is False
        assert result["license"]["exists"] is False
        assert result["templates"]["exists"] is False


class TestClassification:
    """Tests for classification.py - get_project_file_classification function."""

    @patch("Projects.classification.classify_files")
    def test_classification_delegates_to_classify_files(self, mock_classify, mock_gl):
        mock_classify.return_value = {"py": 10, "js": 5}

        result = get_project_file_classification(mock_gl, 123)

        mock_classify.assert_called_once_with(mock_gl, 123)
        assert result == {"py": 10, "js": 5}


class TestComplianceChecks:
    """Tests for compliance_checks.py - get_project_compliance_report function."""

    @patch("Projects.compliance_checks.run_project_compliance_checks")
    def test_compliance_report_delegates(self, mock_run_checks, mock_gl):
        mock_run_checks.return_value = {"readme": {}, "license": {}}

        result = get_project_compliance_report(mock_gl, 123)

        mock_run_checks.assert_called_once_with(mock_gl, 123)
        assert "readme" in result
