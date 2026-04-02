"""Pure business logic for issue-related operations.

This module contains no Streamlit code and no global API calls.
All API operations are passed as parameters.
"""


def check_templates_presence(project, branch="main"):
    """Check for issue and merge request templates in the repository.

    Args:
        project: GitLab project object
        branch: Repository branch to check (default: "main")

    Returns:
        dict: Contains:
            - issue_templates_folder (bool): Whether .gitlab/issue_templates exists
            - issue_template_files (list): Names of .md files in issue templates
            - merge_request_templates_folder (bool): Whether .gitlab/merge_request_templates exists
            - merge_request_template_files (list): Names of .md files in MR templates
    """
    result = {
        "issue_templates_folder": False,
        "issue_template_files": [],
        "merge_request_templates_folder": False,
        "merge_request_template_files": [],
    }

    # Check issue templates
    try:
        items = project.repository_tree(path=".gitlab/issue_templates", ref=branch)
        md_files = [item["name"] for item in items if item["name"].lower().endswith(".md")]
        if md_files:
            result["issue_templates_folder"] = True
            result["issue_template_files"] = md_files
    except Exception:
        pass

    # Check merge request templates
    try:
        items = project.repository_tree(path=".gitlab/merge_request_templates", ref=branch)
        md_files = [item["name"] for item in items if item["name"].lower().endswith(".md")]
        if md_files:
            result["merge_request_templates_folder"] = True
            result["merge_request_template_files"] = md_files
    except Exception:
        pass

    return result


def validate_issue_templates(templates_result):
    """Validate issue templates based on check results.

    Args:
        templates_result (dict): Result from check_templates_presence()

    Returns:
        dict: Validation result with:
            - is_valid (bool): Whether templates are properly configured
            - missing_issues (bool): Whether issue templates are missing
            - missing_mrs (bool): Whether MR templates are missing
            - has_recommended_templates (bool): Whether recommended templates exist
    """
    validation = {
        "is_valid": False,
        "missing_issues": not templates_result.get("issue_templates_folder", False),
        "missing_mrs": not templates_result.get("merge_request_templates_folder", False),
        "has_recommended_templates": False,
    }

    # Check for recommended template files
    issue_files = templates_result.get("issue_template_files", [])
    mr_files = templates_result.get("merge_request_template_files", [])

    recommended_issue_templates = {"bug.md", "feature.md", "default.md", "documentation.md"}
    recommended_mr_templates = {"bug.md", "feature.md", "default.md", "documentation.md"}

    issue_files_lower = {f.lower() for f in issue_files}
    mr_files_lower = {f.lower() for f in mr_files}

    has_issue_recs = bool(issue_files_lower & recommended_issue_templates)
    has_mr_recs = bool(mr_files_lower & recommended_mr_templates)

    validation["has_recommended_templates"] = has_issue_recs or has_mr_recs

    # Valid if both folders exist with at least some templates
    validation["is_valid"] = (
        templates_result.get("issue_templates_folder", False)
        and templates_result.get("merge_request_templates_folder", False)
        and bool(issue_files)
        and bool(mr_files)
    )

    return validation


def get_issue_summary(project, branch="main"):
    """Get a complete issue-related summary for a project.

    Args:
        project: GitLab project object
        branch: Repository branch to check

    Returns:
        dict: Complete issue summary including templates and validation
    """
    templates = check_templates_presence(project, branch)
    validation = validate_issue_templates(templates)

    return {
        "templates": templates,
        "validation": validation,
        "total_issue_templates": len(templates.get("issue_template_files", [])),
        "total_mr_templates": len(templates.get("merge_request_template_files", [])),
    }
