def check_readme(gl, project_id: int) -> dict:
    """
    Checks README existence and size.
    """

    try:
        project = gl.projects.get(project_id)
        files = project.repository_tree(path="", recursive=True)

        readme_files = [f for f in files if f["name"].lower().startswith("readme")]

        if not readme_files:
            return {"exists": False, "status": "Missing README"}

        return {"exists": True, "status": "README present"}

    except Exception as e:
        return {"exists": False, "status": f"Error: {e}"}
