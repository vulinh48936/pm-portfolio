"""Run the daily job outside the API process, for cron or a Kubernetes CronJob.

    cd backend && python scripts/daily_job.py       # sync, then re-backtest
    python scripts/daily_job.py --no-sync           # re-backtest only
    python scripts/daily_job.py --end 2026-08-22    # cut the data at this date
    python scripts/daily_job.py --full-sync         # re-crawl from MARKET_HISTORY_START

Example crontab (16:00 Mon-Fri):
    0 16 * * 1-5  cd /path/backend && /path/python scripts/daily_job.py >> daily_job.log 2>&1

Set SCHEDULER_ENABLED=0 when using cron, or the job runs twice.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-sync", action="store_true")
    ap.add_argument("--end", default=None)
    ap.add_argument("--full-sync", action="store_true")
    ap.add_argument("--no-presets", action="store_true")
    ap.add_argument("--no-saved", action="store_true")
    a = ap.parse_args()

    from app.database import engine, Base
    Base.metadata.create_all(bind=engine)

    from app.lab import daily_job
    s = daily_job.run(trigger="cli", sync=not a.no_sync, end=a.end,
                      include_presets=not a.no_presets, include_saved=not a.no_saved,
                      full_sync=a.full_sync)
    print(json.dumps(s, ensure_ascii=False, indent=1, default=str))
    return 0 if s["status"] in ("ok", "partial") else 1


if __name__ == "__main__":
    raise SystemExit(main())
