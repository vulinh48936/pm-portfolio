"""Daily job: sync data, rebuild the index files, drop caches, then re-backtest every
preset and saved strategy into DailyRun / DailyResult.

`settings.job_data_day` picks the cut-off: "T" syncs up to today's session (for an
end-of-session run, default 16:00), "T-1" up to the previous one.

Entry points: the scheduler, POST /api/lab/jobs/run, or scripts/daily_job.py.

Steps fail independently: if the Data Platform is down the job still backtests the old
snapshot and is marked "partial"; one broken strategy only fails its own row.
"""

from __future__ import annotations

import json
import logging
import threading
import traceback
from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.database import SessionLocal
from app.models import DailyResult, DailyRun, StrategyRecord

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()          # never two jobs at once


def _now() -> datetime:
    return datetime.now(timezone.utc)


def target_end_date() -> str:
    """Data cut-off per settings: "T" is today, "T-1" is yesterday."""
    from app.lab import settings
    today = date.today()
    return (today if settings.get("job_data_day") == "T" else today - timedelta(days=1)).isoformat()


def _default_config(data_end: str | None):
    """Preset config: full universe, 25% cap, from 2020-01-02 to the last session."""
    from app.lab.config import LabConfig
    return LabConfig(start_date="2020-01-02", end_date=data_end or None)


def _saved_config(cfg_json: str, data_end: str | None):
    """Config as saved (universe, cap, floors), with end_date moved to the last session
    so the new numbers stay comparable with the ones stored at save time."""
    from app.lab.schemas import LabConfigIn
    raw = json.loads(cfg_json or "{}")
    allowed = set(LabConfigIn.model_fields)
    clean = {k: v for k, v in raw.items() if k in allowed and v is not None}
    clean["end_date"] = data_end or None
    clean.setdefault("start_date", "2020-01-02")
    return LabConfigIn(**clean).to_config()


def _backtest_one(spec: dict[str, Any], config) -> dict[str, Any]:
    """Backtest one strategy in a child process, 120s timeout: this code is untrusted."""
    from app.lab.runner import run_safe
    res = run_safe(spec, config, timeout=120.0)
    return {"metrics": res["metrics"], "weights": res["weights_latest"],
            "rebalance_schedule": res["rebalance_schedule"], "move_policy": res["move_policy"]}


def run(trigger: str = "schedule", sync: bool = True, end: str | None = None,
        include_presets: bool = True, include_saved: bool = True,
        full_sync: bool = False) -> dict[str, Any]:
    """Run the whole job and return the summary also stored in DailyRun.summary_json.

    `end=None` takes the cut-off from settings (`job_data_day`).
    """
    if not _LOCK.acquire(blocking=False):
        raise RuntimeError("Job đang chạy — không khởi động job thứ hai.")
    db = SessionLocal()
    run_row = DailyRun(trigger=trigger, status="running")
    db.add(run_row)
    db.commit()
    db.refresh(run_row)
    summary: dict[str, Any] = {"run_id": run_row.id, "trigger": trigger, "steps": {}}
    partial = False
    status = "failed"
    try:
        # 1. Sync price data
        if sync:
            from app.services import market_api
            want_end = end or target_end_date()
            try:
                s = market_api.sync_universe(end=want_end, full=full_sync)
                step = {k: v for k, v in s.items() if k != "details"}
                step["full"] = full_sync
                # If the Data Platform has not published EOD yet the snapshot still ends
                # on the previous session. Not an error, but say so plainly.
                got = s.get("data_end")
                if got and got < want_end:
                    step["stale"] = f"chưa có dữ liệu tới {want_end}, mới tới {got}"
                    partial = True
                summary["steps"]["sync"] = step
                if s["errors"]:
                    partial = True
            except Exception as exc:
                logger.exception("sync thất bại")
                summary["steps"]["sync"] = {"error": str(exc)}
                partial = True

            # 2. Rebuild the benchmark files and drop caches
            from app.services import index_build
            for name, fn in (("ftse", index_build.build_ftse_index),
                             ("vnindex", index_build.build_vnindex)):
                try:
                    summary["steps"][f"build_{name}"] = fn()
                except Exception as exc:
                    logger.exception("build %s thất bại", name)
                    summary["steps"][f"build_{name}"] = {"error": str(exc)}
                    partial = True
            index_build.invalidate_caches()

        # 3. Find the last session actually present
        from app.services.csv_data import data_coverage
        from app.lab.benchmark import ftse_index_range
        px_end, ix_end = data_coverage()[1], ftse_index_range()[1]
        if not px_end or not ix_end:
            raise RuntimeError(
                "Chưa có dữ liệu giá/benchmark trong snapshot. Kiểm tra kết nối Data "
                "Platform rồi chạy lại job (lần đầu nên bật 'Tải lại toàn bộ lịch sử')."
            )
        data_end = min(px_end, ix_end)
        run_row.data_end = data_end
        db.commit()
        preset_config = _default_config(data_end)

        # 4. Re-backtest presets and saved strategies
        items: list[tuple[str, str, str, dict, Any]] = []   # (kind, ref, name, spec, config)
        if include_presets:
            from app.lab.presets import PRESETS
            items += [("preset", p, p, {"preset": p}, preset_config) for p in sorted(PRESETS)]
        if include_saved:
            for r in db.query(StrategyRecord).order_by(StrategyRecord.id).all():
                try:
                    cfg = _saved_config(r.config_json, data_end)
                except Exception as exc:                  # broken saved config: record it
                    logger.warning("config saved #%s lỗi: %s", r.id, exc)
                    cfg = exc
                items.append(("saved", str(r.id), r.name or f"strategy #{r.id}", {"code": r.code}, cfg))

        n_ok = n_err = 0
        for kind, ref, name, spec, config in items:
            row = DailyResult(run_id=run_row.id, kind=kind, ref=ref, name=name, data_end=data_end)
            try:
                if isinstance(config, Exception):
                    raise config
                out = _backtest_one(spec, config)
                # Never overwrite StrategyRecord.metrics_json: those are the numbers as of
                # the save date. Fresh ones live in DailyResult (see latest_metrics_map).
                row.metrics_json = json.dumps(out["metrics"])
                row.weights_json = json.dumps(out["weights"])
                n_ok += 1
            except Exception as exc:
                row.error = f"{type(exc).__name__}: {exc}"
                n_err += 1
                logger.warning("backtest %s/%s lỗi: %s", kind, ref, exc)
            db.add(row)
            db.commit()
        summary["steps"]["backtest"] = {"ok": n_ok, "errors": n_err, "data_end": data_end}
        if n_err:
            partial = True

        status = "partial" if partial else "ok"
    except Exception as exc:
        logger.exception("daily job thất bại")
        summary["error"] = f"{type(exc).__name__}: {exc}"
        summary["traceback"] = traceback.format_exc()[-2000:]
        status = "failed"
    finally:
        try:
            run_row.status = status
            run_row.finished_at = _now()
            run_row.summary_json = json.dumps(summary, default=str)
            db.commit()
        finally:
            db.close()
            _LOCK.release()
    summary["status"] = status
    return summary


def is_running() -> bool:
    if _LOCK.acquire(blocking=False):
        _LOCK.release()
        return False
    return True


# Queries used by the router

def _run_out(r: DailyRun) -> dict[str, Any]:
    return {"id": r.id, "status": r.status, "trigger": r.trigger, "data_end": r.data_end,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            "summary": json.loads(r.summary_json or "{}")}


def latest_metrics_map(db) -> dict[str, dict[str, Any]]:
    """{strategy_id: {metrics, data_end, error}} from the latest run, so the Saved tab
    can show fresh numbers next to the ones stored at save time."""
    last = db.query(DailyRun).filter(DailyRun.status != "running") \
             .order_by(DailyRun.id.desc()).first()
    if not last:
        return {}
    rows = db.query(DailyResult).filter(DailyResult.run_id == last.id,
                                        DailyResult.kind == "saved").all()
    return {r.ref: {"metrics": json.loads(r.metrics_json or "{}"),
                    "data_end": r.data_end, "error": r.error or None} for r in rows}


def list_runs(db, limit: int = 20) -> list[dict[str, Any]]:
    rows = db.query(DailyRun).order_by(DailyRun.id.desc()).limit(limit).all()
    return [_run_out(r) for r in rows]


def latest_results(db, run_id: int | None = None) -> dict[str, Any]:
    if run_id is None:
        last = db.query(DailyRun).filter(DailyRun.status != "running") \
                 .order_by(DailyRun.id.desc()).first()
        if not last:
            return {"run": None, "results": []}
        run_id = last.id
    run_row = db.query(DailyRun).get(run_id)
    rows = db.query(DailyResult).filter(DailyResult.run_id == run_id) \
             .order_by(DailyResult.kind, DailyResult.name).all()
    return {
        "run": _run_out(run_row) if run_row else None,
        "results": [{
            "id": x.id, "kind": x.kind, "ref": x.ref, "name": x.name, "data_end": x.data_end,
            "metrics": json.loads(x.metrics_json or "{}"),
            "weights": json.loads(x.weights_json or "{}"),
            "error": x.error or None,
        } for x in rows],
    }
