import sys
import types
from unittest.mock import MagicMock

import pytest


class FakeStreamlitModule(types.ModuleType):
    def __init__(self):
        super().__init__("streamlit")

        self.session_state = {}

        self.sidebar = types.SimpleNamespace(
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
        self.info = lambda *a, **k: None
        self.warning = lambda *a, **k: None
        self.error = lambda *a, **k: None
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
        self.error = lambda *a, **k: None
        self.info = lambda *a, **k: None
        self.warning = lambda *a, **k: None
        self.caption = lambda *a, **k: None

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
