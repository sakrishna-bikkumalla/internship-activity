from .file_classifier import classify_files
from .license_checker import check_license
from .readme_checker import check_readme
from .templates_checker import check_templates


def run_project_compliance_checks(gl, project_id: int) -> dict:
    """
    Runs all compliance checks for a project.
    """

    results = {
        "readme": check_readme(gl, project_id),
        "license": check_license(gl, project_id),
        "templates": check_templates(gl, project_id),
        "file_types": classify_files(gl, project_id),
    }

    return results
