import base64


def check_tools(gl, project_id: int) -> dict:
    """
    Checks for the presence of various tools in .pre-commit-config.yaml and .gitlab-ci.yml
    Returns a dictionary of tools categorized.
    """
    try:
        project = gl.projects.get(project_id)
        
        def get_file_content(filepath: str) -> str:
            try:
                branch = getattr(project, "default_branch", "main")
                f = project.files.get(file_path=filepath, ref=branch)
                return base64.b64decode(f.content).decode("utf-8").lower()
            except Exception:
                return ""

        pre_commit_content = get_file_content(".pre-commit-config.yaml")
        gitlab_ci_content = get_file_content(".gitlab-ci.yml")
        
        # Check for .husky directory
        has_husky_dir = False
        try:
            branch = getattr(project, "default_branch", "main")
            project.repository_tree(path=".husky", ref=branch)
            has_husky_dir = True
        except Exception:
            pass

        combined_content = pre_commit_content + "\n" + gitlab_ci_content
        
        tools = {
            "dead_code_checking": {
                "vulture": "vulture" in combined_content,
                "knip": "knip" in combined_content,
                "ts-prune": "ts-prune" in combined_content,
            },
            "security_audits": {
                "bandit": "bandit" in combined_content,
                "safety": "safety" in combined_content,
                "npm audit": "npm audit" in combined_content,
                "yarn audit": "yarn audit" in combined_content,
                "snyk": "snyk" in combined_content,
                "gitleaks": "gitleaks" in combined_content,
            },
            "type_checking": {
                "mypy": "mypy" in combined_content,
                "pyright": "pyright" in combined_content,
                "tsc": "tsc" in combined_content,
                "typescript": "typescript" in combined_content,
            },
            "pre_commit_hooks": {
                "pre-commit": "pre-commit" in combined_content or bool(pre_commit_content),
                "husky": "husky" in combined_content or has_husky_dir,
                "lint-staged": "lint-staged" in combined_content,
            },
            "linting_and_formatting": {
                "ruff": "ruff" in combined_content,
                "flake8": "flake8" in combined_content,
                "black": "black" in combined_content,
                "isort": "isort" in combined_content,
                "pylint": "pylint" in combined_content,
                "eslint": "eslint" in combined_content,
                "prettier": "prettier" in combined_content,
            },
            "i18n": {
                "i18n": "i18n" in combined_content,
                "babel": "babel" in combined_content,
                "gettext": "gettext" in combined_content,
                "i18next": "i18next" in combined_content,
                "vue-i18n": "vue-i18n" in combined_content,
                "react-intl": "react-intl" in combined_content,
            },
            "tests": {
                "pytest": "pytest" in combined_content,
                "unittest": "unittest" in combined_content,
                "jest": "jest" in combined_content,
                "mocha": "mocha" in combined_content,
                "vitest": "vitest" in combined_content,
            },
            "test_coverage_checking": {
                "coverage": "coverage" in combined_content,
                "pytest-cov": "pytest-cov" in combined_content,
                "istanbul": "istanbul" in combined_content,
                "nyc": "nyc" in combined_content,
                "c8": "c8" in combined_content,
            },
            "gitlab_ci": {
                "gitlab-ci": bool(gitlab_ci_content),
            }
        }
        
        return tools
    except Exception as e:
        return {"error": str(e)}
