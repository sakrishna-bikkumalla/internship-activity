from typing import Any, Dict


def check_metadata(gl, project_id: int) -> Dict[str, Any]:
    """
    Checks for project description and tags in GitLab.
    """
    try:
        project = gl.projects.get(project_id)

        results = {
            "description_present": bool(project.description and project.description.strip()),
            "tags_present": len(project.tag_list) > 0,
            "topics": project.topics if hasattr(project, "topics") else [],
        }

        return results
    except Exception as e:
        return {"error": str(e)}
