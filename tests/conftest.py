import sys
import types
from unittest.mock import MagicMock

import pytest


class FakeStreamlitModule(types.ModuleType):
    def __init__(self):
        super().__init__("streamlit")

        self.session_state = {}
        self.messages = {"warning": [], "error": [], "info": []}

        self.sidebar = types.SimpleNamespace(
            _text_inputs=[],
            _mode="",
            text_input=lambda *a, **k: "",
            radio=lambda *a, **k: "",
            header=lambda *a, **k: None,
            markdown=lambda *a, **k: None,
            info=lambda *a, **k: None,
        )

        self.set_page_config = lambda *a, **k: None
        self.title = lambda *a, **k: None
        self.subheader = lambda *a, **k: None
        self.text_input = lambda *a, **k: ""
        self.text_area = lambda *a, **k: ""
        self.radio = lambda *a, **k: ""
        self.markdown = lambda *a, **k: None
        self.caption = lambda *a, **k: None

        self.spinner = lambda *a, **k: _DummyContextManager()
        self.progress = lambda *a, **k: _DummyContextManager()
        self.button = lambda *a, **k: False
        self.write = lambda *a, **k: None
        self.dataframe = lambda *a, **k: None
        self.download_button = lambda *a, **k: None
        self.columns = lambda *a, **k: [_DummyContextManager() for _ in range(2)]
        self.tabs = lambda *a, **k: [MagicMock(), MagicMock()]
        self.selectbox = lambda label, options, index=0, **k: options[index] if options else None
        self.expander = lambda *a, **k: _DummyContextManager()
        self.divider = lambda *a, **k: None
        self.number_input = lambda *a, **k: 0
        self.rerun = lambda *a, **k: None
        self.image = lambda *a, **k: None
        self.metric = lambda *a, **k: None
        self.code = lambda *a, **k: None
        self.success = lambda *a, **k: None

        # as functions that record messages and stop behavior
        self.warning = self._record_warning
        self.error = self._record_error
        self.info = self._record_info
        self.stop = self._stop
        self.caption = lambda *a, **k: None

    def _record_warning(self, message):
        self.messages["warning"].append(message)

    def _record_error(self, message):
        self.messages["error"].append(message)

    def _record_info(self, message):
        self.messages["info"].append(message)

    def _stop(self, *a, **k):
        raise SystemExit("stop")

    def cache_data(self, ttl=None):
        def deco(func):
            return CachedFunction(func)

        return deco


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

    class Sidebar:
        def __init__(self, text_inputs, mode):
            self._text_inputs = list(text_inputs or [])
            self._mode = mode

        def text_input(self, label, value=None, type=None, placeholder=None):
            if self._text_inputs:
                return self._text_inputs.pop(0)
            return ""

        def radio(self, label, options):
            return self._mode

        def header(self, text):
            return None

        def markdown(self, text):
            return None

        def info(self, text):
            return None

        def checkbox(self, label, value=True):
            return value

    fake_st.sidebar = Sidebar(text_inputs, mode)

    # mirror real usage for st.text_input and st.cache_data
    def st_text_input(label, placeholder=None, value=None, type=None):
        # use sidebar text inputs for stepwise navigation
        return fake_st.sidebar.text_input(label, value=value, type=type, placeholder=placeholder)

    def st_cache_data(ttl=None):
        def deco(func):
            return func

        return deco

    fake_st.text_input = st_text_input
    fake_st.cache_data = st_cache_data

    return fake_st


# Pre-insert the fake streamlit module during test collection, so all imports use this stub.
fake_st = FakeStreamlitModule()
if "streamlit" not in sys.modules or sys.modules.get("streamlit") is not fake_st:
    sys.modules["streamlit"] = fake_st


@pytest.fixture(autouse=True)
def patch_streamlit_module(monkeypatch):
    # Keep a stable module object across tests so st alias in imported modules stays valid.
    fake_st.session_state = {}
    monkeypatch.setitem(sys.modules, "streamlit", fake_st)
    yield
