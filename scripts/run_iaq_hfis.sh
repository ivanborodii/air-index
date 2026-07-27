#!/usr/bin/env bash
# scripts/run_iaq_hfis.sh
#
# Sample end-to-end invocation: compute -> evaluate -> report -> plot,
# over the last N minutes of live air-monitor data.
#
# Usage:
#   scripts/run_iaq_hfis.sh [minutes_back] [window_minutes]
#
# Examples:
#   scripts/run_iaq_hfis.sh            # last 60 minutes, default window
#   scripts/run_iaq_hfis.sh 1440       # last 24 hours
#   scripts/run_iaq_hfis.sh 1440 30    # last 24 hours, 30-minute window
#
# Run from the air_ml/ repository root. Does not touch air-monitor's live
# database beyond a read-only snapshot (see src/iaq_hfis/db.py) -- safe to
# run alongside the live collection service.

set -euo pipefail
cd "$(dirname "$0")/.."

MINUTES_BACK="${1:-60}"
WINDOW_MINUTES_ARG=()
if [[ -n "${2:-}" ]]; then
    WINDOW_MINUTES_ARG=(--window-minutes "$2")
fi

TO_TS=$(date -u +%Y-%m-%dT%H:%M:%S+00:00)
FROM_TS=$(date -u -d "${MINUTES_BACK} minutes ago" +%Y-%m-%dT%H:%M:%S+00:00)

echo "iaq_hfis: computing ${FROM_TS} .. ${TO_TS}"

RUN_OUTPUT=$(.venv/bin/python -m iaq_hfis.cli run --from "$FROM_TS" --to "$TO_TS" "${WINDOW_MINUTES_ARG[@]}")
echo "$RUN_OUTPUT"
RUN_ID=$(echo "$RUN_OUTPUT" | head -n1 | sed -E 's/^Run ([a-f0-9]+):.*/\1/')

if [[ -z "$RUN_ID" ]]; then
    echo "iaq_hfis: could not parse run_id from 'run' output, aborting" >&2
    exit 1
fi

echo
echo "iaq_hfis: evaluating run ${RUN_ID}"
.venv/bin/python -m iaq_hfis.cli evaluate --from "$FROM_TS" --to "$TO_TS" "${WINDOW_MINUTES_ARG[@]}" --run-id "$RUN_ID"

echo
echo "iaq_hfis: generating report for run ${RUN_ID}"
.venv/bin/python -m iaq_hfis.cli report --run-id "$RUN_ID"

echo
echo "iaq_hfis: rendering plots for run ${RUN_ID}"
.venv/bin/python -m iaq_hfis.cli plot --run-id "$RUN_ID"

echo
echo "iaq_hfis: done. Artifacts in data/iaq_hfis/reports/${RUN_ID}/"
