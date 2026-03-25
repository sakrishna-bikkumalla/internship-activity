"""
Export service for generating CSV and Excel reports from batch compliance data.
No Streamlit dependencies - can be used in any context.
"""

import csv
import io
import os


def reports_to_csv(rows):
    """Convert a list of per-project summary dicts into CSV string.

    Args:
        rows: List of project report dicts

    Returns:
        CSV content as string
    """
    output = io.StringIO()
    writer = csv.writer(output)
    headers = [
        "project_id",
        "path",
        "branch",
        "python_count",
        "js_count",
        "common_requirements",
        "project_files",
        "tech_files",
        "license_status",
        "license_valid",
        "readme_status",
        "readme_notes",
    ]
    writer.writerow(headers)
    for r in rows:
        writer.writerow(
            [
                r.get("project_id"),
                r.get("path"),
                r.get("branch"),
                r.get("python_count"),
                r.get("js_count"),
                ";".join([os.path.basename(p) for p in r.get("common_requirements", [])]),
                ";".join([os.path.basename(p) for p in r.get("project_files", [])]),
                ";".join([os.path.basename(p) for p in r.get("tech_files", [])]),
                r.get("license_status"),
                r.get("license_valid"),
                r.get("readme_status"),
                r.get("readme_notes"),
            ]
        )
    return output.getvalue()


def reports_to_excel(rows):
    """Return Excel bytes for rows using pandas.

    Chooses an available engine (openpyxl or xlsxwriter).

    Args:
        rows: List of project report dicts

    Returns:
        Excel file content as bytes

    Raises:
        RuntimeError: If pandas or Excel engine is unavailable
    """
    try:
        from io import BytesIO

        import pandas as pd
    except Exception as e:
        raise RuntimeError(
            "pandas is required to generate Excel files. Install with: pip install pandas openpyxl"
        ) from e

    df_rows = []
    for r in rows:
        df_rows.append(
            {
                "project_id": r.get("project_id"),
                "path": r.get("path"),
                "branch": r.get("branch"),
                "python_count": r.get("python_count"),
                "js_count": r.get("js_count"),
                "common_requirements": ";".join([os.path.basename(p) for p in r.get("common_requirements", [])]),
                "project_files": ";".join([os.path.basename(p) for p in r.get("project_files", [])]),
                "tech_files": ";".join([os.path.basename(p) for p in r.get("tech_files", [])]),
                "license_status": r.get("license_status"),
                "license_valid": r.get("license_valid"),
                "readme_status": r.get("readme_status"),
                "readme_notes": ";".join(
                    r.get("readme_notes", [])
                    if isinstance(r.get("readme_notes"), list)
                    else ([r.get("readme_notes")] if r.get("readme_notes") else [])
                ),
            }
        )
    df = pd.DataFrame(df_rows)

    # Check available engines
    openpyxl_available = False
    xlsxwriter_available = False

    try:
        import openpyxl  # noqa: F401

        openpyxl_available = True
    except Exception:
        pass

    try:
        import xlsxwriter  # noqa: F401

        xlsxwriter_available = True
    except Exception:
        pass

    # Choose an available engine
    engine = None
    if openpyxl_available:
        engine = "openpyxl"
    elif xlsxwriter_available:
        engine = "xlsxwriter"

    if engine is None:
        raise RuntimeError(
            "No Excel writer available (openpyxl or xlsxwriter). Install with: pip install openpyxl or pip install xlsxwriter"
        )

    buf = BytesIO()
    try:
        # Use ExcelWriter context manager for proper file closure and flushing
        with pd.ExcelWriter(buf, engine=engine) as writer:
            df.to_excel(writer, index=False, sheet_name="Compliance Report")
    except Exception as e:
        raise RuntimeError(f"Failed to generate Excel file using engine '{engine}': {e}") from e

    buf.seek(0)
    return buf.getvalue()
