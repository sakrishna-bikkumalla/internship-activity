def check_license(gl, project_id: int) -> dict:
    """
    Checks LICENSE file existence.
    """

    try:
        project = gl.projects.get(project_id)
        files = project.repository_tree(path="", recursive=True)

        license_files = [f for f in files if f["name"].lower() == "license"]

        if not license_files:
            return {"exists": False, "status": "LICENSE missing"}

        return {"exists": True, "status": "LICENSE present"}

    except Exception as e:
        return {"exists": False, "status": f"Error: {e}"}
