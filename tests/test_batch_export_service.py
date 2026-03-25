import pytest
from unittest.mock import MagicMock, patch
from batch_mode import export_service
import io
import pandas as pd
import os

def test_reports_to_csv():
    rows = [
        {
            "project_id": 1,
            "path": "group/proj",
            "common_requirements": ["reqs.txt"],
            "project_files": ["README.md"],
            "tech_files": ["Dockerfile"],
            "readme_notes": ["Note"]
        }
    ]
    csv_out = export_service.reports_to_csv(rows)
    assert "project_id,path" in csv_out
    assert "1,group/proj" in csv_out

def test_reports_to_excel_success():
    rows = [
        {"project_id": 1, "path": "p1", "readme_notes": ["N1", "N2"]},
        {"project_id": 2, "path": "p2", "readme_notes": "Single"}
    ]
    excel_bytes = export_service.reports_to_excel(rows)
    assert isinstance(excel_bytes, bytes)
    df = pd.read_excel(io.BytesIO(excel_bytes))
    assert len(df) == 2

def test_reports_to_excel_no_pandas():
    # To cover line 75-78
    with patch("builtins.__import__", side_effect=lambda name, *args, **kwargs:
               (lambda: exec('raise ImportError("no pandas")'))() if name == "pandas" else
               __import__(name, *args, **kwargs)):
        with pytest.raises(RuntimeError) as exc:
            export_service.reports_to_excel([])
        assert "pandas is required" in str(exc.value)

def test_reports_to_excel_no_engine():
    # To cover line 129-132
    # We need to mock both openpyxl and xlsxwriter imports failing
    orig_import = __import__
    def mock_import(name, *args, **kwargs):
        if name in ["openpyxl", "xlsxwriter"]:
            raise ImportError(f"No {name}")
        return orig_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=mock_import):
        with pytest.raises(RuntimeError) as exc:
            export_service.reports_to_excel([{"id": 1}])
        assert "No Excel writer available" in str(exc.value)

def test_reports_to_excel_engine_error():
    # To cover line 140
    with patch("pandas.ExcelWriter", side_effect=Exception("Disk error")):
        with pytest.raises(RuntimeError) as exc:
            export_service.reports_to_excel([{"id": 1}])
        assert "Failed to generate Excel file" in str(exc.value)

def test_reports_to_excel_xlsxwriter_fallback():
    # To cover line 115-127 (openpyxl fails, xlsxwriter succeeds)
    orig_import = __import__
    def mock_import(name, *args, **kwargs):
        if name == "openpyxl":
            raise ImportError("No openpyxl")
        return orig_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=mock_import):
        # Should still work using xlsxwriter
        res = export_service.reports_to_excel([{"id": 1}])
        assert isinstance(res, bytes)
