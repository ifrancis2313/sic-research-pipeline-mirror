"""OpenFIGI (Bloomberg's free symbology API) resolvers -- turn a ticker or
ISIN into a FIGI identifier via a real network call, replacing the
crosswalk's old hardcoded placeholder dict.

This module only resolves; it does not cache. `scripts/refresh_figi_crosswalk.py`
is the one-off caller that batch-resolves the specific securities this repo
currently needs and writes the result to `crosswalk_cache.json`, so the
pipeline's hot path (loading a spreadsheet/parquet file) never makes a live
API call -- resolving once and caching is both more robust (no network
dependency in the middle of a research run) and respects OpenFIGI's rate
limits, which matters once this scales toward a full Russell 1000 universe.

An index ticker (e.g. "SPX", the S&P 500 Index) resolves under a different
OpenFIGI query shape than a common-stock ticker -- see
`resolve_index_tickers_to_figi` vs. `resolve_tickers_to_figi`.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_MAPPING_URL = "https://api.openfigi.com/v3/mapping"
_BATCH_SIZE = 10  # OpenFIGI's per-request job cap without an API key
_THROTTLE_SECONDS = 6.0  # keeps unauthenticated requests under OpenFIGI's rate limit


def resolve_tickers_to_figi(
    tickers: list[str], exch_code: str = "US", api_key: str | None = None, client: httpx.Client | None = None
) -> dict[str, str]:
    """Resolve common-stock/ETF tickers on a given exchange to their
    composite FIGI. Tickers OpenFIGI can't resolve are omitted from the
    result (logged as a warning), not raised -- a partially-resolved
    crosswalk is more useful than an all-or-nothing failure."""
    jobs = [{"idType": "TICKER", "idValue": t, "exchCode": exch_code} for t in tickers]
    figis = _run_jobs(jobs, api_key, client)
    return {t: figi for t, figi in zip(tickers, figis, strict=True) if figi is not None}


def resolve_index_tickers_to_figi(
    tickers: list[str], api_key: str | None = None, client: httpx.Client | None = None
) -> dict[str, str]:
    """Resolve index tickers (e.g. "SPX" for the S&P 500) to FIGI. Indices
    use a different OpenFIGI query shape than equities: idValue carries a
    Bloomberg-style " Index" suffix and marketSecDes pins the security
    type, or OpenFIGI returns an unrelated equity/ETF sharing the same bare
    ticker."""
    jobs = [{"idType": "TICKER", "idValue": f"{t} Index", "marketSecDes": "Index"} for t in tickers]
    figis = _run_jobs(jobs, api_key, client)
    return {t: figi for t, figi in zip(tickers, figis, strict=True) if figi is not None}


def resolve_isins_to_figi(
    isins: list[str], api_key: str | None = None, client: httpx.Client | None = None
) -> dict[str, str]:
    """Resolve ISINs to FIGI. An ISIN can map to several FIGIs (one per
    exchange listing / share class); prefer the entry whose `figi` equals
    its own `compositeFIGI` (the canonical, exchange-independent listing)
    over an arbitrary first match."""
    jobs = [{"idType": "ID_ISIN", "idValue": i} for i in isins]
    figis = _run_jobs(jobs, api_key, client, prefer_composite=True)
    return {i: figi for i, figi in zip(isins, figis, strict=True) if figi is not None}


def _run_jobs(
    jobs: list[dict[str, str]],
    api_key: str | None,
    client: httpx.Client | None,
    prefer_composite: bool = False,
) -> list[str | None]:
    owns_client = client is None
    client = client or httpx.Client(timeout=10)
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-OPENFIGI-APIKEY"] = api_key

    figis: list[str | None] = []
    try:
        for i in range(0, len(jobs), _BATCH_SIZE):
            batch = jobs[i : i + _BATCH_SIZE]
            response = client.post(_MAPPING_URL, json=batch, headers=headers)
            response.raise_for_status()
            for job, result in zip(batch, response.json(), strict=True):
                figis.append(_extract_figi(job, result, prefer_composite))
            if i + _BATCH_SIZE < len(jobs):
                time.sleep(_THROTTLE_SECONDS)
    finally:
        if owns_client:
            client.close()
    return figis


def _extract_figi(job: dict[str, str], result: dict[str, Any], prefer_composite: bool) -> str | None:
    data = result.get("data")
    if not data:
        logger.warning("OpenFIGI could not resolve %s: %s", job, result.get("warning") or result.get("error"))
        return None
    if prefer_composite:
        composite_match = next((row for row in data if row.get("figi") == row.get("compositeFIGI")), None)
        if composite_match is not None:
            return composite_match["figi"]
    return data[0]["figi"]
