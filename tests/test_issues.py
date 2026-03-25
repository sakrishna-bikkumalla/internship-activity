import pytest
from unittest.mock import MagicMock, patch
from issues import issue_metrics, issue_service

# --- Tests for issue_metrics.py ---

def test_get_open_issues_count():
    assert issue_metrics.get_open_issues_count(5) == 5
    assert issue_metrics.get_open_issues_count("Error") == "Error"
    assert issue_metrics.get_open_issues_count(None) == "N/A"

def test_get_assigned_issues_count():
    assert issue_metrics.get_assigned_issues_count({"assigned_issues_count": 3}) == 3
    assert issue_metrics.get_assigned_issues_count({}) == 0

def test_calculate_issue_metrics():
    res = issue_metrics.calculate_issue_metrics(10, 7)
    assert res["open_issues"] == 10
    assert res["assigned_issues"] == 7
    assert res["unassigned_issues"] == 3
    assert res["assignment_percentage"] == 70.0

    # Zero case
    res = issue_metrics.calculate_issue_metrics(0, 0)
    assert res["assignment_percentage"] == 0.0

def test_summarize_issue_compliance():
    templates = {"is_valid": True, "missing_issues": False, "missing_mrs": False, "has_recommended_templates": True}
    res = issue_metrics.summarize_issue_compliance(templates, 10, 9)
    assert res["templates_compliant"] is True
    assert res["metrics"]["open_issues"] == 10
    assert res["compliance_score"] == 100

def test_calculate_compliance_score_scenarios():
    m1 = {"open_issues": 10, "assignment_percentage": 95}
    t1 = {"is_valid": True}
    assert issue_metrics.calculate_compliance_score(t1, m1) == 100

    # partial templates
    t2 = {"is_valid": False, "has_recommended_templates": True}
    assert issue_metrics.calculate_compliance_score(t2, m1) == 80 # 30 + 50

    # only issues
    t3 = {"is_valid": False, "missing_issues": False}
    assert issue_metrics.calculate_compliance_score(t3, m1) == 75 # 25 + 50

    # only mrs
    t4 = {"is_valid": False, "missing_issues": True, "missing_mrs": False}
    assert issue_metrics.calculate_compliance_score(t4, m1) == 70 # 20 + 50

    # No issues
    m2 = {"open_issues": 0}
    assert issue_metrics.calculate_compliance_score(t1, m2) == 100 # 50 + 50

    # medium assignment
    m4 = {"open_issues": 10, "assignment_percentage": 75}
    assert issue_metrics.calculate_compliance_score(t1, m4) == 85 # 50 + 35

    m5 = {"open_issues": 10, "assignment_percentage": 55}
    assert issue_metrics.calculate_compliance_score(t1, m5) == 70 # 50 + 20

    # very low assignment
    m6 = {"open_issues": 10, "assignment_percentage": 10}
    assert issue_metrics.calculate_compliance_score(t1, m6) == 60 # 50 + 10

# --- Tests for issue_service.py ---

def test_check_templates_presence_success():
    project = MagicMock()
    project.repository_tree.side_effect = [
        [{"name": "bug.md"}, {"name": "other.txt"}],
        [{"name": "feature.md"}]
    ]
    res = issue_service.check_templates_presence(project)
    assert res["issue_templates_folder"] is True
    assert res["issue_template_files"] == ["bug.md"]
    assert res["merge_request_templates_folder"] is True

def test_check_templates_presence_fail():
    project = MagicMock()
    project.repository_tree.side_effect = Exception("error")
    res = issue_service.check_templates_presence(project)
    assert res["issue_templates_folder"] is False

def test_validate_issue_templates():
    data = {
        "issue_templates_folder": True,
        "issue_template_files": ["bug.md"],
        "merge_request_templates_folder": True,
        "merge_request_template_files": ["feature.md"]
    }
    res = issue_service.validate_issue_templates(data)
    assert res["is_valid"] is True
    assert res["has_recommended_templates"] is True

    # missing one
    data["merge_request_templates_folder"] = False
    res = issue_service.validate_issue_templates(data)
    assert res["is_valid"] is False

def test_get_issue_summary():
    project = MagicMock()
    with patch("issues.issue_service.check_templates_presence") as mock_presence:
        mock_presence.return_value = {"issue_template_files": ["f1.md"], "merge_request_template_files": []}
        res = issue_service.get_issue_summary(project)
        assert res["total_issue_templates"] == 1
        assert res["total_mr_templates"] == 0
