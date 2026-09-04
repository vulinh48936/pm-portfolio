"""Run `daily_job` on the schedule stored in `app_settings`.

One daemon thread wakes every 30 seconds and re-reads the current schedule, so changes
made in the Operations tab take effect without a restart.

Two guards stop double runs:
  1. `daily_job._LOCK` — never two jobs at once.
  2. A `daily_runs` query: skip if a `trigger="schedule"` run already started today,
     which survives a mid-day restart.

With several replicas, set SCHEDULER_ENABLED=0 and drive scripts/daily_job.py from cron.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, time as dtime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.lab import settings

logger = logging.getLogger(__name__)

_TICK = 30.0                      # seconds between schedule checks

_thread: threading.Thread | None = None
_stop = threading.Event()
_state: dict = {"last_run": None, "last_status": None, "started": False}


# Fixed Vietnam offset, used when the system lacks tzdata (no DST, so +07:00 always holds).
_VN_FALLBACK = timezone(timedelta(hours=7), "ICT")


def _tz():
    for name in (settings.get("scheduler_tz"), "Asia/Ho_Chi_Minh"):
        try:
            return ZoneInfo(name)
        except Exception:
            continue
    return _VN_FALLBACK


def _run_time() -> dtime:
    try:
        hh, mm = settings.get("scheduler_time").split(":")
        return dtime(int(hh), int(mm))
    except Exception:
        return dtime(16, 0)


def _enabled() -> bool:
    return settings.get("scheduler_enabled") == "1"


def _weekdays_only() -> bool:
    return settings.get("scheduler_weekdays_only") == "1"


def next_run(now: datetime | None = None) -> datetime:
    """Next run time under the current settings."""
    tz = _tz()
    now = now or datetime.now(tz)
    rt = _run_time()
    cand = now.replace(hour=rt.hour, minute=rt.minute, second=0, microsecond=0)
    if cand <= now:
        cand += timedelta(days=1)
    if _weekdays_only():
        while cand.weekday() >= 5:               # 5=Sat, 6=Sun
            cand += timedelta(days=1)
    return cand


def _already_ran_today(today) -> bool:
    """Has a scheduled run already started today? Survives a restart."""
    from app.database import SessionLocal
    from app.models import DailyRun

    db = SessionLocal()
    try:
        row = (db.query(DailyRun).filter(DailyRun.trigger == "schedule")
               .order_by(DailyRun.id.desc()).first())
        if not row or not row.started_at:
            return False
        started = row.started_at
        if started.tzinfo is None:               # column stores naive UTC
            started = started.replace(tzinfo=timezone.utc)
        return started.astimezone(_tz()).date() == today
    except Exception:
        return False
    finally:
        db.close()


def _loop() -> None:
    from app.lab import daily_job

    while not _stop.is_set():
        try:
            if _enabled():
                now = datetime.now(_tz())
                rt = _run_time()
                due = now.time() >= rt
                workday = now.weekday() < 5 or not _weekdays_only()
                if due and workday and not _already_ran_today(now.date()):
                    logger.info("scheduler: tới giờ %s — chạy job", rt.strftime("%H:%M"))
                    s = daily_job.run(trigger="schedule")
                    _state["last_status"] = s.get("status")
                    _state["last_run"] = datetime.now(_tz()).isoformat()
        except Exception as exc:
            logger.exception("scheduler: lỗi vòng lặp")
            _state["last_status"] = f"failed: {exc}"
            _state["last_run"] = datetime.now(_tz()).isoformat()
        _stop.wait(_TICK)


def start() -> None:
    """Start the thread; settings decide on each tick whether it actually runs."""
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="daily-scheduler", daemon=True)
    _thread.start()
    _state["started"] = True


def stop() -> None:
    _stop.set()
    _state["started"] = False


def status() -> dict:
    cfg = settings.all_settings()
    enabled = cfg["scheduler_enabled"] == "1"
    return {
        **_state,
        "enabled": enabled,
        "alive": bool(_thread and _thread.is_alive()) and enabled,
        "time": cfg["scheduler_time"],
        "tz": cfg["scheduler_tz"],
        "weekdays_only": cfg["scheduler_weekdays_only"] == "1",
        "data_day": cfg["job_data_day"],
        "next_run": next_run().isoformat() if enabled else None,
    }
