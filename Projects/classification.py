from .file_classifier import classify_files


def get_project_file_classification(gl, project_id: int) -> dict:
    """
    Returns classified file statistics for a project.
    """
    return classify_files(gl, project_id)
