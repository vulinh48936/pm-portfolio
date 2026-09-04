"""The only market-data source: the internal Data Platform (daily OHLCV).

Flow: get a token from CCP, call the paginated data API, write the CSV snapshot under
DATA_DIR. There is no fallback source; if the API is down the job stops at the sync step
and backtests continue on the existing snapshot.

1) CCP (CyberArk Central Credential Provider) — GET `CCP_URL` returns JSON:
       {"Content": "<token>", "PolicyID": ..., "UserName": ..., ...}
   `Content` is the token. It rarely changes, so it is cached in memory for
   CCP_TOKEN_TTL seconds (24h) and re-fetched immediately on a 401/403.

2) Data — GET `MARKET_API_URL` with:
       ticker, start_time (YYYY-MM-DD), end_time, page_size (<=1000), page (starts at 1)
   Response:
       {"status": "success",
        "data": [{ticker, trading_date, open_price, high_price, low_price,
                  close_price, volume}],
        "request_id": ...,
        "pagination": {"total": n, "page_size": 1000, "page": 1, "total_pages": 1}}
   Prices are adjusted floats and are stored as-is, never rounded.

Environment (backend/.env):
    CCP_URL               CCP endpoint returning JSON with "Content"   (required)
    CCP_TOKEN_TTL         seconds, default 86400; a real expiry is caught by the 401 retry
    CCP_VERIFY_SSL        0 disables TLS verification for internal certificates
    MARKET_API_URL        OHLCV endpoint                               (required)
    MARKET_TOKEN_HEADER   header carrying the token, default Authorization
    MARKET_TOKEN_PREFIX   value prefix, default "Bearer" ("" sends the bare token)
    MARKET_PAGE_SIZE      default 1000 (API maximum)
    MARKET_INDEX_TICKER   VNINDEX symbol on the API, default VNINDEX
    MARKET_HISTORY_START  first date of a full crawl, default 2018-10-01
    MARKET_API_TIMEOUT    seconds per request, default 60
"""

from __future__ import annotations

import logging
import os
import threading
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterator

import pandas as pd

from app import paths
from app.data.universe_config import TICKERS_FTSE

logger = logging.getLogger(__name__)

DATA_DIR: Path = paths.DATA_DIR
CSV_COLS = ["time", "open", "high", "low", "close", "volume", "ticker"]

_FIELD_MAP = {
    "trading_date": "time", "open_price": "open", "high_price": "high",
    "low_price": "low", "close_price": "close", "volume": "volume",
    "vollume": "volume",                      # in case the API keeps the misspelled field
}


def _env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name)
    return v if v not in (None, "") else default


def _page_size() -> int:
    return max(1, min(1000, int(_env("MARKET_PAGE_SIZE", "1000"))))


def index_ticker() -> str:
    return _env("MARKET_INDEX_TICKER", "VNINDEX")


def history_start() -> str:
    return _env("MARKET_HISTORY_START", "2018-10-01")


def is_configured() -> bool:
    return bool(_env("MARKET_API_URL") and _env("CCP_URL"))


# CCP token

_token_lock = threading.Lock()
_token: dict[str, Any] = {"value": None, "exp": 0.0}


def get_token(force_refresh: bool = False) -> str:
    """CCP token (`Content`), cached for CCP_TOKEN_TTL. `force_refresh` skips the cache."""
    import requests

    with _token_lock:
        now = time.time()
        if not force_refresh and _token["value"] and now < _token["exp"]:
            return _token["value"]

        url = _env("CCP_URL")
        if not url:
            raise RuntimeError("Chưa cấu hình CCP_URL trong backend/.env.")
        verify = _env("CCP_VERIFY_SSL", "1") != "0"
        try:
            r = requests.get(url, timeout=float(_env("CCP_TIMEOUT", "30")), verify=verify)
            r.raise_for_status()
            body = r.json()
        except Exception as exc:
            raise RuntimeError(f"Lấy token từ CCP thất bại ({url}): {exc}") from exc

        content = body.get("Content")
        if not content:
            raise RuntimeError(f"CCP không trả trường 'Content'. Các khóa nhận được: {list(body)}")

        _token["value"] = str(content)
        _token["exp"] = now + float(_env("CCP_TOKEN_TTL", "86400"))
        logger.info("CCP: lấy token mới cho %s", body.get("UserName", "?"))
        return _token["value"]


def _auth_header(token: str) -> dict[str, str]:
    """Auth header. MARKET_TOKEN_PREFIX in .env usually has no trailing space, so one is
    inserted; leave it empty if the API expects a bare token."""
    header = _env("MARKET_TOKEN_HEADER", "Authorization")
    prefix = os.environ.get("MARKET_TOKEN_PREFIX", "Bearer").strip()
    return {header: f"{prefix} {token}" if prefix else token}


# Data API

def _get(params: dict[str, Any], retries: int = 3) -> dict[str, Any]:
    """GET one page. 401/403 refreshes the token and retries; 429/5xx backs off."""
    import requests

    url = _env("MARKET_API_URL")
    if not url:
        raise RuntimeError("Chưa cấu hình MARKET_API_URL trong backend/.env.")
    timeout = float(_env("MARKET_API_TIMEOUT", "60"))
    last: Exception | None = None
    refresh = False
    for attempt in range(retries):
        try:
            token = get_token(force_refresh=refresh)
            refresh = False
            r = requests.get(url, params=params, headers=_auth_header(token), timeout=timeout)
            if r.status_code in (401, 403):
                refresh = True                       # token rejected: refresh and retry
                raise RuntimeError(f"HTTP {r.status_code}: token bị từ chối")
            if r.status_code == 429 or r.status_code >= 500:
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
            r.raise_for_status()
            body = r.json()
            status = str(body.get("status", "")).lower()
            if status and status not in ("ok", "success", "200", "true", "1"):
                raise RuntimeError(f"status={body.get('status')} request_id={body.get('request_id')}")
            return body
        except Exception as exc:
            last = exc
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"Market API lỗi sau {retries} lần: {last}")


def _iter_pages(ticker: str, start: str, end: str) -> Iterator[list[dict]]:
    """Walk pages 1..total_pages (the API numbers pages FROM 1)."""
    size = _page_size()
    page, total_pages = 1, 1
    while page <= total_pages:
        body = _get({"ticker": ticker, "start_time": start, "end_time": end,
                     "page_size": size, "page": page})
        rows = body.get("data") or []
        yield rows
        if not rows:
            break
        pg = body.get("pagination") or {}
        declared = int(pg.get("total_pages") or 0)
        if declared:
            total_pages = declared
        else:
            # No pagination block: a full page means there is more. Trusting
            # total_pages=1 here would silently cut the history at page_size rows.
            total_pages = page + 1 if len(rows) >= size else page
        page += 1


def fetch_ohlcv(ticker: str, start: str, end: str) -> pd.DataFrame:
    """Fetch OHLCV in [start, end] as a DataFrame in snapshot-CSV format.

    Prices keep the float the API returned (adjusted); volume is cast to whole shares.
    """
    rows: list[dict] = []
    for page in _iter_pages(ticker, start, end):
        rows.extend(page)
    if not rows:
        return pd.DataFrame(columns=CSV_COLS)

    df = pd.DataFrame(rows).rename(columns=_FIELD_MAP)
    missing = [c for c in ("time", "close") if c not in df.columns]
    if missing:
        raise RuntimeError(f"API thiếu field {missing} cho {ticker}: {list(df.columns)}")
    for c in ("open", "high", "low"):
        if c not in df.columns:
            df[c] = df["close"]
    if "volume" not in df.columns:
        df["volume"] = 0

    df["time"] = pd.to_datetime(df["time"]).dt.strftime("%Y-%m-%d")
    for c in ("open", "high", "low", "close"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["close"])
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0).round().astype("int64")
    df["ticker"] = ticker
    df = df.drop_duplicates(subset="time", keep="last").sort_values("time")
    return df[CSV_COLS].reset_index(drop=True)


# Incremental snapshot sync

def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=CSV_COLS)
    df = pd.read_csv(path, dtype={"time": str})
    return df[[c for c in CSV_COLS if c in df.columns]]


def _merge(old: pd.DataFrame, new: pd.DataFrame, start: str, full: bool) -> pd.DataFrame:
    """Merge per session: sessions the API just returned win, the rest stay.

    Do not drop the whole [start, inf) window of the old file and replace it: if the API
    temporarily returns fewer sessions, that would DELETE them from the snapshot.
    `full=True` is the real re-crawl and does replace everything.
    """
    if full or old.empty:
        return new.reset_index(drop=True)
    parts = [x for x in (old, new) if not x.empty]
    return (pd.concat(parts, ignore_index=True)
            .drop_duplicates(subset="time", keep="last").sort_values("time").reset_index(drop=True))


def _write_atomic(df: pd.DataFrame, path: Path) -> None:
    """Atomic write (tmp + replace). `%.10g` keeps round prices as `13000` while adjusted
    prices such as `19453.431523279` stay accurate to about 1e-5 VND."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".csv.tmp")
    df.to_csv(tmp, index=False, float_format="%.10g")
    tmp.replace(path)


def sync_ticker(ticker: str, end: str | None = None, full: bool = False,
                overlap_days: int = 5) -> dict[str, Any]:
    """Update `{ticker}.csv` up to `end` (default today).

    Incremental: refetch from (last CSV date - overlap_days calendar days, about three
    sessions) so late corrections land. `full=True` re-crawls from MARKET_HISTORY_START,
    which a dividend or split requires since it rewrites the whole adjusted series.
    """
    end = end or date.today().isoformat()
    path = DATA_DIR / f"{ticker}.csv"
    old = _read_csv(path)
    if full or old.empty:
        start = history_start()
    else:
        last = pd.Timestamp(old["time"].max())
        start = (last - pd.Timedelta(days=overlap_days)).strftime("%Y-%m-%d")
        if start > end:
            return {"ticker": ticker, "rows_new": 0, "last": old["time"].max(), "skipped": True}

    new = fetch_ohlcv(ticker, start, end)
    if new.empty:
        return {"ticker": ticker, "rows_new": 0,
                "last": old["time"].max() if not old.empty else None, "skipped": True}

    merged = _merge(old, new, start, full)
    _write_atomic(merged, path)
    return {"ticker": ticker, "rows_new": int(len(merged) - len(old)),
            "last": merged["time"].max(), "skipped": False}


def sync_vnindex(end: str | None = None, full: bool = False) -> dict[str, Any]:
    """VNINDEX into `_VNINDEX_raw.csv`; index_build.build_vnindex() derives the index file."""
    end = end or date.today().isoformat()
    path = paths.VNINDEX_RAW_CSV
    old = _read_csv(path)
    start = (history_start() if (full or old.empty)
             else (pd.Timestamp(old["time"].max()) - pd.Timedelta(days=5)).strftime("%Y-%m-%d"))
    new = fetch_ohlcv(index_ticker(), start, end)
    if new.empty:
        return {"ticker": index_ticker(), "rows_new": 0,
                "last": old["time"].max() if not old.empty else None, "skipped": True}
    merged = _merge(old, new, start, full)
    _write_atomic(merged, path)
    return {"ticker": index_ticker(), "rows_new": int(len(merged) - len(old)),
            "last": merged["time"].max(), "skipped": False}


def sync_universe(tickers: list[str] | None = None, end: str | None = None,
                  full: bool = False) -> dict[str, Any]:
    """Sync the whole basket plus VNINDEX; one failing ticker does not stop the job."""
    tickers = list(tickers or TICKERS_FTSE)
    results, errors = [], []
    for t in tickers:
        try:
            results.append(sync_ticker(t, end=end, full=full))
        except Exception as exc:
            logger.warning("sync %s lỗi: %s", t, exc)
            errors.append({"ticker": t, "error": str(exc)})
    try:
        results.append(sync_vnindex(end=end, full=full))
    except Exception as exc:
        logger.warning("sync VNINDEX lỗi: %s", exc)
        errors.append({"ticker": index_ticker(), "error": str(exc)})
    last_dates = [r["last"] for r in results if r.get("last")]
    return {"ok": len(results), "errors": errors,
            "rows_new": int(sum(r["rows_new"] for r in results)),
            "data_end": max(last_dates) if last_dates else None,
            "details": results}


def ping() -> dict[str, Any]:
    """Check CCP and the data API with one small request (Operations tab)."""
    url = _env("MARKET_API_URL")
    if not is_configured():
        return {"ok": False, "url": url, "token": False,
                "detail": "Thiếu CCP_URL hoặc MARKET_API_URL trong .env"}
    try:
        get_token(force_refresh=True)
    except Exception as exc:
        return {"ok": False, "url": url, "token": False, "detail": f"CCP: {exc}"}
    try:
        d = (date.today() - timedelta(days=7)).isoformat()
        body = _get({"ticker": TICKERS_FTSE[0], "start_time": d,
                     "end_time": date.today().isoformat(),
                     "page_size": 1, "page": 1}, retries=1)
        pg = body.get("pagination") or {}
        return {"ok": True, "url": url, "token": True,
                "detail": f"OK — {TICKERS_FTSE[0]}: total={pg.get('total')} "
                          f"page={pg.get('page')}/{pg.get('total_pages')}"}
    except Exception as exc:
        return {"ok": False, "url": url, "token": True, "detail": f"API data: {exc}"}
