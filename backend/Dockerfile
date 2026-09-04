# Backend API image.
# Build from the REPO ROOT, not ./backend, because weight.json lives there:
#     docker build -t portfolio-construction-api:latest -f backend/Dockerfile .
#
# No data in the image: the price snapshot, weight.json and the database all live on the
# /data volume (see app/paths.py), so rebuilding the image never loses data.

FROM python:3.11-slim

# numpy/scipy would otherwise start one thread per core; backtests already run in their
# own process, so one thread each avoids CPU contention and wasted memory.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    OPENBLAS_NUM_THREADS=1 \
    OMP_NUM_THREADS=1 \
    DATA_DIR=/data/market \
    WEIGHT_JSON=/data/weight.json \
    DATABASE_URL=sqlite:////data/pm_lab.db \
    TZ=Asia/Ho_Chi_Minh

WORKDIR /app

# Separate layer so editing code does not reinstall pandas/scipy/sklearn. All of them
# ship manylinux wheels for CPython 3.11, so no compiler is needed.
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY backend/scripts ./scripts
# Seed basket; the entrypoint copies it to /data on first start.
COPY weight.json /app/seed/weight.json
COPY backend/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

RUN chmod +x /usr/local/bin/docker-entrypoint.sh \
    && useradd --create-home --uid 10001 appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /app /data
USER appuser

EXPOSE 8000

# Healthcheck uses the Python already in the image, so curl is not needed.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status==200 else 1)"

ENTRYPOINT ["docker-entrypoint.sh"]
# One worker on purpose: the scheduler lives in-process, so several workers would run the
# daily job several times. To scale, set SCHEDULER_ENABLED=0 and drive scripts/daily_job.py
# from cron or a CronJob instead.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
