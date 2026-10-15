"""Shared paths, I/O and bookkeeping for the index-forecast experiment."""

from __future__ import annotations

import json
import logging
import os
import resource
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import pandas as pd

from iaq_index.config import DEFAULT_CONFIG_PATH, load_config

REPO = Path(__file__).resolve().parents[2]
DATA_CSV = Path(os.environ.get("IAQ_INDEX_DATA", REPO / "data" / "zenodo" / "data_HOM_Pl_Zenodo.csv"))
WORK = REPO / "data" / "index_forecast"  # intermediate results (gitignored)
LOGS = REPO / "logs"
SEED = 42
N_JOBS = 4
HORIZONS_FORECAST = (1, 3, 6)
HORIZONS_ANALYSIS = (1, 3, 6, 12)
SEASONS = ("heating", "warm")

WORK.mkdir(parents=True, exist_ok=True)
LOGS.mkdir(parents=True, exist_ok=True)


def git_sha(short: bool = True) -> str:
    args = ["git", "-C", str(REPO), "rev-parse"] + (["--short"] if short else []) + ["HEAD"]
    return subprocess.check_output(args, text=True).strip()


def run_id() -> str:
    """<date>_<short sha>, fixed at the first stage of a run so restarts
    write into the same results directory."""
    p = WORK / "run_id.txt"
    if p.exists():
        return p.read_text().strip()
    rid = f"{time.strftime('%Y-%m-%d')}_{git_sha()}"
    p.write_text(rid + "\n")
    return rid


def results_dir() -> Path:
    d = REPO / "results" / "index_forecast" / run_id()
    d.mkdir(parents=True, exist_ok=True)
    return d


def figures_data_dir() -> Path:
    d = results_dir() / "figures_data"
    d.mkdir(exist_ok=True)
    return d


def figures_draft_dir() -> Path:
    d = results_dir() / "figures_draft"
    d.mkdir(exist_ok=True)
    return d


def write_table(df: pd.DataFrame, path: Path, float_digits: int = 6) -> None:
    """CSV for Excel: ';' separator, decimal comma, UTF-8 with BOM."""
    df = df.copy()
    for c in df.columns:
        if pd.api.types.is_float_dtype(df[c]):
            df[c] = df[c].round(float_digits)
    df.to_csv(path, sep=";", decimal=",", index=False, encoding="utf-8-sig")


def read_table(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, sep=";", decimal=",", encoding="utf-8-sig")


def get_logger(stage: str) -> logging.Logger:
    log = logging.getLogger(stage)
    if not log.handlers:
        log.setLevel(logging.INFO)
        fmt = logging.Formatter("%(asctime)s [%(name)s] %(message)s")
        for h in (logging.StreamHandler(sys.stdout), logging.FileHandler(LOGS / "index_forecast.log")):
            h.setFormatter(fmt)
            log.addHandler(h)
    return log


def cpu_temp_c() -> float | None:
    """SoC temperature. ``vcgencmd measure_temp`` needs /dev/vcio (root-only
    on this board), so the same sensor is read from sysfs when it fails."""
    try:
        out = subprocess.run(["vcgencmd", "measure_temp"], capture_output=True, text=True, timeout=5)
        if out.returncode == 0 and "temp=" in out.stdout:
            return float(out.stdout.split("=")[1].split("'")[0])
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        return int(Path("/sys/class/thermal/thermal_zone0/temp").read_text()) / 1000.0
    except OSError:
        return None


def peak_rss_mb() -> float:
    """Peak resident set size of this process (ru_maxrss, KiB on Linux)."""
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


@contextmanager
def stage_timer(stage: str):
    """Logs duration/temperature/peak memory of a stage into stage_times.json."""
    log = get_logger(stage)
    t0, temp0 = time.perf_counter(), cpu_temp_c()
    log.info("start (cpu %.1f C)", temp0 or float("nan"))
    yield log
    dt = time.perf_counter() - t0
    rec = {"stage": stage, "seconds": round(dt, 1), "cpu_temp_start_c": temp0, "cpu_temp_end_c": cpu_temp_c(),
           "peak_rss_mb": round(peak_rss_mb(), 1), "finished": time.strftime("%Y-%m-%d %H:%M:%S")}
    p = WORK / "stage_times.json"
    times = json.loads(p.read_text()) if p.exists() else {}
    times[stage] = rec
    p.write_text(json.dumps(times, indent=2))
    log.info("done in %.1f s, peak RSS %.0f MB", dt, rec["peak_rss_mb"])


def main_config():
    """Model config with the PM-merge decision of stage 02 applied."""
    cfg = load_config(DEFAULT_CONFIG_PATH)
    p = WORK / "pm_merge_decision.json"
    if p.exists():
        cfg = cfg.with_overrides(pm10_separate=json.loads(p.read_text())["pm10_separate"])
    return cfg


def spearman(a, b) -> float:
    from scipy.stats import spearmanr
    return float(spearmanr(a, b).statistic)


def pearson(a, b) -> float:
    return float(np.corrcoef(a, b)[0, 1])


def episodes(flag: pd.Series) -> np.ndarray:
    """Lengths (hours) of runs of consecutive True on a regular hourly grid;
    a missing hour (NaN -> False) ends an episode."""
    f = flag.fillna(False).astype(bool).to_numpy()
    if not f.any():
        return np.array([], dtype=int)
    d = np.diff(np.concatenate([[0], f.astype(int), [0]]))
    return np.flatnonzero(d == -1) - np.flatnonzero(d == 1)
