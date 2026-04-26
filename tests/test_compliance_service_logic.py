from unittest.mock import MagicMock, patch
import pytest
from gitlab_compliance_checker.services.compliance import compliance_service

@pytest.fixture
def mock_gl():
    m = MagicMock()
    m._get.return_value = {"default_branch": "main"}
    return m

def test_run_project_compliance_checks(mock_gl):
    with patch("gitlab_compliance_checker.services.compliance.compliance_service.check_readme") as m_readme, \
         patch("gitlab_compliance_checker.services.compliance.compliance_service.check_license") as m_license, \
         patch("gitlab_compliance_checker.services.compliance.compliance_service.check_templates") as m_temp, \
         patch("gitlab_compliance_checker.services.compliance.compliance_service.check_metadata") as m_meta, \
         patch("gitlab_compliance_checker.services.compliance.compliance_service.classify_files") as m_class, \
         patch("gitlab_compliance_checker.services.compliance.compliance_service.check_tools") as m_tools, \
         patch("gitlab_compliance_checker.services.compliance.compliance_service.check_ci_pipeline") as m_ci:
        
        m_readme.return_value = {"found": True}
        m_license.return_value = {"valid": True}
        m_temp.return_value = {"found": True}
        m_meta.return_value = {"found": True}
        m_class.return_value = {"types": []}
        m_tools.return_value = {"project_type": "Python", "dx_score": 80}
        m_ci.return_value = {"recommendations": []}

        # Mock gitlab-ci.yml fetch
        mock_gl._get.side_effect = [
            {"default_branch": "main"}, # project info
            {"content": "Y2kvY29udGVudA=="} # .gitlab-ci.yml content
        ]

        report = compliance_service.run_project_compliance_checks(mock_gl, 123)
        assert report["dx_score"] == 80
        assert report["readme"]["found"] is True

def test_get_dx_suggestions():
    report = {
        "tools": {
            "project_type": "Python",
            "quality_tools": {"ruff": False, "mypy": False},
            "security": {"secret_scanning": False},
            "automation": {"git_cliff": False},
        },
        "license": {"valid": False},
        "readme": {"needs_improvement": True},
        "dx_ci": {"recommendations": [{"message": "Slow pipeline", "command": "Optimize"}]}
    }
    
    suggestions = compliance_service.get_dx_suggestions(report)
    items = [s["item"] for s in suggestions]
    assert "Ruff" in items
    assert "Mypy" in items
    assert "Secret Scanning" in items
    assert "License" in items
    assert "CI Pipeline" in items

def test_get_dx_suggestions_js():
    report = {
        "tools": {
            "project_type": "JavaScript",
            "quality_tools": {"biome": False, "eslint": False, "knip": False},
            "security": {"secret_scanning": True},
            "automation": {"git_cliff": True},
        },
        "license": {"valid": True},
        "readme": {"needs_improvement": False},
    }
    suggestions = compliance_service.get_dx_suggestions(report)
    items = [s["item"] for s in suggestions]
    assert "Biome/ESLint" in items
    assert "Knip" in items
