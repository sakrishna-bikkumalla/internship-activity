from gitlab_utils.pipeline_checker import check_ci_pipeline

def test_active_vs_inactive_jobs():
    yaml_content = """
stages:
  - test

hidden_job:
  .template: true
  script: echo "hidden"

inactive_never:
  stage: test
  script: pytest
  rules:
    - when: never

active_conditional_never:
  stage: test
  script: pytest
  rules:
    - if: '$CI_COMMIT_BRANCH == "main"'
      when: never
    - when: on_success

active_test:
  stage: test
  script: pytest
"""
    result = check_ci_pipeline(yaml_content)
    
    job_names = result["jobs"]["test"]["job_names"]
    
    # hidden_job starts with . but it's actually the KEY that counts for Gitlab.
    # Wait, in Gitlab, hidden jobs are those whose KEY starts with '.'.
    # I should update my script to check the key.
    
    # In my yaml_content above:
    # hidden_job is NOT hidden. .hidden_job WOULD be hidden.
    
    yaml_with_hidden = """
.hidden_job:
  script: pytest
test_job:
  script: pytest
"""
    result_hidden = check_ci_pipeline(yaml_with_hidden)
    assert "test_job" in result_hidden["jobs"]["test"]["job_names"]
    assert ".hidden_job" not in result_hidden["jobs"]["test"]["job_names"]

    # Inactive never (unconditional)
    assert "inactive_never" not in job_names
    # Active conditional never (has 'if')
    assert "active_conditional_never" in job_names

def test_indirect_execution_detection():
    yaml_content = """
test_job:
  stage: test
  script:
    - make test
lint_job:
  stage: lint
  script: bash run_lint.sh
"""
    result = check_ci_pipeline(yaml_content)
    assert result["jobs"]["test"]["indirect_execution"] is True
    assert result["jobs"]["lint"]["indirect_execution"] is True
    
    # Check warning
    warnings = [i["message"] for i in result["issues"] if i["severity"] == "warning"]
    assert any("indirect script execution" in w for w in warnings)

def test_weighted_scoring():
    # Only test stage present with tool
    yaml_test_only = """
test:
  stage: test
  script: pytest
"""
    result = check_ci_pipeline(yaml_test_only)
    # test weight is 3.
    # stage present (1.5) + tool detected (1.5) = 3.0
    # total possible = 3+2+1+2+2 = 10.
    # normalized = (3/10)*10 = 3.0
    assert result["dx_score"] == 3.0

    # test + lint with tools
    yaml_test_lint = """
test:
  stage: test
  script: pytest
lint:
  stage: lint
  script: ruff check .
"""
    result_tl = check_ci_pipeline(yaml_test_lint)
    # test(3) + lint(2) = 5.0
    assert result_tl["dx_score"] == 5.0

def test_structured_recommendations():
    yaml_empty = """
test:
  script: echo "no tools"
"""
    result = check_ci_pipeline(yaml_empty)
    recs = result["recommendations"]
    
    assert len(recs) > 0
    assert "message" in recs[0]
    assert "command" in recs[0]
    assert "severity" in recs[0]
    
    # Check for specific high severity recs
    high_recs = [r for r in recs if r["severity"] == "high"]
    assert any("Ruff" in r["message"] for r in high_recs)
