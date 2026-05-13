"""
Batch processing service for analyzing multiple GitLab projects.
No Streamlit dependencies - can be used in any context.
"""

from internship_activity_tracker.services.batch.api_helper import (
    check_project_compliance,
    classify_repository_files,
    list_all_files,
)
from internship_activity_tracker.services.batch.retry_helper import get_project_with_retries


class BatchProcessingService:
    """Service for processing multiple projects in batch mode."""

    def __init__(self, gl_client):
        """Initialize with GitLab client.

        Args:
            gl_client: GitLab client wrapper (glabflow-based)
        """
        self.gl_client = gl_client

    def process_project(self, path_or_id):
        """Process a single project and return compliance report.

        Args:
            path_or_id: Project path, URL, or ID

        Returns:
            Dict with project metadata, branch, report, and classification
        """
        try:
            proj = get_project_with_retries(self.gl_client, path_or_id)
            if not proj:
                raise ValueError("Project not found")

            # Get default branch and compliance report
            # proj is now a dict from glabflow/_get
            branch = proj.get("default_branch", "main")
            report = check_project_compliance(proj, branch=branch)

            # Classify files
            files = list_all_files(proj, branch=branch)
            classification = classify_repository_files(files)

            return {
                "project": proj,
                "report": report,
                "classification": classification,
                "branch": branch,
                "error": None,
            }
        except Exception as e:
            return {
                "project": None,
                "report": None,
                "classification": None,
                "branch": None,
                "error": str(e),
                "path_or_id": path_or_id,
            }

    def process_projects(self, paths_or_ids):
        """Process multiple projects.

        Args:
            paths_or_ids: List of project paths/URLs/IDs

        Returns:
            List of processing results (including errors)
        """
        results = []
        for path_or_id in paths_or_ids:
            result = self.process_project(path_or_id)
            results.append(result)
        return results

    def create_summary_rows(self, results):
        """Create export-ready summary rows from processing results.

        Args:
            results: List of processing results from process_projects()

        Returns:
            List of dicts suitable for CSV/Excel export
        """
        rows = []
        for result in results:
            if result.get("error"):
                # Error case
                rows.append(
                    {
                        "project_id": None,
                        "path": str(result.get("path_or_id", "unknown")),
                        "branch": None,
                        "python_count": 0,
                        "js_count": 0,
                        "common_requirements": [],
                        "project_files": [],
                        "tech_files": [],
                        "license_status": None,
                        "license_valid": False,
                        "readme_status": "error",
                        "readme_notes": result.get("error", ""),
                        "error": result.get("error"),
                    }
                )
            else:
                # Success case
                proj = result.get("project")
                report = result.get("report")
                classification = result.get("classification")

                if isinstance(proj, dict) and report and classification:
                    rows.append(
                        {
                            "project_id": proj.get("id"),
                            "path": proj.get("path_with_namespace"),
                            "branch": result.get("branch"),
                            "python_count": len(classification.get("python_files", [])),
                            "js_count": len(classification.get("js_files", [])),
                            "common_requirements": classification.get("common_requirements", []),
                            "project_files": classification.get("project_files", []),
                            "tech_files": classification.get("tech_files", []),
                            "license_status": report.get("license_status"),
                            "license_valid": report.get("license_valid"),
                            "readme_status": report.get("readme_status"),
                            "readme_notes": ";".join(
                                report.get("readme_sections", [])
                                if isinstance(report.get("readme_sections"), list)
                                else []
                            ),
                        }
                    )

        return rows
