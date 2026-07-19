"""No real network calls here -- every test injects a fake client so the
suite stays deterministic and offline. scripts/refresh_figi_crosswalk.py is
the one place that hits the real OpenFIGI API."""

from __future__ import annotations

import httpx

from qepm.universe_data_store import openfigi


class _FakeClient:
    """Records each POST and replays a scripted response, mimicking
    httpx.Client's interface (.post(), .close()) closely enough for
    _run_jobs to treat it as a real client."""

    def __init__(self, responses: list[list[dict]]):
        self._responses = responses
        self.calls: list[tuple[str, list[dict], dict]] = []
        self.closed = False

    def post(self, url, json, headers):
        self.calls.append((url, json, headers))
        body = self._responses.pop(0)
        return httpx.Response(200, json=body, request=httpx.Request("POST", url))

    def close(self):
        self.closed = True


def test_resolve_tickers_to_figi_maps_ticker_to_figi():
    client = _FakeClient([[{"data": [{"figi": "BBG-FIXTURE-001", "compositeFIGI": "BBG-FIXTURE-001"}]}]])
    result = openfigi.resolve_tickers_to_figi(["XYZ"], client=client)
    assert result == {"XYZ": "BBG-FIXTURE-001"}


def test_resolve_tickers_to_figi_omits_unresolved_tickers():
    client = _FakeClient([[{"warning": "No identifier found."}]])
    result = openfigi.resolve_tickers_to_figi(["NOTATICKER"], client=client)
    assert result == {}


def test_resolve_index_tickers_to_figi_uses_index_query_shape():
    client = _FakeClient([[{"data": [{"figi": "BBG-FIXTURE-014"}]}]])
    result = openfigi.resolve_index_tickers_to_figi(["SPX"], client=client)
    assert result == {"SPX": "BBG-FIXTURE-014"}
    _, jobs, _ = client.calls[0]
    assert jobs[0] == {"idType": "TICKER", "idValue": "SPX Index", "marketSecDes": "Index"}


def test_resolve_isins_to_figi_prefers_composite_figi_over_first_match():
    # first entry is a non-composite listing (figi != compositeFIGI); the
    # second is the composite -- must pick the second, not just data[0]
    client = _FakeClient([[{
        "data": [
            {"figi": "BBG-FIXTURE-018", "compositeFIGI": "BBG-FIXTURE-017"},
            {"figi": "BBG-FIXTURE-017", "compositeFIGI": "BBG-FIXTURE-017"},
        ]
    }]])
    result = openfigi.resolve_isins_to_figi(["US0000000101"], client=client)
    assert result == {"US0000000101": "BBG-FIXTURE-017"}


def test_resolve_isins_to_figi_falls_back_to_first_match_if_no_composite_flagged():
    client = _FakeClient([[{"data": [{"figi": "BBG-FIXTURE-018", "compositeFIGI": None}]}]])
    result = openfigi.resolve_isins_to_figi(["US0000000101"], client=client)
    assert result == {"US0000000101": "BBG-FIXTURE-018"}


def test_run_jobs_batches_and_closes_only_self_owned_clients(monkeypatch):
    monkeypatch.setattr(openfigi.time, "sleep", lambda s: None)
    tickers = [f"T{i}" for i in range(15)]  # > _BATCH_SIZE (10) forces two batches
    client = _FakeClient([
        [{"data": [{"figi": f"FIGI{i}"}]} for i in range(10)],
        [{"data": [{"figi": f"FIGI{i}"}]} for i in range(10, 15)],
    ])
    result = openfigi.resolve_tickers_to_figi(tickers, client=client)
    assert len(result) == 15
    assert len(client.calls) == 2
    assert not client.closed  # caller-supplied client is not closed by _run_jobs


def test_api_key_is_sent_as_a_header():
    client = _FakeClient([[{"data": [{"figi": "X"}]}]])
    openfigi.resolve_tickers_to_figi(["XYZ"], api_key="secret", client=client)
    _, _, headers = client.calls[0]
    assert headers["X-OPENFIGI-APIKEY"] == "secret"
