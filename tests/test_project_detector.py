"""Tests for project type detection."""

import pytest

from Projects.project_detector import detect_project_type


class TestDetectProjectType:
    """Test cases for detect_project_type function."""

    def test_python_project_with_pyproject_toml(self):
        """Detect Python project with pyproject.toml."""
        filenames = ["pyproject.toml", "README.md", "main.py"]
        assert detect_project_type(filenames) == "Python"

    def test_python_project_with_uv_lock(self):
        """Detect Python project with uv.lock."""
        filenames = ["uv.lock", "src/app.py"]
        assert detect_project_type(filenames) == "Python"

    def test_javascript_project_with_package_json(self):
        """Detect JavaScript project with package.json."""
        filenames = ["package.json", "README.md", "index.js"]
        assert detect_project_type(filenames) == "JavaScript"

    def test_javascript_project_with_package_lock(self):
        """Detect JavaScript project with package-lock.json."""
        filenames = ["package-lock.json", "src/index.js"]
        assert detect_project_type(filenames) == "JavaScript"

    def test_javascript_project_with_bun_lock(self):
        """Detect JavaScript project with bun.lock."""
        filenames = ["bun.lock", "package.json"]
        assert detect_project_type(filenames) == "JavaScript"

    def test_combined_python_and_javascript(self):
        """Detect combined Python and JavaScript project."""
        filenames = ["pyproject.toml", "package.json", "README.md"]
        assert detect_project_type(filenames) == "Python & JavaScript"

    def test_combined_python_and_javascript_with_locks(self):
        """Detect combined project with lock files."""
        filenames = ["uv.lock", "package-lock.json", "main.py"]
        assert detect_project_type(filenames) == "Python & JavaScript"

    def test_unknown_project_type(self):
        """Detect unknown project type when no config files present."""
        filenames = ["README.md", "main.go", "Dockerfile"]
        assert detect_project_type(filenames) == "Unknown"

    def test_empty_file_list(self):
        """Detect unknown project type with empty file list."""
        filenames = []
        assert detect_project_type(filenames) == "Unknown"

    def test_case_sensitive_matching(self):
        """Test that matching is case-sensitive (lowercase expected)."""
        filenames = ["PyProject.toml", "Package.json"]
        assert detect_project_type(filenames) == "Unknown"

    def test_only_requirements_txt_not_python(self):
        """requirements.txt alone should not detect Python."""
        filenames = ["requirements.txt", "main.py"]
        assert detect_project_type(filenames) == "Unknown"

    def test_only_yarn_lock_not_javascript(self):
        """yarn.lock alone should not detect JavaScript."""
        filenames = ["yarn.lock", "index.js"]
        assert detect_project_type(filenames) == "Unknown"
