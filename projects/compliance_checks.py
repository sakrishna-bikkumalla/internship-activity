from gitlab_utils.files_reader import read_file_content


def _first_matching_path(file_paths, candidates):
    lowered = {p.lower(): p for p in file_paths}
    for candidate in candidates:
        if candidate.lower() in lowered:
            return lowered[candidate.lower()]
    return None


def _safe_repository_tree(project, branch):
    try:
        return project.repository_tree(path="", ref=branch, recursive=True, get_all=True)
    except TypeError:
        return project.repository_tree(path="", ref=branch, recursive=True, all=True)


def check_project_compliance(project, branch=None):
    branch = branch or getattr(project, "default_branch", None) or "main"

    tree = _safe_repository_tree(project, branch)
    file_paths = [item.get("path") for item in tree if item.get("type") == "blob" and item.get("path")]
    lowered_paths = {p.lower() for p in file_paths}

    required_files = ["README.md", "LICENSE", ".gitignore"]
    required_status = []
    for required in required_files:
        exists = required.lower() in lowered_paths
        required_status.append(
            {
                "item": required,
                "status": "PASS" if exists else "FAIL",
                "details": "Found" if exists else "Missing",
            }
        )

    readme_path = _first_matching_path(file_paths, ["README.md", "readme.md"])
    readme_content = (
        read_file_content(project, readme_path, branch)
        if readme_path
        else None
    )

    ci_path = _first_matching_path(file_paths, [".gitlab-ci.yml"])
    has_tests = any(path.lower().startswith(("tests/", "test/")) for path in file_paths)
    has_docs = any(path.lower().startswith("docs/") for path in file_paths)

    quality_checks = [
        {
            "item": "README has useful content",
            "status": "PASS" if readme_content and len(readme_content.strip()) >= 40 else "FAIL",
            "details": "README content looks good" if readme_content and len(readme_content.strip()) >= 40 else "README missing/too short",
        },
        {
            "item": "CI configuration",
            "status": "PASS" if ci_path else "FAIL",
            "details": ci_path or ".gitlab-ci.yml not found",
        },
        {
            "item": "Tests directory",
            "status": "PASS" if has_tests else "FAIL",
            "details": "tests/ found" if has_tests else "No tests folder detected",
        },
        {
            "item": "Docs directory",
            "status": "PASS" if has_docs else "FAIL",
            "details": "docs/ found" if has_docs else "No docs folder detected",
        },
    ]

    all_checks = required_status + quality_checks
    passed = sum(1 for row in all_checks if row["status"] == "PASS")

    report = {
        "project_id": getattr(project, "id", None),
        "project_name": getattr(project, "name", ""),
        "project_path": getattr(project, "path_with_namespace", ""),
        "branch": branch,
        "file_paths": file_paths,
        "checks": all_checks,
        "passed": passed,
        "total": len(all_checks),
        "score_pct": round((passed / len(all_checks)) * 100, 2) if all_checks else 0.0,
    }
    return report
