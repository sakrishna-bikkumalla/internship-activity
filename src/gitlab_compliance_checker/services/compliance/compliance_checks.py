from .compliance_service import run_project_compliance_checks


def get_project_compliance_report(gl, project_id: int) -> dict:
    """
    Returns full compliance report for a project.
    """
    return run_project_compliance_checks(gl, project_id)
