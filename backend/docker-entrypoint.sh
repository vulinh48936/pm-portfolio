#!/bin/sh
# Prepare the /data volume before starting the API:
#   - create the snapshot directory if the volume is empty
#   - seed weight.json once; later starts keep whatever the PM edited in the UI
set -e

DATA_DIR="${DATA_DIR:-/data/market}"
WEIGHT_JSON="${WEIGHT_JSON:-/data/weight.json}"
SEED_WEIGHT_JSON="${SEED_WEIGHT_JSON:-/app/seed/weight.json}"

mkdir -p "$DATA_DIR" "$(dirname "$WEIGHT_JSON")"

if [ ! -f "$WEIGHT_JSON" ]; then
    if [ -f "$SEED_WEIGHT_JSON" ]; then
        cp "$SEED_WEIGHT_JSON" "$WEIGHT_JSON"
        echo "[entrypoint] seeded the default basket into $WEIGHT_JSON"
    else
        echo "[entrypoint] WARNING: neither $WEIGHT_JSON nor the seed $SEED_WEIGHT_JSON exists;"
        echo "[entrypoint] the benchmark cannot be built until a basket is entered in the Benchmark tab."
    fi
fi

if [ -z "$(ls -A "$DATA_DIR" 2>/dev/null)" ]; then
    echo "[entrypoint] $DATA_DIR is empty - open the Operations tab and run a full history sync."
fi

exec "$@"
