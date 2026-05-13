import logging
import os

logger = logging.getLogger(__name__)


def extract_path_from_url(input_str):
    from urllib.parse import urlparse

    try:
        path = urlparse(input_str).path.strip("/")
        return path[:-4] if path.endswith(".git") else path
    except Exception:
        return str(input_str).strip()


def get_project_branches(gl_client, project_id):
    """Get all branches for a given project.

    Args:
        gl_client: GitLab client wrapper instance
        project_id: The ID or path of the GitLab project

    Returns:
        A list of branch names as strings.
    """
    try:
        final_pid = str(project_id).replace("/", "%2F")
        branches = gl_client._get_paginated(f"/projects/{final_pid}/repository/branches", all=True)
        return sorted([b.get("name") for b in branches if b.get("name")])
    except Exception:
        return []


def list_all_files(gl_client, project_id, branch="main"):
    """Fetch a recursive file tree and return a list of all file paths.

    Args:
        gl_client: GitLab client wrapper instance
        project_id: The ID or path of the GitLab project
        branch: The branch to scan (defaults to main)

    Returns:
        A list of file paths (blobs only).
    """
    try:
        final_pid = str(project_id).replace("/", "%2F")
        items = gl_client._get_paginated(
            f"/projects/{final_pid}/repository/tree", params={"ref": branch, "recursive": True}, all=True
        )
        return [item.get("path") for item in items if item.get("type") == "blob" and item.get("path")]
    except Exception as e:
        logger.error(f"Error listing files for {project_id}: {e}")
        return []


def classify_repository_files(file_paths):
    """Classify files into categories and detect language files.

    Args:
        file_paths: List of file paths

    Returns:
        Dict with classification results
    """
    res = {
        "common_requirements": [],
        "project_files": [],
        "tech_files": [],
        "python_files": [],
        "js_files": [],
        "java_files": [],
        "c#_files": [],
    }
    for p in file_paths or []:
        lp = p.lower()
        filename = os.path.basename(lp)

        # Common requirement files
        if filename in {
            "requirements.txt",
            "requirements-dev.txt",
            "pipfile",
            "pipfile.lock",
            "pyproject.toml",
            "package.json",
            "package-lock.json",
            "poetry.lock",
            "setup.py",
            "setup.cfg",
        }:
            res["common_requirements"].append(p)

        # Project files
        if (
            filename
            in {
                "readme.md",
                "contributing.md",
                "changelog",
                "changelog.md",
                "license",
                "license.md",
            }
            or lp.startswith("docs/")
            or lp.startswith("src/")
            or lp.startswith("tests/")
        ):
            res["project_files"].append(p)

        # Tech / tooling files
        if (
            filename
            in {
                "dockerfile",
                "docker-compose.yml",
                ".gitlab-ci.yml",
                "makefile",
                "tox.ini",
                ".pre-commit-config.yaml",
                ".editorconfig",
                ".eslintrc",
                ".eslintrc.json",
            }
            or lp.startswith(".vscode/")
            or lp.startswith(".github/")
        ):
            res["tech_files"].append(p)

        # Language-specific
        if lp.endswith(".py"):
            res["python_files"].append(p)
        if lp.endswith((".js", ".jsx", ".ts", ".tsx")):
            res["js_files"].append(p)

    # Deduplicate lists
    for k in res:
        res[k] = sorted(dict.fromkeys(res[k]))
    return res


def check_vscode_settings(gl_client, project_id, branch="main"):
    """Check if the project has a .vscode/settings.json file.

    Args:
        gl_client: GitLab client wrapper instance
        project_id: The ID or path of the GitLab project
        branch: Branch name

    Returns:
        True if the settings.json file exists, False otherwise
    """
    try:
        final_pid = str(project_id).replace("/", "%2F")
        items = gl_client._get(f"/projects/{final_pid}/repository/tree", params={"path": ".vscode", "ref": branch})
        return (
            any(item.get("name", "").lower() == "settings.json" for item in items) if isinstance(items, list) else False
        )
    except Exception:
        return False


def check_vscode_file_exists(gl_client, project_id, filename, branch="main"):
    try:
        final_pid = str(project_id).replace("/", "%2F")
        items = gl_client._get(f"/projects/{final_pid}/repository/tree", params={"path": ".vscode", "ref": branch})
        return (
            any(item.get("name", "").lower() == filename.lower() for item in items)
            if isinstance(items, list)
            else False
        )
    except Exception:
        return False


def check_extensions_json_for_ruff(gl_client, project_id, branch="main", read_file_fn=None):
    """Check if Ruff is recommended in .vscode/extensions.json.

    Args:
        gl_client: GitLab client wrapper instance
        project_id: The ID or path of the project
        branch: Branch name
        read_file_fn: Dependency injection for file reading

    Returns:
        True if charliermarsh.ruff is in recommendations.
    """
    if read_file_fn is None:
        from internship_activity_tracker.infrastructure.gitlab.files_reader import read_file_content

        read_file_fn = read_file_content
    content = read_file_fn(gl_client, project_id, ".vscode/extensions.json", branch)
    if not content:
        return False
    try:
        import json

        recs = json.loads(content).get("recommendations", [])
        return "charliermarsh.ruff" in recs or any("ruff" in str(r).lower() for r in recs)
    except Exception:
        return False


def list_markdown_files_in_folder(gl_client, project_id, folder_path, branch="main"):
    try:
        final_pid = str(project_id).replace("/", "%2F")
        items = gl_client._get(f"/projects/{final_pid}/repository/tree", params={"path": folder_path, "ref": branch})
        return (
            [item.get("name") for item in items if str(item.get("name", "")).lower().endswith(".md")]
            if isinstance(items, list)
            else []
        )
    except Exception:
        return []


def check_templates_presence(gl_client, project_id, branch="main"):
    result = {
        "issue_templates_folder": False,
        "issue_template_files": [],
        "merge_request_templates_folder": False,
        "merge_request_template_files": [],
    }
    final_pid = str(project_id).replace("/", "%2F")
    for key, path in [("issue", ".gitlab/issue_templates"), ("merge_request", ".gitlab/merge_request_templates")]:
        try:
            items = gl_client._get(f"/projects/{final_pid}/repository/tree", params={"path": path, "ref": branch})
            if isinstance(items, list):
                md_files = [item.get("name") for item in items if str(item.get("name", "")).lower().endswith(".md")]
                if md_files:
                    result[f"{key}_templates_folder"] = True
                    result[f"{key}_template_files"] = md_files
        except Exception:
            pass
    return result


def check_license_content(gl_client, project_id, branch="main", read_file_fn=None):
    """Retrieve the license and categorize it based on strict rules.

    Args:
        gl_client: GitLab client wrapper instance
        project_id: Project identifier
        branch: Branch to check
        read_file_fn: Injected strategy to read files

    Returns:
        A string indicating 'valid', 'gnu_other', 'invalid', or 'not_found'
    """
    if read_file_fn is None:
        from internship_activity_tracker.infrastructure.gitlab.files_reader import read_file_content

        read_file_fn = read_file_content
    content = read_file_fn(gl_client, project_id, "LICENSE", branch) or read_file_fn(
        gl_client, project_id, "LICENSE.md", branch
    )
    if not content:
        return "not_found"
    cleaned = " ".join(content.strip().split()).lower()
    if (
        "affero" in cleaned
        and "general public license" in cleaned
        and ("version 3" in cleaned or "v3" in cleaned)
        and "19 november 2007" in cleaned
    ):
        return "valid"
    if (
        "general public license" in cleaned
        and ("version 3" in cleaned or "v3" in cleaned)
        and "29 june 2007" in cleaned
    ):
        return "gnu_other"
    if "mit license" in cleaned or "apache license" in cleaned:
        return "invalid"
    return "gnu_other" if "gnu" in cleaned or "gpl" in cleaned else "invalid"


def check_project_compliance(gl_client, project_id, branch=None, read_file_fn=None):
    """Check project compliance with standard repository structures.

    Args:
        gl_client: GitLab client wrapper instance
        project_id: The project ID or dictionary of project info
        branch: Branch name to check (defaults to main)
        read_file_fn: Optional file reading function

    Returns:
        Dict with compliance report results.
    """
    if read_file_fn is None:
        from internship_activity_tracker.infrastructure.gitlab.files_reader import read_file_content

        read_file_fn = read_file_content
    p_desc, p_tags = "", []
    if isinstance(project_id, dict):
        pid, branch, p_desc, p_tags = (
            project_id.get("id"),
            branch or project_id.get("default_branch", "main"),
            project_id.get("description", ""),
            project_id.get("tag_list", []),
        )
    else:
        pid = project_id
        try:
            p_info = gl_client._get(f"/projects/{str(pid).replace('/', '%2F')}")
            branch, p_desc, p_tags = (
                branch or p_info.get("default_branch", "main"),
                p_info.get("description", ""),
                p_info.get("tag_list", []),
            )
        except Exception:
            branch = branch or "main"
    report = {}
    try:
        f_pid = str(pid).replace("/", "%2F")
        tree = gl_client._get(f"/projects/{f_pid}/repository/tree", params={"ref": branch})
        filenames = [item.get("name", "").lower() for item in (tree or [])]
        report.update(
            {
                "README.md": any(n.startswith("readme") for n in filenames),
                "CONTRIBUTING.md": "contributing.md" in filenames,
                "CHANGELOG": any(n.startswith("changelog") for n in filenames),
                "LICENSE": any(n.startswith("license") for n in filenames),
            }
        )
        if report["README.md"]:
            content = read_file_fn(gl_client, pid, "README.md", branch) or read_file_fn(
                gl_client, pid, "README", branch
            )
            if not content or not content.strip():
                report.update({"readme_status": "empty", "readme_sections": [], "readme_needs_improvement": True})
            else:
                lc = content.lower()
                found = [s for s in ["installation", "usage", "setup", "license", "contributing", "example"] if s in lc]
                report.update(
                    {
                        "readme_status": "present",
                        "readme_sections": found,
                        "readme_needs_improvement": len(found) < 3 or len(content.strip()) < 150,
                    }
                )
        else:
            report.update({"readme_status": "missing", "readme_sections": [], "readme_needs_improvement": True})
        l_status = check_license_content(gl_client, pid, branch, read_file_fn) if report["LICENSE"] else "not_found"
        report.update(
            {
                "license_valid": l_status == "valid",
                "license_status": l_status,
                ".gitignore": ".gitignore" in filenames,
                "pyproject.toml": "pyproject.toml" in filenames,
                "uv_lock_exists": "uv.lock" in filenames,
            }
        )
        report["vscode_settings"] = check_vscode_settings(gl_client, pid, branch)
        report["vscode_config_exists"] = report["vscode_settings"]
        report["vscode_ruff_in_extensions"] = check_extensions_json_for_ruff(gl_client, pid, branch, read_file_fn)
        report.update(check_templates_presence(gl_client, pid, branch))
        report.update({"description_present": bool(p_desc and str(p_desc).strip()), "tags_present": len(p_tags) > 0})
    except Exception as e:
        report["error"] = f"Error during compliance check: {e}"
    return report
