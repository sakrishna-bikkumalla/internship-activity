import base64
from typing import Any, Dict, Optional
from urllib.parse import quote


def check_license(gl, project_id: int, ref: Optional[str] = None) -> Dict[str, Any]:
    """
    Detailed AGPLv3 license checker.
    """
    try:
        if not ref:
            project_info = gl._get(f"/projects/{project_id}")
            ref = project_info.get("default_branch", "main")

        license_variants = ["LICENSE", "LICENSE.md", "LICENSE.txt"]
        content = ""
        found_file = ""

        for variant in license_variants:
            try:
                encoded_path = quote(variant, safe="")
                f = gl._get(f"/projects/{project_id}/repository/files/{encoded_path}", params={"ref": ref})
                if f and isinstance(f, dict) and "content" in f:
                    content = base64.b64decode(f["content"]).decode("utf-8")
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
        has_correct_agpl_date = "19 november 2007" in cleaned

        is_agplv3 = has_affero and has_gpl and has_version_3 and has_correct_agpl_date

        if is_agplv3:
            return {"exists": True, "status": "AGPLv3", "valid": True, "file": found_file}

        if has_gpl and has_version_3:
            return {"exists": True, "status": "GPLv3 (Not Affero)", "valid": False, "file": found_file}

        return {"exists": True, "status": "Invalid (Not AGPLv3)", "valid": False, "file": found_file}

    except Exception as e:
        return {"exists": False, "status": f"Error: {e}", "valid": False}
