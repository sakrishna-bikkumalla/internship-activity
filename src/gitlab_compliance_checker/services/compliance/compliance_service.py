import base64
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from gitlab_compliance_checker.infrastructure.gitlab.pipeline_checker import check_ci_pipeline

from .file_classifier import classify_files
from .license_checker import check_license
from .metadata_checker import check_metadata
from .readme_checker import check_readme
from .templates_checker import check_templates
from .tools_checker import check_tools


def run_project_compliance_checks(gl, project_id: int, ref: Optional[str] = None) -> Dict[str, Any]:
    """
    Ultimate entry point: Runs all production-grade compliance checks for a project.
    """
    try:
        project_info = gl._get(f"/projects/{project_id}")
        branch = ref or project_info.get("default_branch", "main")
    except Exception:
        branch = "main"

    results: Dict[str, Any] = {
        "readme": check_readme(gl, project_id, ref=branch),
        "license": check_license(gl, project_id, ref=branch),
        "templates": check_templates(gl, project_id, ref=branch),
        "metadata": check_metadata(gl, project_id),
        "file_types": classify_files(gl, project_id, ref=branch),
        "tools": check_tools(gl, project_id, ref=branch),
        "dx_ci": None,
    }

    # --- GitLab CI Deep Dive ---
    project_type = results["tools"].get("project_type", "Unknown")
    try:
        encoded_path = quote(".gitlab-ci.yml", safe="")
        f = gl._get(f"/projects/{project_id}/repository/files/{encoded_path}", params={"ref": branch})
        if f and isinstance(f, dict) and "content" in f:
            ci_content = base64.b64decode(f["content"]).decode("utf-8")
            results["dx_ci"] = check_ci_pipeline(ci_content, project_type=project_type)
    except Exception:
        pass

    # Calculate global DX score from tools_checker
    results["dx_score"] = results["tools"].get("dx_score", 0)

    return results


def get_dx_suggestions(report: Dict[str, Any]) -> List[Dict[str, str]]:
    """
    Generates actionable suggestions based on the compliance report.
    """
    suggestions = []
    tools = report.get("tools", {})
    quality = tools.get("quality_tools", {})
    security = tools.get("security", {})
    automation = tools.get("automation", {})
    lang = tools.get("project_type", "Unknown")

    # --- Quality Tools ---
    if "Python" in lang:
        if not quality.get("ruff"):
            suggestions.append(
                {
                    "item": "Ruff",
                    "reason": "Missing industry-standard linter/formatter.",
                    "action": "`uv add --dev ruff` and add to `.pre-commit-config.yaml`",
                }
            )
        if not quality.get("mypy"):
            suggestions.append(
                {"item": "Mypy", "reason": "Type checking is essential for Python DX.", "action": "`uv add --dev mypy`"}
            )

    if "JavaScript" in lang or "TypeScript" in lang:
        if not quality.get("biome") and not quality.get("eslint"):
            suggestions.append(
                {
                    "item": "Biome/ESLint",
                    "reason": "Missing JS/TS linting.",
                    "action": "`npm install --save-dev @biomejs/biome` or `eslint`",
                }
            )
        if not quality.get("knip"):
            suggestions.append(
                {
                    "item": "Knip",
                    "reason": "Dead code checking improves maintainability.",
                    "action": "`npm install --save-dev knip`",
                }
            )

    # --- Security ---
    if not security.get("secret_scanning"):
        suggestions.append(
            {
                "item": "Secret Scanning",
                "reason": "Exposing secrets is a critical security risk.",
                "action": "Add `gitleaks` to pre-commit or enable GitLab Secret Detection.",
            }
        )

    # --- Automation ---
    if not automation.get("git_cliff"):
        suggestions.append(
            {
                "item": "Git-Cliff",
                "reason": "Automated changelogs from conventional commits.",
                "action": "Add `cliff.toml` and integrate with CI/CD.",
            }
        )

    # --- License & Docs ---
    if not report["license"].get("valid"):
        suggestions.append(
            {
                "item": "License",
                "reason": "Project must be licensed under AGPLv3.",
                "action": "Ensure the LICENSE file contains the full AGPLv3 text.",
            }
        )

    if report["readme"].get("needs_improvement"):
        suggestions.append(
            {
                "item": "README Quality",
                "reason": "Poor documentation hinders onboarding.",
                "action": "Add Installation, Usage, and Contributing sections.",
            }
        )

    # --- CI Pipeline Suggestions ---
    dx_ci = report.get("dx_ci")
    if dx_ci and "recommendations" in dx_ci:
        for rec in dx_ci["recommendations"]:
            suggestions.append({"item": "CI Pipeline", "reason": rec["message"], "action": rec["command"]})

    return suggestions
