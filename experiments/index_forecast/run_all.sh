#!/usr/bin/env bash
# Full index-forecast experiment. Every stage checkpoints its outputs under
# data/index_forecast/ (stage 07 per model unit), so a rerun continues where
# it stopped. Run detached, e.g.:
#   nohup experiments/index_forecast/run_all.sh > logs/run_all.out 2>&1 &
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
PY="${PY:-$REPO/.venv-index/bin/python3}"
cd "$REPO/experiments/index_forecast"
mkdir -p "$REPO/logs"
export PYTHONHASHSEED=42

run() {  # stage name, args...; a stage already marked done is skipped
  local s="$1"; shift
  if [[ -f "$REPO/data/index_forecast/done_$s" && "${FORCE:-0}" != 1 ]]; then
    echo "skip $s (done)"; return
  fi
  "$PY" "$s.py" "$@"
  touch "$REPO/data/index_forecast/done_$s"
}

run s00_environment
run s01_data
run s02_index
run s03_correlation
run s04_aggregation
run s05_horizons
run s06_features
# stage 07 always runs: it skips finished units itself. Cheap methods first
# so complete tables for them exist early; RandomForest (the most
# expensive) last. Settings: protocol.yaml.
for methods in "linear dt hgb knn mlp" "et" "rf"; do
  "$PY" s07_forecast.py --scheme S1 S2 --methods $methods
done
run s07b_subsample_check
run s08_metrics
run s09_resources
run s10_text_check
run s11_figures
run s12_summary
"$PY" -m pytest "$REPO/tests" -q -p no:warnings | tee "$REPO/logs/pytest_index_forecast.txt"
