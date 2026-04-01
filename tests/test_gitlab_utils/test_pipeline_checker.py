import pytest
from gitlab_utils.pipeline_checker import check_ci_pipeline

def test_invalid_ci_pipeline():
    """Test with invalid YAML content."""
    invalid_content = "invalid: yaml: : content"
    result = check_ci_pipeline(invalid_content)
    
    # In the current implementation, invalid non-empty YAML returns a full result dict
    # with an error issue, but not a top-level "error" key unless it's empty.
    assert any("Invalid" in issue["message"] for issue in result["issues"])
    assert result["dx_score"] == 0

def test_empty_yaml():
    """Test with empty YAML content."""
    empty_content = ""
    result = check_ci_pipeline(empty_content)
    
    assert result["error"] == "Empty .gitlab-ci.yml content"
    assert result["dx_score"] == 0

def test_missing_stages():
    """Test when stages are missing."""
    content = """
    test_job:
      script:
        - echo "hello"
    """
    result = check_ci_pipeline(content)
    
    assert "No explicit 'stages:' defined in CI" in [i["message"] for i in result["issues"]]
    # It should still find the test_job and assume stage 'test'
    assert result["jobs"]["test"]["job_present"] is True

def test_full_valid_pipeline():
    """Test a full valid pipeline."""
    content = """
    stages:
      - test
      - lint
      - format
      - type_check
      - coverage

    test_job:
      stage: test
      script:
        - pytest
    
    lint_job:
      stage: lint
      script:
        - ruff
    
    format_job:
      stage: format
      script:
        - black
    
    type_job:
      stage: type_check
      script:
        - mypy
    
    cov_job:
      stage: coverage
      script:
        - pytest --cov
    """
    result = check_ci_pipeline(content)
    
    assert result["dx_score"] == 10.0
    assert not any(i["severity"] == "error" for i in result["issues"])
    for stage in ["test", "lint", "format", "type_check", "coverage"]:
        assert result["jobs"][stage]["tool_detected"] is True
