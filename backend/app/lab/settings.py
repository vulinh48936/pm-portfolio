"""Runtime settings stored in the `app_settings` table.

Unlike `.env`, these are edited from the Operations tab without a restart; the `.env`
values are only first-run defaults.

Keys:
    scheduler_enabled       "1"/"0"      turn the daily job on or off
    scheduler_time          "HH:MM"      run time, in scheduler_tz
    scheduler_tz            timezone     defaults to Asia/Ho_Chi_Minh
    scheduler_weekdays_only "1"/"0"      run Monday-Friday only
    job_data_day            "T" | "T-1"  sync up to today's or yesterday's session
"""

from __future__ import annotations

import os
from typing import Any

from app.database import SessionLocal
from app.models import AppSetting

DEFAULTS: dict[str, str] = {
    "scheduler_enabled": os.environ.get("SCHEDULER_ENABLED", "1"),
    "scheduler_time": os.environ.get("SCHEDULER_TIME", "16:00"),
    "scheduler_tz": os.environ.get("SCHEDULER_TZ", "Asia/Ho_Chi_Minh"),
    "scheduler_weekdays_only": os.environ.get("SCHEDULER_WEEKDAYS_ONLY", "1"),
    "job_data_day": os.environ.get("JOB_DATA_DAY", "T"),
}

_ALLOWED = set(DEFAULTS)


def get(key: str, db=None) -> str:
    """Effective value: database, then .env, then the built-in default."""
    own = db is None
    db = db or SessionLocal()
    try:
        row = db.get(AppSetting, key)
        return row.value if row and row.value != "" else DEFAULTS.get(key, "")
    finally:
        if own:
            db.close()


def all_settings(db=None) -> dict[str, str]:
    own = db is None
    db = db or SessionLocal()
    try:
        stored = {r.key: r.value for r in db.query(AppSetting).all()}
        return {k: (stored.get(k) or v) for k, v in DEFAULTS.items()}
    finally:
        if own:
            db.close()


def set_many(values: dict[str, Any], db=None) -> dict[str, str]:
    """Write known keys, ignore unknown ones, return the settings afterwards."""
    own = db is None
    db = db or SessionLocal()
    try:
        for k, v in values.items():
            if k not in _ALLOWED or v is None:
                continue
            row = db.get(AppSetting, k)
            if row:
                row.value = str(v)
            else:
                db.add(AppSetting(key=k, value=str(v)))
        db.commit()
        return all_settings(db)
    finally:
        if own:
            db.close()


def validate(values: dict[str, Any]) -> None:
    """Raise ValueError (message shown to the user) if a value is invalid."""
    t = values.get("scheduler_time")
    if t is not None:
        parts = str(t).split(":")
        if len(parts) != 2 or not all(p.isdigit() for p in parts):
            raise ValueError(f"Giờ chạy không hợp lệ: {t!r} (định dạng HH:MM).")
        hh, mm = int(parts[0]), int(parts[1])
        if not (0 <= hh <= 23 and 0 <= mm <= 59):
            raise ValueError(f"Giờ chạy ngoài khoảng: {t!r}.")
    d = values.get("job_data_day")
    if d is not None and str(d) not in ("T", "T-1"):
        raise ValueError(f"job_data_day phải là 'T' hoặc 'T-1', nhận {d!r}.")
    tz = values.get("scheduler_tz")
    if tz:
        from zoneinfo import ZoneInfo
        try:
            ZoneInfo(str(tz))
        except Exception as exc:
            raise ValueError(f"Múi giờ không hợp lệ: {tz!r} ({exc}).")
