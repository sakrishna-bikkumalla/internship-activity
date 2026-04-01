from gitlab_utils.pipeline_checker import check_ci_pipeline

VALID_YAML = """
stages:
  - test
  - lint
  - format

my_test_job:
  stage: test
  script:
    - pytest tests/

my_lint_job:
  stage: lint
  script: ruff check .

my_format_job:
  stage: format
  script: black .

type_check_job:
  stage: type_check
  script: mypy src/

coverage_job:
  stage: coverage
  script: pytest-cov
"""

INVALID_YAML = """
build_job:
  stage: build
  script: echo "hello world"

test_job:
  stage: test
  script: echo "running tests"
"""


def test_valid_ci_pipeline() -> None:
    result = check_ci_pipeline(VALID_YAML)
    assert not result["missing_stages"]
    assert len(result["stages_present"]) == 5
    assert not result["issues"]

    for stage in ["test", "lint", "format", "type_check", "coverage"]:
        assert result["jobs"][stage]["stage_present"] is True
        assert result["jobs"][stage]["job_present"] is True
        assert result["jobs"][stage]["tool_detected"] is True


def test_invalid_ci_pipeline() -> None:
    result = check_ci_pipeline(INVALID_YAML)
    assert result["stages_present"] == ["test"]
    assert "lint" in result["missing_stages"]
    assert "format" in result["missing_stages"]
    assert "type_check" in result["missing_stages"]
    assert "coverage" in result["missing_stages"]

    assert result["jobs"]["test"]["stage_present"] is True
    assert result["jobs"]["test"]["job_present"] is True
    assert result["jobs"]["test"]["tool_detected"] is False

    assert "Stage 'test' missing expected tools (pytest/unittest)" in result["issues"]
    assert "Missing stage: lint" in result["issues"]


def test_empty_yaml() -> None:
    result = check_ci_pipeline("")
    assert "Invalid or empty YAML content" in result.get("error", "")
    assert result["stages_present"] == []
    assert len(result["missing_stages"]) == 5
