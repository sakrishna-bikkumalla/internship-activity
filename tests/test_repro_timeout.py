import runpy

import aiohttp
import pytest


class DummyResponse:
    def __init__(self, data=None, raise_exc=False):
        self._data = data
        self.raise_exc = raise_exc

    async def __aenter__(self):
        if self.raise_exc:
            raise aiohttp.ClientConnectorError(None, None)
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self):
        return self._data


class DummySession:
    def __init__(self, data=None, raise_exc=False):
        self.data = data
        self.raise_exc = raise_exc

    def request(self, method, url, timeout=0):
        assert method == "GET"
        assert timeout == 10
        return DummyResponse(data=self.data, raise_exc=self.raise_exc)


def _cleanup_client(client):
    if hasattr(client, "_loop") and client._loop is not None:
        client._loop.call_soon_threadsafe(client._loop.stop)


def test_repro_timeout_runs_success(monkeypatch, capsys):
    monkeypatch.setattr(aiohttp, "ClientSession", lambda: DummySession(data={"ok": True}))

    namespace = runpy.run_path("repro_timeout.py", run_name="__main__")
    out = capsys.readouterr().out

    assert "{'ok': True}" in out or 'ok' in out
    _cleanup_client(namespace["client"])


def test_repro_timeout_runs_error(monkeypatch, capsys):
    monkeypatch.setattr(aiohttp, "ClientSession", lambda: DummySession(raise_exc=True))

    namespace = runpy.run_path("repro_timeout.py", run_name="__main__")
    out = capsys.readouterr().out

    assert "REPRODUCED ERROR" in out
    _cleanup_client(namespace["client"])


def test_repro_timeout_v2_runs_success(monkeypatch, capsys):
    monkeypatch.setattr(aiohttp, "ClientSession", lambda: DummySession(data={"ok": True}))

    namespace = runpy.run_path("repro_timeout_v2.py", run_name="__main__")
    out = capsys.readouterr().out

    assert "{'ok': True}" in out or 'ok' in out
    _cleanup_client(namespace["client"])


def test_repro_timeout_v2_runs_error(monkeypatch, capsys):
    monkeypatch.setattr(aiohttp, "ClientSession", lambda: DummySession(raise_exc=True))

    namespace = runpy.run_path("repro_timeout_v2.py", run_name="__main__")
    out = capsys.readouterr().out

    assert "ERROR:" in out
    _cleanup_client(namespace["client"])
