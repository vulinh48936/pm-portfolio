"""Read and write `weight.json`: the FTSE GEIS basket per review period.

This is business input the PM updates every period from the FTSE publication, not data
from the Data Platform, which is why it has its own screen instead of a file on the server.

File shape (kept as-is so index_build.py can read it):
    {"source": ..., "note": ..., "periods": [
        {"effective_date": "2026-09-01", "period": "2026-09", "num_stocks": 20,
         "constituents": [{"ticker": "VIC", "weight_pct": 23.15}, ...]}]}

Every write MUST be followed by index_build.build_ftse_index(): the drift benchmark is
derived from this file, and without a rebuild the UI keeps comparing against the old
basket. The router does that after each write.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app import paths

WEIGHT_JSON: Path = paths.WEIGHT_JSON

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TICKER_RE = re.compile(r"^[A-Z0-9]{3,10}$")


def _load_raw() -> dict[str, Any]:
    data = json.loads(WEIGHT_JSON.read_text(encoding="utf-8"))
    data.setdefault("periods", [])
    return data


def _save_raw(data: dict[str, Any]) -> None:
    """Atomic write, periods sorted by effective_date so the file stays readable."""
    data["periods"] = sorted(data.get("periods", []), key=lambda p: p["effective_date"])
    tmp = WEIGHT_JSON.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(WEIGHT_JSON)


def _clean_ticker(t: str) -> str:
    """Strip FTSE decoration (◆) and separators stuck to the code ("VHM," -> "VHM")."""
    return re.sub(r"[^A-Z0-9]", "", str(t).strip().upper())


def _summary(period: dict[str, Any]) -> dict[str, Any]:
    cons = period.get("constituents", [])
    total = round(sum(float(c.get("weight_pct", 0)) for c in cons), 4)
    return {
        "effective_date": period["effective_date"],
        "period": period.get("period", period["effective_date"][:7]),
        "num_stocks": len(cons),
        "total_weight_pct": total,
        # FTSE rounds, so the total is rarely exactly 100; a gap above 0.5pp usually
        # means a ticker is missing.
        "sum_ok": abs(total - 100.0) <= 0.5,
    }


# Read

def list_periods() -> dict[str, Any]:
    data = _load_raw()
    periods = sorted(data["periods"], key=lambda p: p["effective_date"])
    return {"source": data.get("source", ""), "note": data.get("note", ""),
            "periods": [_summary(p) for p in periods]}


def get_period(effective_date: str) -> dict[str, Any]:
    for p in _load_raw()["periods"]:
        if p["effective_date"] == effective_date:
            cons = sorted(p.get("constituents", []),
                          key=lambda c: -float(c.get("weight_pct", 0)))
            return {**_summary(p),
                    "constituents": [{"ticker": _clean_ticker(c["ticker"]),
                                      "weight_pct": round(float(c["weight_pct"]), 4)}
                                     for c in cons]}
    raise KeyError(f"Không có kỳ {effective_date}.")


# Write

def validate(effective_date: str, constituents: list[dict[str, Any]]) -> list[str]:
    """Raise ValueError on malformed input; return warnings that do not block saving."""
    if not _DATE_RE.match(effective_date or ""):
        raise ValueError(f"effective_date phải dạng YYYY-MM-DD, nhận {effective_date!r}.")
    if not constituents:
        raise ValueError("Kỳ phải có ít nhất 1 mã.")

    seen: set[str] = set()
    total = 0.0
    for c in constituents:
        t = _clean_ticker(c.get("ticker", ""))
        if not _TICKER_RE.match(t):
            raise ValueError(f"Mã không hợp lệ: {c.get('ticker')!r}.")
        if t in seen:
            raise ValueError(f"Mã {t} bị lặp trong cùng một kỳ.")
        seen.add(t)
        try:
            w = float(c.get("weight_pct"))
        except (TypeError, ValueError):
            raise ValueError(f"Weight của {t} không phải số: {c.get('weight_pct')!r}.")
        if not (0 < w <= 100):
            raise ValueError(f"Weight của {t} phải trong (0, 100], nhận {w}.")
        total += w

    warnings: list[str] = []
    if abs(total - 100.0) > 0.5:
        warnings.append(f"Tổng weight = {total:.4f}% (lệch {total - 100:+.4f}đ% so với 100%).")

    # index_build silently drops tickers with no prices, so warn about them here.
    from app.data.universe_config import TICKERS_FTSE
    unknown = sorted(seen - set(TICKERS_FTSE))
    if unknown:
        warnings.append(
            f"{len(unknown)} mã chưa có trong rổ dữ liệu ({', '.join(unknown)}): "
            f"chưa được đồng bộ giá nên sẽ bị bỏ qua khi dựng benchmark. "
            f"Thêm vào TICKERS_FTSE (universe_config.py) rồi chạy 'Tải lại toàn bộ lịch sử'."
        )
    return warnings


def upsert_period(effective_date: str, constituents: list[dict[str, Any]],
                  period_label: str | None = None) -> dict[str, Any]:
    """Add a period or overwrite the existing one with the same effective_date."""
    warnings = validate(effective_date, constituents)
    data = _load_raw()
    entry = {
        "effective_date": effective_date,
        "period": period_label or effective_date[:7],
        "num_stocks": len(constituents),
        "constituents": [{"ticker": _clean_ticker(c["ticker"]),
                          "weight_pct": round(float(c["weight_pct"]), 4)}
                         for c in constituents],
    }
    others = [p for p in data["periods"] if p["effective_date"] != effective_date]
    created = len(others) == len(data["periods"])
    data["periods"] = others + [entry]
    _save_raw(data)
    return {"created": created, "warnings": warnings, **_summary(entry)}


def delete_period(effective_date: str) -> dict[str, Any]:
    data = _load_raw()
    rest = [p for p in data["periods"] if p["effective_date"] != effective_date]
    if len(rest) == len(data["periods"]):
        raise KeyError(f"Không có kỳ {effective_date}.")
    if not rest:
        raise ValueError("Không thể xóa kỳ cuối cùng — benchmark cần ít nhất một kỳ.")
    data["periods"] = rest
    _save_raw(data)
    return {"deleted": effective_date, "remaining": len(rest)}


def _to_float(raw: str) -> float | None:
    """'23,15' -> 23.15; '1,234.56' -> 1234.56; '9.5%' -> 9.5; 'Weight' -> None.

    A comma is a decimal mark in Vietnamese tables and a thousands separator in English
    ones: exactly one comma and no dot means decimal.
    """
    num = raw.replace("%", "").replace(" ", "").strip()
    if num.count(",") == 1 and "." not in num:
        num = num.replace(",", ".")
    else:
        num = num.replace(",", "")
    try:
        return float(num)
    except ValueError:
        return None


def parse_paste(text: str) -> list[dict[str, Any]]:
    """Parse a pasted FTSE table: one `TICKER<tab|;|,|space>WEIGHT` per line.

    Blank and header lines are skipped and ◆ is stripped. Columns split on tab, `;`, `|`
    or spaces; a comma is only used as a separator when nothing else works, so decimals
    like `23,15` stay intact.
    """
    out: list[dict[str, Any]] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = [x for x in re.split(r"[\t;|]+|\s+", line) if x]
        if len(parts) < 2:                       # "VIC,23.15": only then split on the comma
            parts = [x for x in re.split(r",", line) if x.strip()]
        if len(parts) < 2:
            continue
        ticker = _clean_ticker(parts[0])
        weight = _to_float(parts[-1])
        if weight is None or not _TICKER_RE.match(ticker):
            continue                             # header line such as "Ticker  Weight"
        out.append({"ticker": ticker, "weight_pct": weight})
    return out
