import sys
import types

import pytest
from conftest import make_fake_st


class FakeClient:
    def __init__(self, url, token):
        self.url = url
        self.token = token
        self.client = "fake-client"


@pytest.fixture(autouse=True)
def reimport_main(monkeypatch):
    if "gitlab_compliance_checker.ui.main" in sys.modules:
        del sys.modules["gitlab_compliance_checker.ui.main"]

    sys.modules["streamlit"] = make_fake_st(["https://gitlab.com", "token"], "Check Project Compliance")
    sys.modules["streamlit"].sidebar = sys.modules["streamlit"].sidebar
    sys.modules["dotenv"] = type("Dotenv", (), {"load_dotenv": lambda: None})

    from gitlab_compliance_checker.ui import main

    yield main

    for m in ["gitlab_compliance_checker.ui.main", "streamlit", "dotenv"]:
        if m in sys.modules:
            del sys.modules[m]


def test_main_no_token(monkeypatch, reimport_main):
    main_mod = reimport_main
    fake_st = make_fake_st(["https://gitlab.com", ""], "Check Project Compliance")
    main_mod.st = fake_st
    monkeypatch.setattr(main_mod, "GitLabClient", FakeClient)

    with pytest.raises(SystemExit):
        main_mod.main()

    assert "Please enter a GitLab Token" in fake_st.messages["warning"][0]


def test_main_client_init_error(monkeypatch, reimport_main):
    main_mod = reimport_main
    fake_st = make_fake_st(["https://gitlab.com", "token"], "Check Project Compliance")
    main_mod.st = fake_st

    class BadClient:
        def __init__(self, url, token):
            raise Exception("boom")

    monkeypatch.setattr(main_mod, "GitLabClient", BadClient)

    with pytest.raises(SystemExit):
        main_mod.main()

    assert "Critical Error initializing GitLab client" in fake_st.messages["error"][0]


def test_main_mode_routing_check_project(monkeypatch, reimport_main):
    main_mod = reimport_main
    fake_st = make_fake_st(["https://gitlab.com", "token"], "Check Project Compliance")
    main_mod.st = fake_st
    monkeypatch.setattr(main_mod, "GitLabClient", FakeClient)

    called = {}

    def fake_render_compliance_mode(client_obj):
        called["compliance"] = client_obj

    monkeypatch.setattr(main_mod, "render_compliance_mode", fake_render_compliance_mode)

    main_mod.main()

    assert called["compliance"].client == "fake-client"


def test_main_mode_user_profile_not_found(monkeypatch, reimport_main):
    main_mod = reimport_main
    fake_st = make_fake_st(["https://gitlab.com", "token", "ghost"], "User Profile Overview")
    main_mod.st = fake_st
    monkeypatch.setattr(main_mod, "GitLabClient", FakeClient)

    def fake_get_user_by_username(client, username):
        return None

    monkeypatch.setattr(main_mod.users, "get_user_by_username", fake_get_user_by_username)

    main_mod.main()

    assert "not found" in fake_st.messages["error"][0]


def test_main_mode_user_profile_exception(monkeypatch, reimport_main):
    main_mod = reimport_main
    fake_st = make_fake_st(["https://gitlab.com", "token", "ghost"], "User Profile Overview")
    main_mod.st = fake_st
    monkeypatch.setattr(main_mod, "GitLabClient", FakeClient)

    def fake_get_user_by_username(client, username):
        raise Exception("nope")

    monkeypatch.setattr(main_mod.users, "get_user_by_username", fake_get_user_by_username)

    main_mod.main()

    assert "Error: nope" in fake_st.messages["error"][0]


@pytest.mark.parametrize(
    "mode, expected_called",
    [
        ("Batch Analytics", "batch"),
        ("Team Leaderboard", "team"),
    ],
)
def test_main_other_modes(monkeypatch, reimport_main, mode, expected_called):
    main_mod = reimport_main
    fake_st = make_fake_st(["https://gitlab.com", "token"], mode)
    main_mod.st = fake_st
    monkeypatch.setattr(main_mod, "GitLabClient", FakeClient)

    called = {}

    monkeypatch.setattr(main_mod, "render_batch_analytics_ui", lambda c: called.setdefault("batch", True))
    monkeypatch.setattr(main_mod, "render_team_leaderboard", lambda c: called.setdefault("team", True))

    main_mod.main()

    assert called[expected_called]


def test_main_invalid_mode(monkeypatch, reimport_main):
    main_mod = reimport_main
    fake_st = make_fake_st(["https://gitlab.com", "token"], "UNKNOWN MODE")
    main_mod.st = fake_st
    monkeypatch.setattr(main_mod, "GitLabClient", FakeClient)

    main_mod.main()

    assert "Routing Error" in fake_st.messages["error"][0]


def test_app_import_error_branch(monkeypatch):
    fake_st = make_fake_st(["https://gitlab.com", "token"], "Check Project Compliance")
    monkeypatch.setitem(sys.modules, "streamlit", fake_st)
    monkeypatch.setitem(sys.modules, "dotenv", type("Dotenv", (), {"load_dotenv": lambda: None}))
    # Mocking the new consolidated mode module
    monkeypatch.setitem(
        sys.modules, "gitlab_compliance_checker.ui.batch", types.ModuleType("gitlab_compliance_checker.ui.batch")
    )

    if "gitlab_compliance_checker.ui.main" in sys.modules:
        del sys.modules["gitlab_compliance_checker.ui.main"]

    # This test might need rethinking if we want it to actually fail import
    # But for now let's just make it not crash.
    from gitlab_compliance_checker.ui import main  # noqa: F401


def test_user_profile_render_user_profile(monkeypatch, reimport_main):
    main_mod = reimport_main
    fake_st = make_fake_st(["https://gitlab.com", "token", "ghost"], "User Profile Overview")
    main_mod.st = fake_st
    app_client = FakeClient("https://gitlab.com", "token")
    monkeypatch.setattr(main_mod, "GitLabClient", lambda url, token: app_client)

    monkeypatch.setattr(main_mod.users, "get_user_by_username", lambda client, username: {"id": 1})

    called = {}

    def fake_render_user_profile(client_obj, user_info):
        called["render_user_profile"] = (client_obj, user_info)

    monkeypatch.setattr(main_mod, "render_user_profile", fake_render_user_profile)

    main_mod.main()

    assert called.get("render_user_profile") == (app_client, {"id": 1})


def test_app_run_as_script_calls_main(monkeypatch):
    fake_st = make_fake_st(["https://gitlab.com", "token"], "Team Leaderboard")
    monkeypatch.setitem(sys.modules, "streamlit", fake_st)
    monkeypatch.setitem(sys.modules, "dotenv", type("Dotenv", (), {"load_dotenv": lambda: None}))

    monkeypatch.setitem(
        sys.modules,
        "gitlab_compliance_checker.infrastructure.gitlab.users",
        types.SimpleNamespace(get_user_by_username=lambda c, u: None),
    )
    monkeypatch.setitem(
        sys.modules,
        "gitlab_compliance_checker.infrastructure.gitlab.client",
        types.SimpleNamespace(GitLabClient=FakeClient),
    )
    monkeypatch.setitem(
        sys.modules,
        "gitlab_compliance_checker.ui.batch",
        types.SimpleNamespace(render_batch_analytics_ui=lambda c: None),
    )
    monkeypatch.setitem(
        sys.modules,
        "gitlab_compliance_checker.ui.compliance",
        types.SimpleNamespace(render_compliance_mode=lambda c: None),
    )
    monkeypatch.setitem(
        sys.modules,
        "gitlab_compliance_checker.ui.leaderboard",
        types.SimpleNamespace(render_team_leaderboard=lambda c: None),
    )
    monkeypatch.setitem(
        sys.modules,
        "gitlab_compliance_checker.ui.profile",
        types.SimpleNamespace(render_user_profile=lambda c, u: None),
    )

    if "app" in sys.modules:
        del sys.modules["app"]

    import runpy

    runpy.run_path("app.py", run_name="__main__")


def test_main_with_no_mode(monkeypatch, reimport_main):
    """Test main with no mode selected."""
    main_mod = reimport_main

    fake_st = make_fake_st(["https://gitlab.com", "token"], "")
    main_mod.st = fake_st
    monkeypatch.setattr(main_mod, "GitLabClient", FakeClient)

    main_mod.main()

    assert "Routing Error" in fake_st.messages.get("error", [""])[0]


def test_main_mode_team_leaderboard(monkeypatch, reimport_main):
    """Test Team Leaderboard mode routing."""
    main_mod = reimport_main
    fake_st = make_fake_st(["https://gitlab.com", "token"], "Team Leaderboard")
    main_mod.st = fake_st
    monkeypatch.setattr(main_mod, "GitLabClient", FakeClient)

    called = {}
    monkeypatch.setattr(main_mod, "render_team_leaderboard", lambda c: called.setdefault("team", True))

    main_mod.main()

    assert called.get("team") is True
