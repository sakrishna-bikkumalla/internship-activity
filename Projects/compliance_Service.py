from .file_classifier import classify_files
from .license_checker import check_license
from .readme_checker import check_readme
from .templates_checker import check_templates
from .vscode_checker import check_vscode


def get_project_compliance(gl, project_id: int) -> dict:
    """
    Runs all compliance checks for a project.
    """

    results = {
        "readme": check_readme(gl, project_id),
        "license": check_license(gl, project_id),
        "vscode": check_vscode(gl, project_id),
        "templates": check_templates(gl, project_id),
        "file_types": classify_files(gl, project_id),
    }

    return results
