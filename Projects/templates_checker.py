def check_templates(gl, project_id: int) -> dict:
    """
    Checks templates folder existence.
    """

    try:
        project = gl.projects.get(project_id)
        files = project.repository_tree(path="", recursive=True)

        templates = [f for f in files if "template" in f["path"].lower()]

        if not templates:
            return {"exists": False, "status": "Templates missing"}

        return {"exists": True, "status": "Templates present"}

    except Exception as e:
        return {"exists": False, "status": f"Error: {e}"}
