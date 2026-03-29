import importlib
import sys
import types

import pytest


def _setup_batch_depends(monkeypatch):
    """Ensure batch_mode submodules exist for import-time dependency resolution."""
    monkeypatch.setitem(
        sys.modules,
        "batch_mode.batch_service",
        types.SimpleNamespace(process_single_project=lambda gl_client, project_id, include_details=True: None),
    )
    monkeypatch.setitem(
        sys.modules,
        "batch_mode.export_service",
        types.SimpleNamespace(prepare_export_data=lambda results: []),
    )


def _run_test_for_module(module):
    fake_results = [
        {"project": "a", "status": "PASS"},
        {"project": "b", "status": "FAIL"},
    ]

    def fake_process_single_project(gl_client, project_id, include_details=True):
        if project_id == "error":
            raise Exception("boom")
        return {"project": project_id, "status": "PASS" if project_id == "good" else "FAIL"}

    def fake_prepare_export_data(results):
        return [r["project"] for r in results]

    module.process_single_project = fake_process_single_project
    module.prepare_export_data = fake_prepare_export_data

    returned = module.run_batch_for_projects("client", ["good", "bad", "error"])

    assert returned["success"] == [
        {"project": "good", "status": "PASS"},
        {"project": "bad", "status": "FAIL"},
    ]
    assert returned["failed"][0]["project"] == "error"
    assert returned["summary"]["total_projects"] == 3
    assert returned["summary"]["passed"] == 1
    assert returned["summary"]["failed"] == 1
    assert returned["summary"]["errors"] == 1
    assert returned["export_data"] == ["good", "bad"]


def test_run_batch_for_projects_batch_controller(monkeypatch):
    _setup_batch_depends(monkeypatch)
    import batch_mode.batch_controller as module

    importlib.reload(module)

    _run_test_for_module(module)


def test_run_batch_for_projects_batch_servie(monkeypatch):
    _setup_batch_depends(monkeypatch)
    import batch_mode.batch_servie as module

    importlib.reload(module)

    _run_test_for_module(module)


def test_generate_summary_edge_cases_batch_controller(monkeypatch):
    _setup_batch_depends(monkeypatch)
    import batch_mode.batch_controller as module

    importlib.reload(module)

    summary = module._generate_summary([], [{"project": "x", "error": "boom"}])
    assert summary == {"total_projects": 1, "passed": 0, "failed": 0, "errors": 1}


def test_generate_summary_edge_cases_batch_servie(monkeypatch):
    _setup_batch_depends(monkeypatch)
    import batch_mode.batch_servie as module

    importlib.reload(module)

    summary = module._generate_summary([{"project": "x", "status": "FAIL"}], [])
    assert summary == {"total_projects": 1, "passed": 0, "failed": 1, "errors": 0}
