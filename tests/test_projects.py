import base64
from unittest.mock import MagicMock, patch

import pytest

from gitlab_compliance_checker.services.compliance.classification import get_project_file_classification
from gitlab_compliance_checker.services.compliance.compliance_checks import get_project_compliance_report
from gitlab_compliance_checker.services.compliance.compliance_service import run_project_compliance_checks
from gitlab_compliance_checker.services.compliance.file_classifier import classify_files
from gitlab_compliance_checker.services.compliance.license_checker import check_license
from gitlab_compliance_checker.services.compliance.readme_checker import check_readme
from gitlab_compliance_checker.services.compliance.templates_checker import check_templates


@pytest.fixture
def mock_gl():
    return MagicMock()


@pytest.fixture
def mock_project():
    project = MagicMock()
    project.default_branch = "main"
    project.repository_tree.return_value = [
        {"name": "README.md", "path": "README.md", "type": "blob"},
        {"name": "LICENSE", "path": "LICENSE", "type": "blob"},
        {"name": "main.py", "path": "main.py", "type": "blob"},
        {"name": "utils.py", "path": "utils.py", "type": "blob"},
        {"name": "template.html", "path": "templates/template.html", "type": "blob"},
        {"name": "style.css", "path": "css/style.css", "type": "blob"},
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
        mock_file = MagicMock()
        mock_file.content = base64.b64encode(b"Affero General Public License version 3 19 November 2007").decode(
            "utf-8"
        )
        mock_project.files.get.return_value = mock_file

        result = check_license(mock_gl, 123)

        assert result["exists"] is True
        assert result["valid"] is True
        assert "AGPLv3" in result["status"]

    def test_license_missing(self, mock_gl, mock_project):
        mock_gl.projects.get.return_value = mock_project
        mock_project.files.get.side_effect = Exception("Not Found")

        result = check_license(mock_gl, 123)

        assert result["exists"] is False
        assert "missing" in result["status"].lower()

    def test_license_case_insensitive(self, mock_gl, mock_project):
        mock_gl.projects.get.return_value = mock_project
        mock_file = MagicMock()
        mock_file.content = base64.b64encode(b"Affero General Public License version 3 19 November 2007").decode(
            "utf-8"
        )

        # Simulate variant check
        def side_effect(file_path, ref):
            if file_path == "LICENSE":
                return mock_file
            raise Exception("Not Found")

        mock_project.files.get.side_effect = side_effect

        result = check_license(mock_gl, 123)

        assert result["exists"] is True
        assert result["valid"] is True


class TestCheckReadme:
    """Tests for readme_checker.py - check_readme function."""

    def test_readme_exists(self, mock_gl, mock_project):
        mock_gl.projects.get.return_value = mock_project
        mock_file = MagicMock()
        # Sufficient length and sections
        mock_file.content = base64.b64encode(b"README\nInstallation\nUsage\nLicense\n" + b"x" * 150).decode("utf-8")
        mock_project.files.get.return_value = mock_file

        result = check_readme(mock_gl, 123)

        assert result["exists"] is True
        assert result["needs_improvement"] is False

    def test_readme_missing(self, mock_gl, mock_project):
        mock_gl.projects.get.return_value = mock_project
        mock_project.files.get.side_effect = Exception("Not Found")

        result = check_readme(mock_gl, 123)

        assert result["exists"] is False
        assert "Missing" in result["status"]

    def test_readme_case_insensitive(self, mock_gl, mock_project):
        mock_gl.projects.get.return_value = mock_project
        mock_file = MagicMock()
        mock_file.content = base64.b64encode(b"README content").decode("utf-8")

        def side_effect(file_path, ref):
            if file_path == "README.md":
                return mock_file
            raise Exception("Not Found")

        mock_project.files.get.side_effect = side_effect

        result = check_readme(mock_gl, 123)

        assert result["exists"] is True


class TestCheckTemplates:
    """Tests for templates_checker.py - check_templates function."""

    def test_templates_exist(self, mock_gl, mock_project):
        mock_gl.projects.get.return_value = mock_project

        def side_effect(path, ref):
            if path == ".gitlab/issue_templates":
                return [{"name": "Bug.md"}]
            if path == ".gitlab/merge_request_templates":
                return [{"name": "Feature.md"}]
            return []

        mock_project.repository_tree.side_effect = side_effect

        result = check_templates(mock_gl, 123)

        assert result["exists"] is True
        assert result["issue_templates_folder"] is True
        assert "Bug.md" in result["issue_template_files"]

    def test_templates_missing(self, mock_gl, mock_project):
        mock_gl.projects.get.return_value = mock_project
        mock_project.repository_tree.return_value = []

        result = check_templates(mock_gl, 123)

        assert result["exists"] is False

    def test_templates_exception(self, mock_gl, mock_project):
        mock_gl.projects.get.return_value = mock_project
        mock_project.repository_tree.side_effect = Exception("API Error")

        result = check_templates(mock_gl, 123)

        assert "error" not in result  # it catches internal exceptions per path
        assert result["exists"] is False


class TestComplianceService:
    """Tests for compliance_service.py - run_project_compliance_checks function."""

    @patch("gitlab_compliance_checker.services.compliance.compliance_service.check_templates")
    @patch("gitlab_compliance_checker.services.compliance.compliance_service.check_license")
    @patch("gitlab_compliance_checker.services.compliance.compliance_service.check_readme")
    @patch("gitlab_compliance_checker.services.compliance.compliance_service.classify_files")
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

    @patch("gitlab_compliance_checker.services.compliance.compliance_service.check_templates")
    @patch("gitlab_compliance_checker.services.compliance.compliance_service.check_license")
    @patch("gitlab_compliance_checker.services.compliance.compliance_service.check_readme")
    @patch("gitlab_compliance_checker.services.compliance.compliance_service.classify_files")
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

    @patch("gitlab_compliance_checker.services.compliance.classification.classify_files")
    def test_classification_delegates_to_classify_files(self, mock_classify, mock_gl):
        mock_classify.return_value = {"py": 10, "js": 5}

        result = get_project_file_classification(mock_gl, 123)

        mock_classify.assert_called_once_with(mock_gl, 123)
        assert result == {"py": 10, "js": 5}


class TestComplianceChecks:
    """Tests for compliance_checks.py - get_project_compliance_report function."""

    @patch("gitlab_compliance_checker.services.compliance.compliance_checks.run_project_compliance_checks")
    def test_compliance_report_delegates(self, mock_run_checks, mock_gl):
        mock_run_checks.return_value = {"readme": {}, "license": {}}

        result = get_project_compliance_report(mock_gl, 123)

        mock_run_checks.assert_called_once_with(mock_gl, 123)
        assert "readme" in result
