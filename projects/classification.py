import os

def classify_repository_files(file_paths):
    res = {
        "common_requirements": [],
        "project_files": [],
        "tech_files": [],
        "python_files": [],
        "js_files": [],
    }

    if not file_paths:
        return res

    common_required = {
        "readme.md",
        "license",
        ".gitignore",
    }

    project_files = {
        "pyproject.toml",
        "requirements.txt",
        "package.json",
        "dockerfile",
        "docker-compose.yml",
        "docker-compose.yaml",
    }

    tech_files = {
        ".pre-commit-config.yaml",
        ".pre-commit-config.yml",
        ".flake8",
        "setup.py",
        "setup.cfg",
        "tox.ini",
        ".editorconfig",
    }

    for raw_path in file_paths:
        path = (raw_path or "").strip()
        if not path:
            continue

        base_name = os.path.basename(path).lower()

        if base_name in common_required:
            res["common_requirements"].append(path)
        if base_name in project_files:
            res["project_files"].append(path)
        if base_name in tech_files:
            res["tech_files"].append(path)

        if path.lower().endswith(".py"):
            res["python_files"].append(path)
        if path.lower().endswith((".js", ".jsx", ".ts", ".tsx")):
            res["js_files"].append(path)

    return res
