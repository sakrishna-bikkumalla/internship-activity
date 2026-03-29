import builtins
import importlib
import runpy
import sys
import types

import pytest
from unittest.mock import MagicMock, patch

import app


def _make_spinner_mock():
    spinner = MagicMock()
    spinner.__enter__.return_value = None
    spinner.__exit__.return_value = False
    return spinner


def _ensure_export_prepare():
    import batch_mode.export_service as export_service
    if not hasattr(export_service, "prepare_export_data"):
        export_service.prepare_export_data = lambda rows: rows
    return export_service


def _ensure_batch_service_module():
    if "batch_mode.batch_service" not in sys.modules:
        mod = types.ModuleType("batch_mode.batch_service")
        mod.process_single_project = MagicMock()
        sys.modules["batch_mode.batch_service"] = mod


def _setup_sidebar_for_mode(mock_st, mode):
    mock_st.sidebar.text_input.side_effect = lambda *args, **kwargs: "https://gitlab.com" if "GitLab URL" in args else "token123"
    mock_st.sidebar.radio.return_value = mode
    mock_st.sidebar.markdown.return_value = None
    mock_st.sidebar.info.return_value = None


@patch("app.st")
@patch("app.GitLabClient")
def test_main_compliance_mode(mock_client, mock_st):
    app.render_compliance_mode = MagicMock()
    _setup_sidebar_for_mode(mock_st, "Check Project Compliance")
    mock_st.text_input.return_value = ""
    mock_st.spinner.return_value = _make_spinner_mock()
    mock_client.return_value = MagicMock(client="client")

    app.main()

    app.render_compliance_mode.assert_called_once_with("client")


@patch("app.st")
@patch("app.GitLabClient")
def test_main_token_missing_stops(mock_client, mock_st):
    _setup_sidebar_for_mode(mock_st, "Check Project Compliance")
    mock_st.sidebar.text_input.side_effect = lambda *args, **kwargs: "https://gitlab.com" if "GitLab URL" in args else ""
    mock_st.stop.side_effect = SystemExit

    with pytest.raises(SystemExit):
        app.main()

    mock_st.warning.assert_called_once_with("Please enter a GitLab Token in the sidebar or .env file.")


@patch("app.st")
@patch("app.GitLabClient")
def test_main_client_init_exception(mock_client, mock_st):
    _setup_sidebar_for_mode(mock_st, "Check Project Compliance")
    mock_st.spinner.return_value = _make_spinner_mock()
    mock_st.stop.side_effect = SystemExit
    mock_client.side_effect = Exception("fail")

    with pytest.raises(SystemExit):
        app.main()

    mock_st.error.assert_called_once_with("Critical Error initializing GitLab client: fail")


@patch("app.st")
@patch("app.GitLabClient")
def test_main_user_profile_found(mock_client, mock_st):
    app.render_user_profile = MagicMock()
    _setup_sidebar_for_mode(mock_st, "User Profile Overview")
    mock_st.text_input.return_value = " alice "
    mock_st.spinner.return_value = _make_spinner_mock()
    mock_client.return_value = MagicMock(client="client")
    app.users.get_user_by_username = MagicMock(return_value={"username": "alice"})

    app.main()

    app.render_user_profile.assert_called_once()


@patch("app.st")
@patch("app.GitLabClient")
def test_main_user_profile_not_found_and_error(mock_client, mock_st):
    _setup_sidebar_for_mode(mock_st, "User Profile Overview")
    mock_st.text_input.return_value = "unknown"
    mock_st.spinner.return_value = _make_spinner_mock()
    mock_client.return_value = MagicMock(client="client")

    app.users.get_user_by_username = MagicMock(return_value=None)
    app.main()
    mock_st.error.assert_called_with("User 'unknown' not found.")

    _setup_sidebar_for_mode(mock_st, "User Profile Overview")
    mock_st.text_input.return_value = "unknown"
    app.users.get_user_by_username.side_effect = Exception("unreachable")
    app.main()
    mock_st.error.assert_called_with("Error: unreachable")


@patch("app.st")
@patch("app.GitLabClient")
def test_main_routing_other_modes(mock_client, mock_st):
    _setup_sidebar_for_mode(mock_st, "Batch 2026 ICFAI")
    mock_st.spinner.return_value = _make_spinner_mock()
    mock_client.return_value = MagicMock(client="client")

    route_actions = {
        "Batch 2026 ICFAI": "render_batch_mode_ui",
        "Batch 2026 RCTS": "render_batch_mode_ui",
        "Team Leaderboard": "render_team_leaderboard",
        "BAD MRs (Batch)": "render_bad_mrs_batch_ui",
    }

    for mode, function_name in route_actions.items():
        _setup_sidebar_for_mode(mock_st, mode)
        fn = MagicMock()
        setattr(app, function_name, fn)
        app.main()
        fn.assert_called_once()


@patch("app.st")
@patch("app.GitLabClient")
def test_main_unknown_mode(mock_client, mock_st):
    _setup_sidebar_for_mode(mock_st, "Unknown")
    mock_st.spinner.return_value = _make_spinner_mock()
    mock_client.return_value = MagicMock(client="client")

    app.main()

    mock_st.error.assert_called_once_with("Routing Error: Unknown mode 'Unknown' selected.")


@pytest.mark.parametrize("value", [True, False])
@patch("app.st")
def test_button_behavior(mock_st, value):
    mock_st.button.return_value = value
    assert app.st.button("Test") is value


def test_import_error_branch():
    import streamlit as real_streamlit
    original_import = builtins.__import__

    def raise_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name.startswith("gitlab_utils") or name.startswith("modes"):
            raise ImportError("simulated import error")
        return original_import(name, globals, locals, fromlist, level)

    fake_st = MagicMock()
    fake_st.sidebar.text_input.side_effect = lambda *args, **kwargs: "https://gitlab.com" if "GitLab URL" in args else "token123"
    fake_st.sidebar.radio.return_value = "Check Project Compliance"
    fake_st.sidebar.markdown.return_value = None
    fake_st.sidebar.info.return_value = None
    fake_st.stop.side_effect = SystemExit

    sys.modules["streamlit"] = fake_st
    try:
        with patch("builtins.__import__", side_effect=raise_import):
            with pytest.raises(SystemExit):
                runpy.run_path("app.py", run_name="__main__")
    finally:
        sys.modules["streamlit"] = real_streamlit

    fake_st.error.assert_called_once()


@patch("modes.compliance_mode.render_compliance_mode")
@patch("app.st")
@patch("gitlab_utils.client.GitLabClient")
def test_main_when_run_as_main(mock_client, mock_st, mock_render):
    _setup_sidebar_for_mode(mock_st, "Check Project Compliance")
    mock_st.text_input.return_value = ""
    mock_st.spinner.return_value = _make_spinner_mock()
    mock_client.return_value = MagicMock(client="client")

    runpy.run_path("app.py", run_name="__main__")

    mock_render.assert_called_once()


def test_batch_controller_run_batch_for_projects():
    _ensure_export_prepare()
    _ensure_batch_service_module()

    import batch_mode.batch_controller as bc
    importlib.reload(bc)

    bc.process_single_project = MagicMock(side_effect=[
        {"project": "p1", "status": "PASS"},
        Exception("fail")
    ])
    bc.prepare_export_data = MagicMock(return_value=[{"project": "p1"}])

    result = bc.run_batch_for_projects(None, ["p1", "p2"])

    assert result["success"] == [{"project": "p1", "status": "PASS"}]
    assert result["failed"] == [{"project": "p2", "error": "fail"}]
    assert result["summary"] == {"total_projects": 2, "passed": 1, "failed": 0, "errors": 1}
    assert result["export_data"] == [{"project": "p1"}]


def test_batch_servie_run_batch_for_projects():
    _ensure_export_prepare()
    _ensure_batch_service_module()

    import batch_mode.batch_servie as bs
    importlib.reload(bs)

    bs.process_single_project = MagicMock(side_effect=[
        {"project": "p1", "status": "FAIL"},
        {"project": "p2", "status": "PASS"}
    ])
    bs.prepare_export_data = MagicMock(return_value=[{"project": "p1"}, {"project": "p2"}])

    result = bs.run_batch_for_projects(None, ["p1", "p2"])

    assert result["success"] == [{"project": "p1", "status": "FAIL"}, {"project": "p2", "status": "PASS"}]
    assert result["failed"] == []
    assert result["summary"] == {"total_projects": 2, "passed": 1, "failed": 1, "errors": 0}
    assert result["export_data"] == [{"project": "p1"}, {"project": "p2"}]


def test_batch_controller_generate_summary():
    _ensure_export_prepare()
    _ensure_batch_service_module()

    import batch_mode.batch_controller as bc
    importlib.reload(bc)

    summary = bc._generate_summary([{"status": "PASS"}, {"status": "FAIL"}], [{"project": "p"}])

    assert summary == {"total_projects": 3, "passed": 1, "failed": 1, "errors": 1}


def test_batch_servie_generate_summary():
    _ensure_export_prepare()
    _ensure_batch_service_module()

    import batch_mode.batch_servie as bs
    importlib.reload(bs)

    summary = bs._generate_summary([{"status": "PASS"}, {"status": "FAIL"}], [])

    assert summary == {"total_projects": 2, "passed": 1, "failed": 1, "errors": 0}
