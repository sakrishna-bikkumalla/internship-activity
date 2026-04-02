from gitlab_compliance_checker.infrastructure.gitlab.pipeline_checker import check_ci_pipeline


def test_structured_recommendations():
    """Test that recommendations are returned correctly."""
    # Invalid but non-empty content should not return early with dx_score 0
    # and should trigger recommendations for a Python project
    result = check_ci_pipeline("not: a: valid: ci", project_type="Python")

    recs = result.get("recommendations", [])
    assert len(recs) > 0

    # Check for specific Python recommendations
    messages = [r["message"] for r in recs]
    assert "Add Ruff for linting" in messages
    assert "Add Ruff for formatting" in messages


def test_coverage_fallback():
    """Test that coverage tool in test stage is detected."""
    content = """
    stages:
      - test
    
    test_job:
      stage: test
      script:
        - pytest --cov=app
    """
    result = check_ci_pipeline(content)

    assert result["jobs"]["coverage"]["tool_detected"] is True
    assert result["jobs"]["coverage"]["note"] == "Coverage detected in test stage"


def test_unconditional_when_never():
    """Test that unconditional 'when: never' jobs are ignored."""
    content = """
    stages:
      - test
    
    ignored_job:
      stage: test
      script:
        - pytest
      rules:
        - when: never
    """
    result = check_ci_pipeline(content)
    assert result["jobs"]["test"]["job_present"] is False


def test_manual_jobs_ignored():
    """Test that manual jobs are ignored."""
    content = """
    manual_job:
      stage: test
      script:
        - pytest
      when: manual
    """
    result = check_ci_pipeline(content)
    assert result["jobs"]["test"]["job_present"] is False


def test_dx_score_calculation():
    """Test the weighted DX score calculation."""
    content = """
    stages:
      - test
    
    test_job:
      stage: test
      script:
        - pytest
    """
    result = check_ci_pipeline(content)
    # test stage weight is 3. Total weights = 10 (3+2+1+2+2)
    # test_job present = 3 * 0.5 = 1.5
    # pytest detected = 3 * 0.5 = 1.5
    # Total raw score = 3.0
    # dx_score = (3.0 / 10.0) * 10 = 3.0
    assert result["dx_score"] == 3.0
