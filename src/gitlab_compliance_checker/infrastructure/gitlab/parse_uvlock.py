import tomllib


def parse_uvlock_content(content: str):
    """
    Parse uv.lock TOML content and return dependency info.
    """
    try:
        data = tomllib.loads(content)
    except Exception:
        return {"error": "Invalid uv.lock format"}

    packages = []

    for package in data.get("package", []):
        packages.append(
            {
                "name": package.get("name"),
                "version": package.get("version"),
                "source": package.get("source", {}).get("type"),
            }
        )

    return {
        "total_dependencies": len(packages),
        "packages": packages,
    }


def extract_dependencies_from_project(gl, project_id: int, branch="main"):
    """
    Fetch uv.lock from GitLab project and parse it via REST API.
    """
    try:
        from urllib.parse import quote
        import base64
        
        encoded_path = quote("uv.lock", safe="")
        file_obj = gl._get(f"/projects/{project_id}/repository/files/{encoded_path}", params={"ref": branch})
        if file_obj and isinstance(file_obj, dict) and "content" in file_obj:
            content = base64.b64decode(file_obj["content"]).decode("utf-8")
            return parse_uvlock_content(content)
        return {"error": "uv.lock not found or unreadable"}
    except Exception:
        return {"error": "uv.lock not found or unreadable"}
