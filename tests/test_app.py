import sys
from unittest.mock import MagicMock, patch

import pytest
from conftest import make_fake_st


class FakeClient:
    def __init__(self, base_url, token, is_oauth=False):
        self.base_url = base_url
        self.token = token
        self.is_oauth = is_oauth
        self.client = "fake-client"

    def close(self):
        pass


@pytest.fixture(autouse=True)
def reimport_main(monkeypatch):
    if "gitlab_compliance_checker.ui.main" in sys.modules:
        del sys.modules["gitlab_compliance_checker.ui.main"]

    fake_st = make_fake_st(["https://gitlab.com", "token"], "User Profile Overview")
    fake_st.session_state["user_info"] = {
        "preferred_username": "Saikrishna_b",
        "is_logged_in": True,
        "access_token": "fake_token",
        "name": "Saikrishna"
    }
    fake_st.secrets = {
        "auth": {"gitlab": {"client_id": "fake", "client_secret": "fake"}},
        "rbac": {"users": {"Saikrishna_b": "admin"}},
        "database": {"url": "sqlite:///:memory:"}
    }
    sys.modules["streamlit"] = fake_st
    sys.modules["dotenv"] = type("Dotenv", (), {"load_dotenv": lambda: None})

    # Mock init_db to avoid real DB setup
    with patch("gitlab_compliance_checker.ui.main.init_db"):
        from gitlab_compliance_checker.ui import main
        yield main

    for m in ["gitlab_compliance_checker.ui.main", "streamlit", "dotenv"]:
        if m in sys.modules:
            del sys.modules[m]


def test_main_no_token(monkeypatch, reimport_main):
    main_mod = reimport_main
    fake_st = make_fake_st([], "User Profile Overview")
    # Clear user_info to simulate no token
    fake_st.session_state = {}
    main_mod.st = fake_st
    monkeypatch.setattr(main_mod, "GitLabClient", FakeClient)

    with pytest.raises(SystemExit):
        main_mod.main()

    assert any("Please enter a GitLab Token" in msg for msg in fake_st.messages["warning"])


def test_main_client_init_error(monkeypatch, reimport_main):
    main_mod = reimport_main
    fake_st = make_fake_st(["https://gitlab.com", "token"], "User Profile Overview")
    main_mod.st = fake_st

    class BadClient:
        def __init__(self, url, token, is_oauth=False):
            raise Exception("boom")

    monkeypatch.setattr(main_mod, "get_gitlab_client", BadClient)

    with pytest.raises(SystemExit):
        main_mod.main()

    assert any("Critical Error initializing GitLab client" in msg for msg in fake_st.messages["error"])


def test_main_mode_user_profile_not_found(monkeypatch, reimport_main):
    main_mod = reimport_main
    # Admin mode needs more inputs: URL, Lookup Method, Member selection, Button
    fake_st = make_fake_st(["https://gitlab.com"], "User Profile Overview")
    fake_st.sidebar._mode = "User Profile Overview"
    fake_st.session_state["user_role"] = "admin"
    main_mod.st = fake_st
    monkeypatch.setattr(main_mod, "get_gitlab_client", lambda *a, **k: FakeClient(*a))

    # Mock DB call
    monkeypatch.setattr("gitlab_compliance_checker.ui.main.get_all_members_with_teams", lambda: [])
    # Mock radio for lookup mode
    main_mod.st.radio = MagicMock(return_value="Manual Username Input")
    # Mock text_input for username
    main_mod.st.text_input = MagicMock(return_value="ghost")
    # Mock button
    main_mod.st.button = MagicMock(return_value=True)

    def fake_get_user_by_username(client, username):
        raise Exception("not found")

    monkeypatch.setattr(main_mod.users, "get_user_by_username", fake_get_user_by_username)

    main_mod.main()

    assert "active_profile_error" in main_mod.st.session_state
    assert "not found" in main_mod.st.session_state["active_profile_error"]


@pytest.mark.parametrize(
    "mode, expected_called",
    [
        ("Compliance Audit", "batch"),
        ("Batch Analytics and Ranking", "team"),
    ],
)
def test_main_other_modes(monkeypatch, reimport_main, mode, expected_called):
    main_mod = reimport_main
    fake_st = make_fake_st(["https://gitlab.com"], mode)
    main_mod.st = fake_st
    monkeypatch.setattr(main_mod, "get_gitlab_client", lambda *a, **k: FakeClient(*a))

    called = {}

    monkeypatch.setattr(main_mod, "render_batch_analytics_ui", lambda c: called.setdefault("batch", True))
    monkeypatch.setattr(main_mod, "render_batch_analytics", lambda c: called.setdefault("team", True))

    main_mod.main()

    assert called[expected_called]


def test_main_invalid_mode(monkeypatch, reimport_main):
    main_mod = reimport_main
    fake_st = make_fake_st(["https://gitlab.com"], "UNKNOWN MODE")
    main_mod.st = fake_st
    monkeypatch.setattr(main_mod, "get_gitlab_client", lambda *a, **k: FakeClient(*a))

    main_mod.main()

    assert any("Routing Error" in msg for msg in fake_st.messages["error"])


def test_user_profile_render_user_profile(monkeypatch, reimport_main):
    main_mod = reimport_main
    fake_st = make_fake_st(["https://gitlab.com"], "User Profile Overview")
    fake_st.session_state["user_role"] = "admin"
    main_mod.st = fake_st
    
    monkeypatch.setattr(main_mod, "get_gitlab_client", lambda *a, **k: FakeClient(*a))
    monkeypatch.setattr("gitlab_compliance_checker.ui.main.get_all_members_with_teams", lambda: [])
    main_mod.st.radio = MagicMock(return_value="Manual Username Input")
    main_mod.st.text_input = MagicMock(return_value="ghost")
    main_mod.st.button = MagicMock(return_value=True)

    monkeypatch.setattr(main_mod.users, "get_user_by_username", lambda client, username: {"id": 1})

    called = {}

    def fake_render_user_profile(client_obj, user_info):
        called["render_user_profile"] = (client_obj, user_info)

    monkeypatch.setattr(main_mod, "render_user_profile", fake_render_user_profile)

    main_mod.main()
    
    assert called.get("render_user_profile") is not None
    assert called["render_user_profile"][1] == {"id": 1}


def test_main_with_no_mode(monkeypatch, reimport_main):
    """Test main with no mode selected."""
    main_mod = reimport_main

    fake_st = make_fake_st(["https://gitlab.com"], "")
    main_mod.st = fake_st
    monkeypatch.setattr(main_mod, "get_gitlab_client", lambda *a, **k: FakeClient(*a))

    main_mod.main()

    assert any("Routing Error" in msg for msg in fake_st.messages.get("error", [""]))
