from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, DateTime
from app.database import Base


def _now():
    return datetime.now(timezone.utc)


class StrategyRecord(Base):
    """A saved strategy: the re-runnable ruleset behind a base portfolio."""
    __tablename__ = "strategies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), default="")
    nl_prompt = Column(Text, default="")
    code = Column(Text, default="")
    config_json = Column(Text, default="{}")
    metrics_json = Column(Text, default="{}")
    rebalance_schedule = Column(String(20), default="quarterly")
    move_policy = Column(String(20), default="band")
    status = Column(String(20), default="draft")
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)


class DailyRun(Base):
    """One run of the daily job: sync data, then re-backtest presets + saved."""
    __tablename__ = "daily_runs"

    id = Column(Integer, primary_key=True, index=True)
    started_at = Column(DateTime, default=_now)
    finished_at = Column(DateTime, nullable=True)
    status = Column(String(20), default="running")    # running | ok | partial | failed
    trigger = Column(String(20), default="schedule")  # schedule | manual | cli
    data_end = Column(String(10), default="")
    summary_json = Column(Text, default="{}")


class DailyResult(Base):
    """Metrics of one strategy (preset or saved) within one run."""
    __tablename__ = "daily_results"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, index=True)
    kind = Column(String(10), default="preset")       # preset | saved
    ref = Column(String(120), default="")             # preset name or saved id
    name = Column(String(160), default="")
    data_end = Column(String(10), default="")
    metrics_json = Column(Text, default="{}")
    weights_json = Column(Text, default="{}")
    error = Column(Text, default="")
    created_at = Column(DateTime, default=_now)


class AppSetting(Base):
    """Runtime settings edited from the UI (job schedule), not from .env."""
    __tablename__ = "app_settings"

    key = Column(String(64), primary_key=True)
    value = Column(Text, default="")
    updated_at = Column(DateTime, default=_now, onupdate=_now)
