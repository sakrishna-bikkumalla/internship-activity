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
def reimport_app(monkeypatch):
    if "app" in sys.modules:
        del sys.modules["app"]

    sys.modules["streamlit"] = make_fake_st(["https://gitlab.com", "token"], "Check Project Compliance")
    sys.modules["streamlit"].sidebar = sys.modules["streamlit"].sidebar
    sys.modules["dotenv"] = type("Dotenv", (), {"load_dotenv": lambda: None})

    import app

    yield app

    for m in ["app", "streamlit", "dotenv"]:
        if m in sys.modules:
            del sys.modules[m]


@pytest.fixture
def fresh_app_import():
    """Fixture that provides a fresh app import."""
    if "app" in sys.modules:
        del sys.modules["app"]
    yield
    if "app" in sys.modules:
        del sys.modules["app"]


def test_main_no_token(monkeypatch, reimport_app):
    app = reimport_app
    fake_st = make_fake_st(["https://gitlab.com", ""], "Check Project Compliance")
    app.st = fake_st
    monkeypatch.setattr(app, "GitLabClient", FakeClient)

    with pytest.raises(SystemExit):
        app.main()

    assert "Please enter a GitLab Token" in fake_st.messages["warning"][0]


def test_main_client_init_error(monkeypatch, reimport_app):
    app = reimport_app
    fake_st = make_fake_st(["https://gitlab.com", "token"], "Check Project Compliance")
    app.st = fake_st

    class BadClient:
        def __init__(self, url, token):
            raise Exception("boom")

    monkeypatch.setattr(app, "GitLabClient", BadClient)

    with pytest.raises(SystemExit):
        app.main()

    assert "Critical Error initializing GitLab client" in fake_st.messages["error"][0]


def test_main_mode_routing_check_project(monkeypatch, reimport_app):
    app = reimport_app
    fake_st = make_fake_st(["https://gitlab.com", "token"], "Check Project Compliance")
    app.st = fake_st
    monkeypatch.setattr(app, "GitLabClient", FakeClient)

    called = {}

    def fake_render_compliance_mode(client_obj):
        called["compliance"] = client_obj

    monkeypatch.setattr(app, "render_compliance_mode", fake_render_compliance_mode)

    app.main()

    assert called["compliance"] == "fake-client"


def test_main_mode_user_profile_not_found(monkeypatch, reimport_app):
    app = reimport_app
    fake_st = make_fake_st(["https://gitlab.com", "token", "ghost"], "User Profile Overview")
    app.st = fake_st
    monkeypatch.setattr(app, "GitLabClient", FakeClient)

    def fake_get_user_by_username(client, username):
        return None

    monkeypatch.setattr(app.users, "get_user_by_username", fake_get_user_by_username)

    app.main()

    assert "not found" in fake_st.messages["error"][0]


def test_main_mode_user_profile_exception(monkeypatch, reimport_app):
    app = reimport_app
    fake_st = make_fake_st(["https://gitlab.com", "token", "ghost"], "User Profile Overview")
    app.st = fake_st
    monkeypatch.setattr(app, "GitLabClient", FakeClient)

    def fake_get_user_by_username(client, username):
        raise Exception("nope")

    monkeypatch.setattr(app.users, "get_user_by_username", fake_get_user_by_username)

    app.main()

    assert "Error: nope" in fake_st.messages["error"][0]


@pytest.mark.parametrize(
    "mode, expected_called",
    [
        ("Batch 2026 ICFAI", "batch"),
        ("Batch 2026 RCTS", "batch"),
        ("Team Leaderboard", "team"),
        ("BAD MRs (Batch)", "bad"),
    ],
)
def test_main_other_modes(monkeypatch, reimport_app, mode, expected_called):
    app = reimport_app
    fake_st = make_fake_st(["https://gitlab.com", "token"], mode)
    app.st = fake_st
    monkeypatch.setattr(app, "GitLabClient", FakeClient)

    called = {}

    monkeypatch.setattr(app, "render_batch_mode_ui", lambda c, x=None: called.setdefault("batch", True))
    monkeypatch.setattr(app, "render_team_leaderboard", lambda c: called.setdefault("team", True))
    monkeypatch.setattr(app, "render_bad_mrs_batch_ui", lambda c: called.setdefault("bad", True))

    app.main()

    assert called[expected_called]


def test_main_invalid_mode(monkeypatch, reimport_app):
    app = reimport_app
    fake_st = make_fake_st(["https://gitlab.com", "token"], "UNKNOWN MODE")
    app.st = fake_st
    monkeypatch.setattr(app, "GitLabClient", FakeClient)

    app.main()

    assert "Routing Error" in fake_st.messages["error"][0]


def test_app_import_error_branch(monkeypatch):
    fake_st = make_fake_st(["https://gitlab.com", "token"], "Check Project Compliance")
    monkeypatch.setitem(sys.modules, "streamlit", fake_st)
    monkeypatch.setitem(sys.modules, "dotenv", type("Dotenv", (), {"load_dotenv": lambda: None}))
    monkeypatch.setitem(sys.modules, "modes.bad_mrs_batch", types.ModuleType("modes.bad_mrs_batch"))

    if "app" in sys.modules:
        del sys.modules["app"]

    with pytest.raises(ImportError):
        import app  # noqa: F401


def test_user_profile_render_user_profile(monkeypatch, reimport_app):
    app = reimport_app
    fake_st = make_fake_st(["https://gitlab.com", "token", "ghost"], "User Profile Overview")
    app.st = fake_st
    app_client = FakeClient("https://gitlab.com", "token")
    monkeypatch.setattr(app, "GitLabClient", lambda url, token: app_client)
    monkeypatch.setattr(app.users, "get_user_by_username", lambda client, username: {"id": 1})

    called = {}

    def fake_render_user_profile(client_obj, user_info):
        called["render_user_profile"] = (client_obj, user_info)

    monkeypatch.setattr(app, "render_user_profile", fake_render_user_profile)

    app.main()

    assert called.get("render_user_profile") == (app_client, {"id": 1})


def test_app_run_as_script_calls_main(monkeypatch):
    fake_st = make_fake_st(["https://gitlab.com", "token"], "Team Leaderboard")
    monkeypatch.setitem(sys.modules, "streamlit", fake_st)
    monkeypatch.setitem(sys.modules, "dotenv", type("Dotenv", (), {"load_dotenv": lambda: None}))

    monkeypatch.setitem(
        sys.modules, "gitlab_utils.users", types.SimpleNamespace(get_user_by_username=lambda c, u: None)
    )
    monkeypatch.setitem(
        sys.modules, "gitlab_utils.client", types.SimpleNamespace(GitLabClient=FakeClient, BATCH_USERNAMES=[])
    )
    monkeypatch.setitem(
        sys.modules, "modes.bad_mrs_batch", types.SimpleNamespace(render_bad_mrs_batch_ui=lambda c: None)
    )
    monkeypatch.setitem(sys.modules, "modes.batch_mode", types.SimpleNamespace(render_batch_mode_ui=lambda c, x: None))
    monkeypatch.setitem(
        sys.modules, "modes.compliance_mode", types.SimpleNamespace(render_compliance_mode=lambda c: None)
    )
    monkeypatch.setitem(
        sys.modules, "modes.team_leaderboard", types.SimpleNamespace(render_team_leaderboard=lambda c: None)
    )
    monkeypatch.setitem(sys.modules, "modes.user_profile", types.SimpleNamespace(render_user_profile=lambda c, u: None))

    if "app" in sys.modules:
        del sys.modules["app"]

    import runpy

    runpy.run_path("app.py", run_name="__main__")


def test_main_with_no_mode(monkeypatch, fresh_app_import):
    """Test app.main with no mode selected."""
    import app

    fake_st = make_fake_st(["https://gitlab.com", "token"], "")
    app.st = fake_st
    monkeypatch.setattr(app, "GitLabClient", FakeClient)

    app.main()

    assert "Routing Error" in fake_st.messages.get("error", [""])[0]


def test_main_mode_team_leaderboard(monkeypatch, reimport_app):
    """Test Team Leaderboard mode routing."""
    app = reimport_app
    fake_st = make_fake_st(["https://gitlab.com", "token"], "Team Leaderboard")
    app.st = fake_st
    monkeypatch.setattr(app, "GitLabClient", FakeClient)

    called = {}
    monkeypatch.setattr(app, "render_team_leaderboard", lambda c: called.setdefault("team", True))

    app.main()

    assert called.get("team") is True
