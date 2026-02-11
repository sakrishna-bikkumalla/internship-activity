"""Issue-related metrics collection for compliance reporting.

Pure calculation logic without Streamlit or API calls.
"""


def get_open_issues_count(user_issue_count):
    """Get the count of open issues for a user.

    Args:
        user_issue_count: Result from client API call

    Returns:
        int | str: Number of open issues or error message
    """
    if isinstance(user_issue_count, int):
        return user_issue_count
    return user_issue_count if isinstance(user_issue_count, str) else "N/A"


def get_assigned_issues_count(user_info):
    """Get the count of issues assigned to a user.

    Args:
        user_info (dict): User information dict

    Returns:
        int | str: Count of assigned issues or N/A
    """
    # This would typically come from the API but is passed as parameter
    # to keep business logic separate from API calls
    return user_info.get("assigned_issues_count", 0)


def calculate_issue_metrics(open_issues, assigned_issues):
    """Calculate derived metrics from issue counts.

    Args:
        open_issues (int): Count of open issues
        assigned_issues (int): Count of assigned issues

    Returns:
        dict: Calculated metrics including percentages and summaries
    """
    metrics = {
        "open_issues": open_issues,
        "assigned_issues": assigned_issues,
        "unassigned_issues": max(0, open_issues - assigned_issues),
    }

    if open_issues > 0:
        metrics["assignment_percentage"] = round((assigned_issues / open_issues) * 100, 2)
        metrics["unassigned_percentage"] = round(
            (metrics["unassigned_issues"] / open_issues) * 100, 2
        )
    else:
        metrics["assignment_percentage"] = 0.0
        metrics["unassigned_percentage"] = 0.0

    return metrics


def summarize_issue_compliance(templates_validation, open_issues_count, assigned_issues_count):
    """Create a comprehensive issue compliance summary.

    Args:
        templates_validation (dict): Validation result from validate_issue_templates()
        open_issues_count (int): Count of open issues
        assigned_issues_count (int): Count of assigned issues

    Returns:
        dict: Complete compliance summary
    """
    metrics = calculate_issue_metrics(open_issues_count, assigned_issues_count)

    return {
        "templates_compliant": templates_validation.get("is_valid", False),
        "has_issue_templates": not templates_validation.get("missing_issues", True),
        "has_mr_templates": not templates_validation.get("missing_mrs", True),
        "has_recommended_templates": templates_validation.get("has_recommended_templates", False),
        "metrics": metrics,
        "compliance_score": calculate_compliance_score(templates_validation, metrics),
    }


def calculate_compliance_score(templates_validation, metrics):
    """Calculate an issue compliance score (0-100).

    Args:
        templates_validation (dict): Template validation result
        metrics (dict): Calculated metrics

    Returns:
        int: Compliance score 0-100
    """
    score = 0

    # Templates (50 points max)
    if templates_validation.get("is_valid", False):
        score += 50
    elif templates_validation.get("has_recommended_templates", False):
        score += 30
    elif not templates_validation.get("missing_issues", True):
        score += 25
    elif not templates_validation.get("missing_mrs", True):
        score += 20

    # Issue assignment health (50 points max)
    open_count = metrics.get("open_issues", 0)
    if open_count == 0:
        score += 50  # No issues is clean state
    else:
        assignment_pct = metrics.get("assignment_percentage", 0)
        if assignment_pct >= 90:
            score += 50
        elif assignment_pct >= 70:
            score += 35
        elif assignment_pct >= 50:
            score += 20
        elif assignment_pct > 0:
            score += 10

    return min(score, 100)
