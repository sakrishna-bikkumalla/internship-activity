import re
from typing import Any, Dict, List

import yaml

EXPECTED_STAGES = ["test", "lint", "format", "type_check", "coverage"]

STAGE_TOOLS = {
    "test": ["pytest", "unittest", "jest", "vitest", "mocha", "ava", "cypress", "playwright"],
    "lint": ["ruff", "flake8", "pylint", "eslint", "biome", "jshint", "stylelint"],
    "format": ["black", "isort", "prettier", "biome", "clang-format"],
    "type_check": ["mypy", "pyright", "tsc", "typescript", "flow"],
    "coverage": ["coverage", "pytest-cov", "pytest --cov", "istanbul", "nyc", "c8", "vitest run --coverage"],
}

# New weighted scoring per stage
STAGE_WEIGHTS = {
    "test": 3,
    "lint": 2,
    "format": 1,
    "type_check": 2,
    "coverage": 2,
}


def _parse_yaml(content: str) -> Dict[str, Any]:
    """
    Robust YAML parsing using yaml.safe_load.
    Handles empty, invalid, or non-dictionary YAML safely.
    """
    try:
        data = yaml.safe_load(content)
        if isinstance(data, dict):
            return data
        return {}
    except yaml.YAMLError:
        return {}


def contains_tool(script_text: str, tools: List[str]) -> List[str]:
    """
    Returns list of detected tools using regex matching.
    Improved to match tools that might be part of a command (e.g., 'pytest-cov' should match if 'pytest' is in tools)
    while still using boundaries to avoid matching 'py' in 'pytest'.
    """
    detected = []
    for tool in tools:
        # We want to match 'tool' as a whole word, allowing hyphens as part of the word
        # This matches 'pytest' in 'pytest --cov' but also 'pytest-cov' in 'pytest-cov .'
        # We use word boundaries \b but need to be careful with hyphens.

        # Simple heuristic: look for the tool as a word, or as part of a hyphenated word
        pattern = rf"\b{re.escape(tool)}\b"
        if re.search(pattern, script_text, re.IGNORECASE):
            detected.append(tool)
    return detected


def is_active_job(job: Dict[str, Any]) -> bool:
    """
    Filters out inactive jobs (e.g., when: manual).
    Explicitly ignores jobs with unconditional rules: when: never.
    """
    # 1. Ignore manual jobs
    if job.get("when") == "manual":
        return False

    # 2. Advanced rules handling: ignore jobs with unconditional'when: never'
    rules = job.get("rules")
    if isinstance(rules, list):
        for rule in rules:
            if isinstance(rule, dict):
                # An unconditional "when: never" rule means the job is inactive.
                # If there's an "if" condition, it's considered active for our heuristic.
                if rule.get("when") == "never" and "if" not in rule:
                    return False

    return True


def check_ci_pipeline(ci_content: str, project_type: str = "Unknown") -> Dict[str, Any]:
    """
    Refined DX CI Pipeline Analyzer.
    Validates stages, jobs, tool usage, and provides insights with severity classification.
    """
    parsed_yaml = _parse_yaml(ci_content)
    if not ci_content.strip():
        return {
            "error": "Empty .gitlab-ci.yml content",
            "stages_present": [],
            "missing_stages": EXPECTED_STAGES,
            "jobs": {},
            "issues": [
                {
                    "message": "Empty .gitlab-ci.yml content",
                    "severity": "error",
                }
            ],
            "dx_score": 0,
        }

    issues: List[Dict[str, str]] = []
    if not parsed_yaml:
        issues.append({"message": "Invalid or non-dictionary YAML content", "severity": "error"})
        parsed_yaml = {}

    # 1. Explicit vs Implicit Stages Detection
    has_explicit_stages = "stages" in parsed_yaml and isinstance(parsed_yaml["stages"], list)
    if not has_explicit_stages:
        issues.append({"message": "No explicit 'stages:' defined in CI", "severity": "warning"})

    # 1b. Check for includes (which might define stages/jobs elsewhere)
    has_includes = "include" in parsed_yaml
    if has_includes:
        issues.append(
            {
                "message": "CI uses 'include:', which may define stages or jobs not visible to this analyzer.",
                "severity": "info",
            }
        )

    # 2. Extract defined stages
    defined_stages = set()
    if has_explicit_stages:
        defined_stages.update([str(s) for s in parsed_yaml["stages"]])

    # 3. Extract and filter active jobs
    active_jobs = {}
    for key, value in parsed_yaml.items():
        # Valid jobs must be dicts, contain a 'script' key, and NOT start with '.'
        if isinstance(value, dict) and "script" in value:
            # Skip hidden jobs (GitLab hidden jobs start with .)
            if key.startswith("."):
                continue

            if is_active_job(value):
                # Normalize script to list of strings
                script = value["script"]
                if isinstance(script, str):
                    script = [script]
                elif not isinstance(script, list):
                    script = [str(script)]

                job_stage = str(value.get("stage", "test"))
                active_jobs[key] = {"stage": job_stage, "script": script}
                defined_stages.add(job_stage)

    # 4. Results initialization
    stages_present_all = [s for s in EXPECTED_STAGES if s in defined_stages]
    missing_stages = [s for s in EXPECTED_STAGES if s not in defined_stages]

    result: Dict[str, Any] = {
        "stages_present": stages_present_all,
        "missing_stages": missing_stages,
        "jobs": {},
        "issues": issues,
    }

    # 5. Core Stage Validation
    for req_stage in EXPECTED_STAGES:
        stage_present = req_stage in defined_stages

        # Find all jobs for this stage
        jobs_for_stage = [name for name, details in active_jobs.items() if details["stage"] == req_stage]
        job_present = len(jobs_for_stage) > 0

        detected_tools: List[str] = []
        indirect_execution = False
        if job_present:
            # Aggregate all script text for this stage
            all_script_text = "\n".join(["\n".join(active_jobs[j]["script"]) for j in jobs_for_stage])
            detected_tools = contains_tool(all_script_text, STAGE_TOOLS[req_stage])

            # Detect indirect script execution
            indirect_match = re.search(r"\b(bash|sh|make)\b", all_script_text, re.IGNORECASE)
            if indirect_match:
                indirect_execution = True

        result["jobs"][req_stage] = {
            "stage_present": stage_present,
            "job_present": job_present,
            "tool_detected": len(detected_tools) > 0,
            "job_names": jobs_for_stage,
            "detected_tools": detected_tools,
            "indirect_execution": indirect_execution,
        }

        # Issue generation logic
        if not stage_present:
            result["issues"].append({"message": f"Missing stage: {req_stage}", "severity": "error"})
        elif not job_present:
            result["issues"].append({"message": f"No active job defined for stage '{req_stage}'", "severity": "error"})
        elif not detected_tools:
            tools_str = "/".join(STAGE_TOOLS[req_stage])
            result["issues"].append(
                {
                    "message": f"Stage '{req_stage}' missing expected tools ({tools_str})",
                    "severity": "warning",
                }
            )

        if indirect_execution:
            result["issues"].append(
                {
                    "message": f"Tool detection for '{req_stage}' may be incomplete due to indirect script execution (bash/sh/make)",
                    "severity": "warning",
                }
            )

    # 6. Coverage Fallback Logic
    cov_result = result["jobs"]["coverage"]
    if not cov_result["stage_present"] or not cov_result["job_present"]:
        # Check 'test' stage for coverage tools
        test_jobs_names = result["jobs"]["test"]["job_names"]
        if test_jobs_names:
            test_script_text = "\n".join(["\n".join(active_jobs[j]["script"]) for j in test_jobs_names])
            # Detect coverage tools specifically
            test_detected_cov = contains_tool(test_script_text, STAGE_TOOLS["coverage"])
            if test_detected_cov:
                result["jobs"]["coverage"].update(
                    {
                        "tool_detected": True,
                        "note": "Coverage detected in test stage",
                        "detected_tools": test_detected_cov,
                    }
                )
                # Remove the error issue for missing coverage stage if tool is found in test
                result["issues"] = [
                    i
                    for i in result["issues"]
                    if not (
                        i["message"] == "Missing stage: coverage"
                        or i["message"] == "No active job defined for stage 'coverage'"
                    )
                ]

    # 7. Weighted DX Score Calculation (Bonus)
    # Weighted by importance per stage
    total_possible_score = sum(STAGE_WEIGHTS.values())
    raw_score = 0.0
    for req_stage, weight in STAGE_WEIGHTS.items():
        details = result["jobs"][req_stage]
        if details["stage_present"] and details["job_present"]:
            raw_score += weight * 0.5  # 50% for having the stage/job
            if details["tool_detected"]:
                raw_score += weight * 0.5  # 50% for detecting the actual tool

    # Normalize to 10
    result["dx_score"] = round((raw_score / total_possible_score) * 10, 1)

    # 8. Structured Recommendations (Bonus)
    recommendations = []
    is_python = "Python" in project_type
    is_js_ts = any(x in project_type for x in ["JavaScript", "TypeScript", "JS/TS"])

    if not result["jobs"]["lint"]["tool_detected"]:
        if is_python:
            recommendations.append(
                {"message": "Add Ruff for linting", "command": "uv add --dev ruff && ruff check .", "severity": "high"}
            )
        elif is_js_ts:
            recommendations.append(
                {
                    "message": "Add ESLint or Biome for linting",
                    "command": "npm install --save-dev eslint OR npm install --save-dev @biomejs/biome",
                    "severity": "high",
                }
            )

    if not result["jobs"]["format"]["tool_detected"]:
        if is_python:
            recommendations.append(
                {"message": "Add Ruff for formatting", "command": "ruff format .", "severity": "medium"}
            )
        elif is_js_ts:
            recommendations.append(
                {
                    "message": "Add Prettier for formatting",
                    "command": "npm install --save-dev prettier",
                    "severity": "medium",
                }
            )

    if not result["jobs"]["coverage"]["tool_detected"]:
        if is_python:
            recommendations.append(
                {
                    "message": "Add coverage reporting",
                    "command": "uv add --dev pytest-cov && pytest --cov=.",
                    "severity": "high",
                }
            )
        elif is_js_ts:
            recommendations.append(
                {
                    "message": "Add coverage reporting (Jest/Vitest)",
                    "command": "npm test -- --coverage",
                    "severity": "high",
                }
            )

    if not result["jobs"]["type_check"]["tool_detected"]:
        if is_python:
            recommendations.append(
                {
                    "message": "Add Mypy for type checking",
                    "command": "uv add --dev mypy && mypy .",
                    "severity": "medium",
                }
            )
        elif is_js_ts:
            recommendations.append(
                {
                    "message": "Add TypeScript for type checking",
                    "command": "npm install --save-dev typescript && npx tsc",
                    "severity": "medium",
                }
            )

    result["recommendations"] = recommendations

    return result
