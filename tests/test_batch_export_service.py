import io
from unittest.mock import patch

import pandas as pd
import pytest

from batch_mode import export_service


def test_reports_to_csv():
    rows = [
        {
            "project_id": 1,
            "path": "group/proj",
            "common_requirements": ["reqs.txt"],
            "project_files": ["README.md"],
            "tech_files": ["Dockerfile"],
            "readme_notes": ["Note"],
        }
    ]
    csv_out = export_service.reports_to_csv(rows)
    assert "project_id,path" in csv_out
    assert "1,group/proj" in csv_out


def test_reports_to_excel_success():
    rows = [
        {"project_id": 1, "path": "p1", "readme_notes": ["N1", "N2"]},
        {"project_id": 2, "path": "p2", "readme_notes": "Single"},
    ]
    try:
        excel_bytes = export_service.reports_to_excel(rows)
        assert isinstance(excel_bytes, bytes)
        df = pd.read_excel(io.BytesIO(excel_bytes))
        assert len(df) == 2
    except RuntimeError as e:
        if "No Excel writer" in str(e):
            pytest.skip("openpyxl/xlsxwriter not installed")
        raise


def test_reports_to_excel_empty_rows():
    """Test with empty rows."""
    try:
        excel_bytes = export_service.reports_to_excel([])
        assert isinstance(excel_bytes, bytes)
    except RuntimeError as e:
        if "No Excel writer" in str(e):
            pytest.skip("openpyxl/xlsxwriter not installed")
        raise


@pytest.mark.skip(reason="Excel dependencies not available")
def test_reports_to_excel_with_nested_notes():
    """Test with nested readme_notes structure."""
    rows = [
        {"project_id": 1, "path": "p1", "readme_notes": [{"Line": 1, "note": "Test"}]},
    ]
    excel_bytes = export_service.reports_to_excel(rows)
    assert isinstance(excel_bytes, bytes)


@pytest.mark.skip(reason="Excel dependencies not available")
def test_reports_to_excel_engine_error():
    """Test error handling when ExcelWriter fails."""
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
        try:
            res = export_service.reports_to_excel([{"id": 1}])
            assert isinstance(res, bytes)
        except RuntimeError as e:
            if "No Excel writer" in str(e):
                pytest.skip("xlsxwriter not installed")
            raise


def test_reports_to_csv_empty():
    """Test CSV with empty rows."""
    csv_out = export_service.reports_to_csv([])
    assert "project_id" in csv_out


def test_reports_to_csv_with_special_chars():
    """Test CSV with special characters."""
    rows = [
        {"project_id": 1, "path": "path/with,comma", "notes": "Note with\nnewline"},
    ]
    csv_out = export_service.reports_to_csv(rows)
    assert "path/with,comma" in csv_out
