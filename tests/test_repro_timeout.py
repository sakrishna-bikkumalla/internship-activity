import runpy

import aiohttp


def fake_response_context(data=None, raise_exc=False):
    class DummyResponse:
        async def __aenter__(self):
            if raise_exc:
                raise aiohttp.ClientConnectorError(None, None)
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def json(self):
            return data

    return DummyResponse()


class DummySession:
    def __init__(self, data=None, raise_exc=False):
        self.data = data
        self.raise_exc = raise_exc

    def request(self, method, url, timeout=None):
        assert method == "GET"
        assert timeout == 10
        return fake_response_context(data=self.data, raise_exc=self.raise_exc)


def _cleanup_client(client):
    if hasattr(client, "_loop") and client._loop is not None:
        client._loop.call_soon_threadsafe(client._loop.stop)


def test_repro_timeout_runs_success(monkeypatch, capsys):
    monkeypatch.setattr(aiohttp, "ClientSession", lambda: DummySession(data={"ok": True}))
    namespace = runpy.run_path("repro_timeout.py", run_name="__main__")
    output = capsys.readouterr().out

    assert "ok" in output
    _cleanup_client(namespace["client"])


def test_repro_timeout_runs_error(monkeypatch, capsys):
    monkeypatch.setattr(aiohttp, "ClientSession", lambda: DummySession(raise_exc=True))
    namespace = runpy.run_path("repro_timeout.py", run_name="__main__")
    output = capsys.readouterr().out

    assert "REPRODUCED ERROR" in output
    _cleanup_client(namespace["client"])


def test_repro_timeout_v2_runs_success(monkeypatch, capsys):
    monkeypatch.setattr(aiohttp, "ClientSession", lambda: DummySession(data={"ok": True}))
    namespace = runpy.run_path("repro_timeout_v2.py", run_name="__main__")
    output = capsys.readouterr().out

    assert "ok" in output
    _cleanup_client(namespace["client"])


def test_repro_timeout_v2_runs_error(monkeypatch, capsys):
    monkeypatch.setattr(aiohttp, "ClientSession", lambda: DummySession(raise_exc=True))
    namespace = runpy.run_path("repro_timeout_v2.py", run_name="__main__")
    output = capsys.readouterr().out

    assert "ERROR:" in output
    _cleanup_client(namespace["client"])
