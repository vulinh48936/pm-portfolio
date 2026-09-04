"""HTTP routes under /api/lab."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.data.universe_config import TICKERS_FTSE, TICKER_META
from app.models import StrategyRecord
from app.lab import service
from app.lab.codegen import generate_strategy
from app.lab.features import FEATURE_REGISTRY
from app.lab.presets import PRESETS
from app.lab.sandbox import validate_strategy_source
from app.lab import schemas as S

router = APIRouter(prefix="/lab", tags=["lab"])


def _to_config(cfg_in: S.LabConfigIn):
    """LabConfigIn to LabConfig, turning validation errors into 400 instead of 500."""
    try:
        return cfg_in.to_config()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Cấu hình lỗi: {exc}")


# Config and metadata

@router.get("/config/defaults")
def config_defaults():
    from app.lab.benchmark import ftse_index_range
    from app.services.csv_data import data_coverage

    universe = [
        {"ticker": t, "name": TICKER_META.get(t, {}).get("name", t),
         "sector": TICKER_META.get(t, {}).get("sector", "Khác")}
        for t in TICKERS_FTSE
    ]
    # Date bounds are the intersection of the price panel and index_ftse.csv: before the
    # index starts the benchmark would be filled with zeros and look flat.
    px_min, px_max = data_coverage()
    ix_min, ix_max = ftse_index_range()
    # Fresh install with no snapshot yet: report data_ready=false so the UI can explain
    # how to run the first sync, instead of returning 500.
    ready = all(v is not None for v in (px_min, px_max, ix_min, ix_max))
    min_date = max(px_min, ix_min) if ready else None
    max_date = min(px_max, ix_max) if ready else None
    return {
        "data_ready": ready,
        "universe": universe,
        "default_cap": 0.25,
        "start_date": min_date,
        "end_date": max_date,           # defaults to the last session with data
        "min_date": min_date,
        "max_date": max_date,
        "presets": sorted(PRESETS.keys()),
        "preset_code": {k: PRESETS[k] for k in sorted(PRESETS)},
        "features": ["price"] + sorted(FEATURE_REGISTRY.keys()),
    }


# Strategy generation and backtest

@router.post("/strategy/generate")
def generate(body: S.GenerateIn):
    config = _to_config(body.config)
    try:
        code = generate_strategy(body.nl_request, config, body.model)
        return {"code": code}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Codegen lỗi: {exc}")


@router.post("/strategy/backtest")
def backtest(body: S.BacktestIn):
    spec = S._spec_dict(body.spec)
    if spec.get("code"):
        try:
            validate_strategy_source(spec["code"])
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Code không hợp lệ: {exc}")
    config = _to_config(body.config)
    try:
        return service.backtest(spec, config)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Backtest lỗi: {exc}")


@router.post("/strategy/compare")
def compare(body: S.CompareIn):
    strategies = [{"name": it.name, "spec": S._spec_dict(it.spec)} for it in body.strategies]
    config = _to_config(body.config)
    try:
        return service.compare(strategies, config)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Compare lỗi: {exc}")


@router.post("/strategy/weight-grid")
def weight_grid(body: S.WeightGridIn):
    strategies = [{"name": it.name, "spec": S._spec_dict(it.spec)} for it in body.strategies]
    config = _to_config(body.config)
    try:
        return service.weight_grid(strategies, config, body.date,
                                   force_rebalance=body.force_rebalance)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Weight grid lỗi: {exc}")


@router.post("/strategy/attribution")
def attribution(body: S.AttributionIn):
    from app.lab.attribution import compute_attribution
    spec = S._spec_dict(body.spec)
    config = _to_config(body.config)
    try:
        res = service.run_cached(spec, config)
        return compute_attribution(res["w_matrix"], config, body.window_start)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Attribution lỗi: {exc}")


@router.post("/strategy/explain")
def explain(body: S.ExplainIn):
    """Explain a strategy. Presets return curated text and need no LLM."""
    from app.lab.explain import explain as explain_strategy
    spec = S._spec_dict(body.spec)
    config = _to_config(body.config)
    try:
        return explain_strategy(spec, config, body.model)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Explain lỗi: {exc}")


@router.post("/strategy/liquidity")
def liquidity(body: S.LiquidityIn):
    from app.lab.liquidity import analyze
    spec = S._spec_dict(body.spec)
    config = _to_config(body.config)
    try:
        res = service.run_cached(spec, config)
        return analyze(
            weights=res["weights_latest"], w_matrix=res["w_matrix"],
            rebal_idx=res.get("rebal_idx", []), tickers=config.universe, config=config,
            target_aum=body.target_aum if body.target_aum is not None else config.aum_bn,
            redeem_pct=body.redeem_pct,
            participation=body.participation, window=body.window,
            dates=res.get("weight_dates"),
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Liquidity lỗi: {exc}")


# Saved strategies

def _to_out(r: StrategyRecord) -> dict:
    return {
        "id": r.id, "name": r.name, "nl_prompt": r.nl_prompt, "code": r.code,
        "config": json.loads(r.config_json or "{}"),
        "metrics": json.loads(r.metrics_json or "{}"),
        "rebalance_schedule": r.rebalance_schedule, "move_policy": r.move_policy,
        "status": r.status,
        "created_at": r.created_at.isoformat() if r.created_at else "",
        "updated_at": r.updated_at.isoformat() if r.updated_at else "",
    }


@router.post("/strategies", status_code=201)
def save_strategy(body: S.SaveStrategyIn, db: Session = Depends(get_db)):
    try:
        validate_strategy_source(body.code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Code không hợp lệ: {exc}")
    r = StrategyRecord(
        name=body.name, nl_prompt=body.nl_prompt, code=body.code,
        config_json=json.dumps(body.config), metrics_json=json.dumps(body.metrics),
        rebalance_schedule=body.rebalance_schedule, move_policy=body.move_policy,
        status="saved",
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return _to_out(r)


@router.get("/strategies")
def list_strategies(db: Session = Depends(get_db)):
    """Includes `latest`: metrics from the most recent daily run, or None."""
    from app.lab.daily_job import latest_metrics_map
    latest = latest_metrics_map(db)
    rows = db.query(StrategyRecord).order_by(StrategyRecord.updated_at.desc()).all()
    return [{**_to_out(r), "latest": latest.get(str(r.id))} for r in rows]


@router.delete("/strategies/{sid}", status_code=204)
def delete_strategy(sid: int, db: Session = Depends(get_db)):
    r = db.query(StrategyRecord).filter(StrategyRecord.id == sid).first()
    if not r:
        raise HTTPException(status_code=404, detail="Strategy not found")
    db.delete(r)
    db.commit()


# Benchmark basket (weight.json), maintained by the PM each review period

def _rebuild_benchmark() -> dict:
    """Rebuild index_ftse.csv and drop caches after weight.json changes.

    Required: the drift benchmark is read from that file, so without a rebuild the UI
    keeps comparing against the old basket.
    """
    from app.services import index_build
    out = index_build.build_ftse_index()
    index_build.invalidate_caches()
    return out


@router.get("/weights")
def weights_list():
    """Review periods with the total weight of each."""
    from app.services import weights
    return weights.list_periods()


@router.get("/weights/{effective_date}")
def weights_get(effective_date: str):
    from app.services import weights
    try:
        return weights.get_period(effective_date)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.put("/weights/{effective_date}")
def weights_upsert(effective_date: str, body: S.WeightPeriodIn):
    """Add or edit one period, then rebuild the benchmark."""
    from app.services import weights
    try:
        res = weights.upsert_period(
            effective_date, [c.model_dump() for c in body.constituents], body.period)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    try:
        res["benchmark"] = _rebuild_benchmark()
    except Exception as exc:
        res["benchmark_error"] = str(exc)
    return res


@router.delete("/weights/{effective_date}")
def weights_delete(effective_date: str):
    from app.services import weights
    try:
        res = weights.delete_period(effective_date)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    try:
        res["benchmark"] = _rebuild_benchmark()
    except Exception as exc:
        res["benchmark_error"] = str(exc)
    return res


@router.post("/weights/parse")
def weights_parse(body: S.WeightPasteIn):
    """Parse a pasted FTSE table into normalized constituents."""
    from app.services import weights
    rows = weights.parse_paste(body.text)
    if not rows:
        raise HTTPException(status_code=400, detail="Không đọc được dòng nào. Mỗi dòng cần: MÃ và weight.")
    return {"constituents": rows, "num_stocks": len(rows),
            "total_weight_pct": round(sum(r["weight_pct"] for r in rows), 4)}


# Daily job

@router.get("/jobs/status")
def jobs_status(db: Session = Depends(get_db)):
    """Scheduler state, Data API and LLM connectivity, data range, recent runs."""
    from app.lab import daily_job, scheduler, llm
    from app.services import market_api
    from app.services.csv_data import data_coverage
    from app.lab.benchmark import ftse_index_range
    px = data_coverage()
    ix = ftse_index_range()
    return {
        "scheduler": scheduler.status(),
        "running": daily_job.is_running(),
        "market_api": {"url": market_api._env("MARKET_API_URL"),
                       "ccp_url": market_api._env("CCP_URL"),
                       "configured": market_api.is_configured()},
        "llm": llm.health(),
        "data": {"price_start": px[0], "price_end": px[1],
                 "index_start": ix[0], "index_end": ix[1]},
        "runs": daily_job.list_runs(db, limit=10),
    }


@router.get("/jobs/schedule")
def jobs_schedule_get(db: Session = Depends(get_db)):
    """Current schedule settings."""
    from app.lab import scheduler, settings
    return {"settings": settings.all_settings(db), "scheduler": scheduler.status()}


@router.put("/jobs/schedule")
def jobs_schedule_put(body: S.ScheduleIn, db: Session = Depends(get_db)):
    """Change run time, timezone, weekday-only and the T / T-1 cut-off. Takes effect at once."""
    from app.lab import scheduler, settings
    values = {k: v for k, v in body.model_dump().items() if v is not None}
    try:
        settings.validate(values)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if "scheduler_enabled" in values:
        values["scheduler_enabled"] = "1" if values["scheduler_enabled"] else "0"
    if "scheduler_weekdays_only" in values:
        values["scheduler_weekdays_only"] = "1" if values["scheduler_weekdays_only"] else "0"
    saved = settings.set_many(values, db)
    return {"settings": saved, "scheduler": scheduler.status()}


@router.post("/jobs/run", status_code=202)
def jobs_run(body: S.JobRunIn):
    """Trigger the job in the background. sync=false only re-backtests existing data;
    an empty `end` uses the configured cut-off."""
    import threading
    from app.lab import daily_job
    if daily_job.is_running():
        raise HTTPException(status_code=409, detail="Job đang chạy.")
    threading.Thread(
        target=daily_job.run,
        kwargs={"trigger": "manual", "sync": body.sync, "end": body.end,
                "include_presets": body.include_presets, "include_saved": body.include_saved,
                "full_sync": body.full_sync},
        daemon=True,
    ).start()
    return {"started": True}


@router.get("/jobs/market-ping")
def jobs_market_ping():
    from app.services import market_api
    return market_api.ping()


@router.get("/jobs/results")
def jobs_results(run_id: int | None = None, db: Session = Depends(get_db)):
    """Preset and saved metrics from the latest run, or from `run_id`."""
    from app.lab import daily_job
    return daily_job.latest_results(db, run_id)
