from typing import Any, Dict, Optional


def check_templates(gl, project_id: int, ref: Optional[str] = None) -> Dict[str, Any]:
    """
    Detailed GitLab templates checker for issues and MRs.
    """
    try:
        if not ref:
            project_info = gl._get(f"/projects/{project_id}")
            ref = project_info.get("default_branch", "main")

        result = {
            "issue_templates_folder": False,
            "issue_template_files": [],
            "merge_request_templates_folder": False,
            "merge_request_template_files": [],
            "exists": False,
        }

        try:
            items = gl._get_paginated(
                f"/projects/{project_id}/repository/tree",
                params={"path": ".gitlab/issue_templates", "ref": ref},
                per_page=100,
            )
            md_files = [item.get("name") for item in (items or []) if str(item.get("name", "")).lower().endswith(".md")]
            if md_files:
                result["issue_templates_folder"] = True
                result["issue_template_files"] = md_files
                result["exists"] = True
        except Exception:
            pass

        try:
            items = gl._get_paginated(
                f"/projects/{project_id}/repository/tree",
                params={"path": ".gitlab/merge_request_templates", "ref": ref},
                per_page=100,
            )
            md_files = [item.get("name") for item in (items or []) if str(item.get("name", "")).lower().endswith(".md")]
            if md_files:
                result["merge_request_templates_folder"] = True
                result["merge_request_template_files"] = md_files
                result["exists"] = True
        except Exception:
            pass

        return result
    except Exception as e:
        return {"error": str(e)}
