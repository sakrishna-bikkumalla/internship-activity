import base64
from typing import Any, Dict, Optional

from gitlab_compliance_checker.infrastructure.gitlab.parsers import parse_json, parse_yaml

from .project_detector import detect_project_type


def check_tools(gl, project_id: int, ref: Optional[str] = None) -> Dict[str, Any]:
    """
    Ultimate DX-checker: Deep analysis of CLI tools and CI/CD pipelines.
    Checks for: ruff, uv audit, vulture, knip, mypy, git-cliff, secret scanning, etc.
    """
    try:
        project = gl.projects.get(project_id)
        branch = ref or getattr(project, "default_branch", "main")

        # Fetch root files for language detection
        try:
            items = project.repository_tree(path="", ref=branch, all=True)
            filenames = [item["name"] for item in items if item["type"] == "blob"]
        except Exception:
            filenames = []

        project_type = detect_project_type(filenames)

        def get_file_content(filepath: str) -> str:
            try:
                f = project.files.get(file_path=filepath, ref=branch)
                return base64.b64decode(f.content).decode("utf-8")
            except Exception:
                return ""

        # Load key configuration files
        # Load key configuration files
        configs: Dict[str, Any] = {
            "gitlab_ci": parse_yaml(get_file_content(".gitlab-ci.yml")),
            "pre_commit": parse_yaml(get_file_content(".pre-commit-config.yaml")),
            "pyproject": get_file_content("pyproject.toml"),
            "package_json": parse_json(get_file_content("package.json")),
            "husky_pre_commit": get_file_content(".husky/pre-commit"),
            "cliff_toml": get_file_content("cliff.toml"),
        }

        # Initialize results
        quality_tools: Dict[str, Any] = {}
        security: Dict[str, Any] = {}
        testing: Dict[str, Any] = {}
        automation: Dict[str, Any] = {}
        i18n: Dict[str, Any] = {}

        pyproject_content = str(configs.get("pyproject", ""))
        pre_commit_content = str(configs.get("pre_commit", ""))
        gitlab_ci_content = str(configs.get("gitlab_ci", ""))

        # --- 1. Quality & Linting Tools ---
        if "Python" in project_type:
            quality_tools["ruff"] = "[tool.ruff]" in pyproject_content or "ruff" in pre_commit_content
            quality_tools["mypy"] = "[tool.mypy]" in pyproject_content or "mypy" in pre_commit_content
            quality_tools["vulture"] = "[tool.vulture]" in pyproject_content or "vulture" in pre_commit_content
            quality_tools["pip_audit"] = "pip-audit" in gitlab_ci_content or "pip-audit" in pre_commit_content

        if "JavaScript" in project_type or "TypeScript" in project_type:
            pkg = configs.get("package_json")
            if isinstance(pkg, dict):
                deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                quality_tools["eslint"] = "eslint" in deps
                quality_tools["prettier"] = "prettier" in deps
                quality_tools["biome"] = "biome" in deps or "biome.json" in filenames
                quality_tools["knip"] = "knip" in deps
                quality_tools["husky"] = "husky" in deps or ".husky" in filenames

        # --- 2. Security & Secret Scanning ---
        ci_str = gitlab_ci_content.lower()
        pc_str = pre_commit_content.lower()

        security["secret_scanning"] = any(
            x in ci_str or x in pc_str for x in ["gitleaks", "trufflehog", "secret_detection"]
        )
        security["dependency_audit"] = any(
            x in ci_str or x in pc_str
            for x in ["uv audit", "uv-audit", "pip-audit", "npm audit", "yarn audit", "auditjs"]
        )
        if "Python" in project_type:
            security["bandit"] = "bandit" in pc_str or "bandit" in ci_str

        # --- 3. Testing & Coverage ---
        if "Python" in project_type:
            testing["pytest"] = "pytest" in pyproject_content or "pytest" in ci_str
            testing["coverage"] = "pytest-cov" in pyproject_content or "coverage" in ci_str
            # Check for coverage threshold
            testing["coverage_threshold"] = "fail-under" in pyproject_content or "fail_under" in pyproject_content

        if "JavaScript" in project_type or "TypeScript" in project_type:
            pkg = configs.get("package_json")
            if isinstance(pkg, dict):
                scripts = pkg.get("scripts", {})
                testing["jest_vitest"] = any(x in str(pkg) for x in ["jest", "vitest"])
                testing["coverage"] = any("coverage" in s for s in scripts.values())

        # --- 4. Automation & Changelog ---
        automation["git_cliff"] = configs["cliff_toml"] != "" or "git-cliff" in ci_str
        automation["pre_commit"] = configs["pre_commit"] is not None
        automation["gitlab_ci"] = configs["gitlab_ci"] is not None

        # --- 5. Internationalization (i18n) ---
        i18n["supported"] = any(
            x in (ci_str + pc_str + str(configs["pyproject"]) + str(configs["package_json"]))
            for x in ["babel", "gettext", "i18next", "react-intl"]
        )

        # --- Calculate DX Score (Simple Weighted) ---
        checks = [
            quality_tools.get("ruff") or quality_tools.get("biome") or quality_tools.get("eslint"),
            quality_tools.get("mypy") or quality_tools.get("knip"),
            security.get("secret_scanning"),
            security.get("dependency_audit"),
            testing.get("coverage"),
            automation.get("git_cliff"),
            automation.get("pre_commit"),
            automation.get("gitlab_ci"),
        ]
        dx_score = int((sum(1 for c in checks if c) / len(checks)) * 100) if checks else 0

        return {
            "project_type": project_type,
            "quality_tools": quality_tools,
            "security": security,
            "testing": testing,
            "automation": automation,
            "i18n": i18n,
            "dx_score": dx_score,
        }

    except Exception as e:
        return {"error": str(e)}
