from typing import Any, Dict

from Projects.compliance_service import run_project_compliance_checks


def process_single_project(gl_client, project_id: Any, include_details: bool = True) -> Dict[str, Any]:
    """Process a single project for batch compliance checking.

    Args:
        gl_client: GitLab client instance (python-gitlab client)
        project_id: Project ID or path
        include_details: Whether to fetch detailed compliance info

    Returns:
        Project compliance result dict
    """
    try:
        # Note: compliance_service expects the python-gitlab client object
        # gl_client should be either the GitLabClient wrapper or the raw gitlab.Gitlab object
        # We handle both if possible, but standard is the raw client for compliance_service
        raw_client = getattr(gl_client, "client", gl_client)

        report = run_project_compliance_checks(raw_client, project_id)

        if not include_details:
            # Return only high-level score
            return {
                "project_id": project_id,
                "dx_score": report.get("dx_score", 0),
                "project_type": report.get("tools", {}).get("project_type", "Unknown"),
            }

        return report
    except Exception as e:
        return {"project_id": project_id, "error": str(e), "dx_score": 0}
