import csv
import io
import os

def reports_to_csv(rows):
    """Convert list of report dicts to CSV bytes."""
    rows = rows or []

    # Keep a stable, predictable column order based on first-seen keys.
    fieldnames = []
    for row in rows:
        if isinstance(row, dict):
            for key in row.keys():
                if key not in fieldnames:
                    fieldnames.append(key)

    # Ensure we can always produce a CSV even for empty input.
    if not fieldnames:
        fieldnames = ["message"]
        rows = [{"message": "No rows available"}]

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row if isinstance(row, dict) else {"message": str(row)})

    return buffer.getvalue().encode("utf-8")

def reports_to_excel(rows):
    """Convert list of report dicts to XLSX bytes."""
    import pandas as pd

    rows = rows or []
    normalized_rows = []
    for row in rows:
        normalized_rows.append(row if isinstance(row, dict) else {"message": str(row)})

    if not normalized_rows:
        normalized_rows = [{"message": "No rows available"}]

    df = pd.DataFrame(normalized_rows)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="report")

    return output.getvalue()
