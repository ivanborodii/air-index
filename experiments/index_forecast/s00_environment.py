"""Stage 00: environment.json (board, CPU, RAM, OS, versions, git commit)."""

import json
import platform
from importlib import metadata
from pathlib import Path

import psutil

from common import N_JOBS, SEED, cpu_temp_c, git_sha, results_dir, stage_timer

PKGS = ["pandas", "numpy", "scikit-learn", "scipy", "pyarrow", "joblib", "psutil", "PyYAML", "matplotlib", "pytest"]


def _read(p):
    try:
        return Path(p).read_text().strip("\x00\n ")
    except OSError:
        return None


def main():
    with stage_timer("s00_environment"):
        cpu = [l.split(":", 1)[1].strip() for l in (_read("/proc/cpuinfo") or "").splitlines() if l.startswith("Model")]
        os_rel = dict(l.split("=", 1) for l in (_read("/etc/os-release") or "").splitlines() if "=" in l)
        env = {
            "board_model": _read("/proc/device-tree/model"),
            "cpu": {"model": cpu[0] if cpu else platform.processor(), "machine": platform.machine(),
                    "logical_cores": psutil.cpu_count(), "physical_cores": psutil.cpu_count(logical=False),
                    "max_freq_mhz": getattr(psutil.cpu_freq(), "max", None)},
            "ram_total_gb": round(psutil.virtual_memory().total / 2**30, 2),
            "os": os_rel.get("PRETTY_NAME", "").strip('"'),
            "kernel": platform.release(),
            "python": platform.python_version(),
            "libraries": {p: metadata.version(p) for p in PKGS},
            "git_commit": git_sha(short=False),
            "random_seed": SEED,
            "n_jobs": N_JOBS,
            "cpu_temp_c_at_start": cpu_temp_c(),
        }
        (results_dir() / "environment.json").write_text(json.dumps(env, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
