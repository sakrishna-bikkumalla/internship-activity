import sys
import types
from unittest.mock import MagicMock

import pytest


class FakeStreamlitModule(types.ModuleType):
    def __init__(self):
        super().__init__("streamlit")

        self.session_state = {}
        self.query_params = {}
        self.secrets = {
            "auth": {"gitlab": {"client_id": "fake", "client_secret": "fake"}},
            "rbac": {"users": {"Saikrishna_b": "admin"}},
            "database": {"url": "sqlite:///:memory:"},
        }
        self.messages = {"warning": [], "error": [], "info": []}

        self.sidebar = types.SimpleNamespace(
            _text_inputs=[],
            _mode="",
            text_input=lambda *a, **k: "",
            radio=lambda *a, **k: "",
            header=lambda *a, **k: None,
            markdown=lambda *a, **k: None,
            info=lambda *a, **k: None,
            write=lambda *a, **k: None,
            error=lambda *a, **k: None,
            success=lambda *a, **k: None,
            button=lambda *a, **k: False,
            checkbox=lambda label, value=True: value,
            expander=lambda *a, **k: _DummyContextManager(),
        )

        self.set_page_config = lambda *a, **k: None
        self.title = lambda *a, **k: None
        self.header = lambda *a, **k: None
        self.subheader = lambda *a, **k: None
        self.text_input = lambda *a, **k: ""
        self.text_area = lambda *a, **k: ""
        self.radio = lambda *a, **k: ""
        self.markdown = lambda *a, **k: None
        self.caption = lambda *a, **k: None
        self.divider = lambda *a, **k: None
        self.date_input = lambda *a, **k: None
        self.file_uploader = lambda *a, **k: None
        self.selectbox = lambda label, options, index=0, **k: (
            options[index] if options and index < len(options) else None
        )
        self.multiselect = lambda label, options, default=None, **k: default or []
        self.number_input = lambda *a, **k: 0
        self.button = lambda *a, **k: False
        self.form_submit_button = lambda *a, **k: False
        self.form = lambda *a, **k: _DummyContextManager()
        self.spinner = lambda *a, **k: _DummyContextManager()
        self.progress = lambda *a, **k: _DummyContextManager()
        self.columns = lambda *a, **k: [MagicMock() for _ in range(2 if not a or not isinstance(a[0], int) else a[0])]
        self.tabs = lambda *a, **k: [MagicMock(), MagicMock(), MagicMock(), MagicMock()]  # Default 4 tabs for admin
        self.expander = lambda *a, **k: _DummyContextManager()
        self.write = lambda *a, **k: None
        self.dataframe = lambda *a, **k: None
        self.download_button = lambda *a, **k: None
        self.rerun = lambda *a, **k: None
        self.image = lambda *a, **k: None
        self.metric = lambda *a, **k: None
        self.code = lambda *a, **k: None
        self.success = lambda *a, **k: None
        self.warning = self._record_warning
        self.error = self._record_error
        self.info = self._record_info
        self.column_config = types.SimpleNamespace(
            LinkColumn=lambda *a, **k: MagicMock(),
            TextColumn=lambda *a, **k: MagicMock(),
            ProgressColumn=lambda *a, **k: MagicMock(),
            CheckboxColumn=lambda *a, **k: MagicMock(),
            SelectboxColumn=lambda *a, **k: MagicMock(),
            NumberColumn=lambda *a, **k: MagicMock(),
            DatetimeColumn=lambda *a, **k: MagicMock(),
            DateColumn=lambda *a, **k: MagicMock(),
            TimeColumn=lambda *a, **k: MagicMock(),
            ListColumn=lambda *a, **k: MagicMock(),
            ImageColumn=lambda *a, **k: MagicMock(),
        )
        self.stop = self._stop

    def cache_data(self, *a, **k):
        if len(a) == 1 and callable(a[0]):
            return CachedFunction(a[0])

        def deco(func):
            return CachedFunction(func)

        return deco

    def cache_resource(self, *a, **k):
        if len(a) == 1 and callable(a[0]):
            return CachedFunction(a[0])

        def deco(func):
            return CachedFunction(func)

        return deco

    def _record_warning(self, message):
        self.messages["warning"].append(message)

    def _record_error(self, message):
        self.messages["error"].append(message)

    def _record_info(self, message):
        self.messages["info"].append(message)

    def _stop(self, *a, **k):
        raise SystemExit("stop")


class CachedFunction:
    def __init__(self, func):
        self.func = func

    def __call__(self, *args, **kwargs):
        return self.func(*args, **kwargs)

    def clear(self):
        return None


class _DummyContextManager:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


def make_fake_st(text_inputs=None, mode=None):
    fake_st = FakeStreamlitModule()
    fake_st.session_state = {
        "user_role": "admin",
        "user_info": {
            "preferred_username": "Saikrishna_b",
            "username": "Saikrishna_b",
            "is_logged_in": True,
            "access_token": "fake_token",
            "name": "Saikrishna",
            "id": 1,
        },
    }

    class Sidebar:
        def __init__(self, text_inputs, mode):
            self._text_inputs = list(text_inputs or [])
            self._mode = mode
            self.header = lambda *a, **k: None
            self.markdown = lambda *a, **k: None
            self.info = lambda *a, **k: None
            self.write = lambda *a, **k: None
            self.error = lambda *a, **k: None
            self.success = lambda *a, **k: None
            self.button = lambda *a, **k: False
            self.checkbox = lambda label, value=True: value
            self.expander = lambda *a, **k: _DummyContextManager()

        def text_input(self, label, value=None, type=None, placeholder=None, key=None):
            if self._text_inputs:
                return self._text_inputs.pop(0)
            return value or ""

        def radio(self, label, options):
            return self._mode

    fake_st.sidebar = Sidebar(text_inputs, mode)

    def st_text_input(label, placeholder=None, value=None, type=None, key=None):
        return fake_st.sidebar.text_input(label, value=value, type=type, placeholder=placeholder)

    fake_st.text_input = st_text_input

    return fake_st


fake_st = FakeStreamlitModule()
if "streamlit" not in sys.modules or sys.modules.get("streamlit") is not fake_st:
    sys.modules["streamlit"] = fake_st


@pytest.fixture(autouse=True)
def patch_streamlit_module(monkeypatch):
    fake_st.session_state = {}
    fake_st.messages = {"warning": [], "error": [], "info": []}
    monkeypatch.setitem(sys.modules, "streamlit", fake_st)

    from internship_activity_tracker.infrastructure.gitlab import merge_requests

    def global_mock_compliance(*a, **k):
        return {
            "No Description": 0,
            "Failed Pipelines": 0,
            "No Issues Linked": 0,
            "No Time Spent": 0,
            "No Unit Tests": 0,
            "Total Desc Score": 0,
            "Total MRs Evaluated": 0,
        }, []

    monkeypatch.setattr(merge_requests, "get_single_user_live_mr_compliance", global_mock_compliance)

    yield
