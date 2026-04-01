import base64
from typing import Any, Dict


def check_license(gl, project_id: int) -> Dict[str, Any]:
    """
    Detailed AGPLv3 license checker.
    """
    try:
        project = gl.projects.get(project_id)
        branch = getattr(project, "default_branch", "main")

        license_variants = ["LICENSE", "LICENSE.md", "LICENSE.txt"]
        content = ""
        found_file = ""

        for variant in license_variants:
            try:
                f = project.files.get(file_path=variant, ref=branch)
                content = base64.b64decode(f.content).decode("utf-8")
                found_file = variant
                break
            except Exception:
                continue

        if not content:
            return {"exists": False, "status": "LICENSE missing", "valid": False}

        cleaned = " ".join(content.strip().split()).lower()
        has_affero = "affero" in cleaned
        has_gpl = "general public license" in cleaned
        has_version_3 = "version 3" in cleaned or "v3" in cleaned or "3.0" in cleaned
        # Specific markers for AGPLv3
        has_correct_agpl_date = "19 november 2007" in cleaned

        is_agplv3 = has_affero and has_gpl and has_version_3 and has_correct_agpl_date

        if is_agplv3:
            return {"exists": True, "status": "AGPLv3", "valid": True, "file": found_file}

        # Check for other GPL variants
        if has_gpl and has_version_3:
            return {"exists": True, "status": "GPLv3 (Not Affero)", "valid": False, "file": found_file}

        return {"exists": True, "status": "Invalid (Not AGPLv3)", "valid": False, "file": found_file}

    except Exception as e:
        return {"exists": False, "status": f"Error: {e}", "valid": False}
