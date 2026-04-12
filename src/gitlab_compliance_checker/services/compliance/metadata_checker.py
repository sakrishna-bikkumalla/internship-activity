from typing import Any, Dict


def check_metadata(gl, project_id: int) -> Dict[str, Any]:
    """
    Checks for project description and tags in GitLab.
    """
    try:
        project = gl._get(f"/projects/{project_id}")

        results = {
            "description_present": bool(project.get("description") and str(project.get("description")).strip()),
            "tags_present": len(project.get("tag_list", [])) > 0,
            "topics": project.get("topics", []),
        }

        return results
    except Exception as e:
        return {"error": str(e)}
