"""Estimators, hyperparameter grids, splits and tuning (task 8.2, 8.5, 8.6)."""

from __future__ import annotations

import itertools
import threading
import time

import numpy as np
import pandas as pd
import psutil
from joblib import Parallel, delayed
from sklearn.base import clone
from sklearn.ensemble import (ExtraTreesClassifier, ExtraTreesRegressor, HistGradientBoostingClassifier,
                              HistGradientBoostingRegressor, RandomForestClassifier, RandomForestRegressor)
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import f1_score, mean_absolute_error
from sklearn.model_selection import TimeSeriesSplit
from sklearn.neighbors import KNeighborsClassifier, KNeighborsRegressor
from sklearn.neural_network import MLPClassifier, MLPRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor

from common import N_JOBS, SEED

METHODS = ["linear", "dt", "rf", "et", "hgb", "knn", "mlp"]
# The linear method is Ridge for regression and LogisticRegression for classification.
SCALED = {"linear", "knn", "mlp"}           # StandardScaler inside the Pipeline
INTERNAL_PARALLEL = {"rf", "et", "hgb", "knn"}  # use n_jobs/threads themselves
SAMPLE_WEIGHTED = {"hgb", "mlp"}            # classification: weights 1/class frequency
N_CLASSES = 5


def make_estimator(method: str, task: str):
    reg = task == "reg"
    if method == "linear":
        est = Ridge() if reg else LogisticRegression(max_iter=2000, class_weight="balanced")
    elif method == "dt":
        est = DecisionTreeRegressor(random_state=SEED) if reg else DecisionTreeClassifier(random_state=SEED, class_weight="balanced")
    elif method == "rf":
        kw = dict(min_samples_leaf=5, n_jobs=N_JOBS, random_state=SEED)
        est = RandomForestRegressor(**kw) if reg else RandomForestClassifier(**kw, class_weight="balanced")
    elif method == "et":
        kw = dict(min_samples_leaf=5, n_jobs=N_JOBS, random_state=SEED)
        est = ExtraTreesRegressor(**kw) if reg else ExtraTreesClassifier(**kw, class_weight="balanced")
    elif method == "hgb":
        est = HistGradientBoostingRegressor(random_state=SEED) if reg else HistGradientBoostingClassifier(random_state=SEED)
    elif method == "knn":
        est = KNeighborsRegressor(n_jobs=N_JOBS) if reg else KNeighborsClassifier(n_jobs=N_JOBS)
    elif method == "mlp":
        kw = dict(early_stopping=True, random_state=SEED)
        est = MLPRegressor(**kw) if reg else MLPClassifier(**kw)
    else:
        raise KeyError(method)
    if method in SCALED:
        return Pipeline([("scaler", StandardScaler()), ("model", est)])
    return Pipeline([("model", est)])


def grid(method: str, task: str) -> list[dict]:
    g = {
        "linear": {"alpha": [0.1, 1, 10]} if task == "reg" else {"C": [0.1, 1, 10]},
        "dt": {"max_depth": [6, 10, 14]},
        "rf": {"n_estimators": [100, 200], "max_depth": [12, None], "min_samples_leaf": [5]},
        "et": {"n_estimators": [100, 200], "max_depth": [12, None], "min_samples_leaf": [5]},
        "hgb": {"learning_rate": [0.05, 0.1], "max_leaf_nodes": [31, 63]},
        "knn": {"n_neighbors": [5, 15, 31]},
        "mlp": {"hidden_layer_sizes": [(64,), (64, 32)], "alpha": [1e-4, 1e-3]},
    }[method]
    keys = list(g)
    return [dict(zip(keys, v)) for v in itertools.product(*(g[k] for k in keys))]


def class_weights(y: np.ndarray) -> np.ndarray:
    counts = np.bincount(y.astype(int), minlength=N_CLASSES).astype(float)
    present = counts > 0
    w = np.zeros(N_CLASSES)
    w[present] = len(y) / (present.sum() * counts[present])
    return w[y.astype(int)]


def fit_model(method: str, task: str, params: dict, X, y):
    est = make_estimator(method, task)
    est.set_params(**{f"model__{k}": v for k, v in params.items()})
    fit_kw = {}
    if task == "clf" and method in SAMPLE_WEIGHTED:
        fit_kw["model__sample_weight"] = class_weights(y)
    est.fit(X, y, **fit_kw)
    return est


def predict(est, task: str, X, clip: tuple[float, float] | None):
    p = est.predict(X)
    if task == "reg" and clip is not None:
        p = np.clip(p, *clip)
    return p


def score(task: str, y, p) -> float:
    """Higher is better: -MAE (regression) or macro-F1 (classification)."""
    if task == "reg":
        return -mean_absolute_error(y, p)
    return f1_score(y, p, labels=list(range(N_CLASSES)), average="macro", zero_division=0)


# ---------------------------------------------------------------- splits
def split_masks(df: pd.DataFrame, homes_train, homes_test, span: pd.DataFrame, h: int):
    """Per home: training = first 75% of the period (t + h < cut), test =
    last 25% after a gap of 24 + h hours (t >= cut + 24 + h). Rows with t in
    the gap are used for neither."""
    cut = df["home"].map(span["cut"])
    train = df["home"].isin(homes_train) & (df["time"] + pd.Timedelta(hours=h) < cut)
    test = df["home"].isin(homes_test) & (df["time"] >= cut + pd.Timedelta(hours=24 + h))
    return train.to_numpy().copy(), test.to_numpy().copy()


def inner_splits_s1(train_times: np.ndarray) -> list[tuple[np.ndarray, np.ndarray]]:
    """S1 tuning: TimeSeriesSplit(3) over the pooled training rows ordered by time."""
    order = np.argsort(train_times, kind="stable")
    return [(order[a], order[b]) for a, b in TimeSeriesSplit(n_splits=3).split(order)]


def inner_splits_s2(train_df: pd.DataFrame, h: int, seed: int = SEED) -> list[tuple[np.ndarray, np.ndarray]]:
    """S2 tuning: training homes split into 3 groups; each group in turn is
    validation. Same time cut-off logic as the outer split, applied inside
    the training period: inner cut at 75% of each home's training span,
    inner-train t + h < inner cut, inner-validation t >= inner cut + 24 + h."""
    homes = np.array(sorted(train_df["home"].unique()))
    rng = np.random.default_rng(seed)
    groups = np.array_split(rng.permutation(homes), 3)
    span = train_df.groupby("home")["time"].agg(["min", "max"])
    cut = train_df["home"].map(span["min"] + 0.75 * (span["max"] - span["min"]))
    t = train_df["time"]
    early = (t + pd.Timedelta(hours=h) < cut).to_numpy()
    late = (t >= cut + pd.Timedelta(hours=24 + h)).to_numpy()
    out = []
    for g in groups:
        val_home = train_df["home"].isin(g).to_numpy()
        out.append((np.flatnonzero(~val_home & early), np.flatnonzero(val_home & late)))
    return out


def subsample_train(df: pd.DataFrame, train: np.ndarray, frac: float | None, seed: int = SEED) -> np.ndarray:
    """Random ``frac`` of the training rows, drawn within each home (so every
    home keeps its share), after the features were computed on the full
    hourly series. Deterministic for a given frame, so all methods of one
    (scheme, fold, h) get the same rows. Test rows are never subsampled."""
    if not frac or frac >= 1:
        return train
    rng = np.random.default_rng(seed)
    out = np.zeros_like(train)
    idx = np.flatnonzero(train)
    homes = df["home"].to_numpy()[idx]
    for h in np.unique(homes):
        rows = idx[homes == h]
        out[rng.choice(rows, size=int(round(frac * len(rows))), replace=False)] = True
    return out


# ---------------------------------------------------------------- tuning
def _cv_one(method, task, params, X, y, tr, va, clip):
    est = fit_model(method, task, params, X[tr], y[tr])
    return score(task, y[va], predict(est, task, X[va], clip))


def tune(method: str, task: str, X, y, splits, clip, subsample: float | None = None, seed: int = SEED):
    """Grid search over ``splits``; returns (best params, table of mean CV scores).
    With ``subsample`` the CV folds use a random fraction of their rows
    (seed 42) -- the final model is still trained on all training data."""
    if subsample:
        rng = np.random.default_rng(seed)
        splits = [(np.sort(rng.choice(tr, int(len(tr) * subsample), replace=False)),
                   np.sort(rng.choice(va, int(len(va) * subsample), replace=False))) for tr, va in splits]
    combos = grid(method, task)
    jobs = [(p, tr, va) for p in combos for tr, va in splits]
    if method in INTERNAL_PARALLEL:
        scores = [_cv_one(method, task, p, X, y, tr, va, clip) for p, tr, va in jobs]
    else:
        scores = Parallel(n_jobs=N_JOBS)(delayed(_cv_one)(method, task, p, X, y, tr, va, clip) for p, tr, va in jobs)
    s = np.array(scores).reshape(len(combos), len(splits)).mean(axis=1)
    table = pd.DataFrame({"params": [repr(p) for p in combos], "cv_score": s})
    # Scores tied up to floating-point noise (e.g. identical trees from
    # depth 12 and None, summed in thread order) resolve to the first grid
    # entry, so reruns pick the same parameters.
    return combos[int(np.argmax(np.round(s, 10)))], table


def _read_int(path: str) -> int | None:
    try:
        with open(path) as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None


class ResourceMonitor:
    """Measures a code block on the Pi: wall time, CPU time of this process
    and its children (joblib workers), mean and peak CPU utilisation (in
    cores), peak RSS of the process tree, system-wide mean CPU %, SoC
    temperature (start/max/end) and the lowest CPU frequency seen (thermal
    throttling shows up as a drop below the nominal 2.4 GHz). Sampled every
    ``interval`` seconds in a background thread."""

    TEMP = "/sys/class/thermal/thermal_zone0/temp"
    FREQ = "/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq"

    def __init__(self, interval: float = 0.25):
        self.interval = interval
        self._stop = threading.Event()
        self._cpu: dict[int, float] = {}    # pid -> last seen user+system seconds
        self._cpu0: dict[int, float] = {}   # pid -> seconds when first seen
        self.peak_rss_mb = 0.0
        self.peak_cores = None  # None if the block was shorter than one interval
        self.max_temp_c = None
        self.min_freq_mhz = None

    def _tree(self):
        me = psutil.Process()
        return [me] + me.children(recursive=True)

    def _sample(self) -> float:
        rss, total = 0, 0.0
        for p in self._tree():
            try:
                with p.oneshot():
                    rss += p.memory_info().rss
                    c = p.cpu_times()
                    t = c.user + c.system
            except psutil.Error:
                continue
            # a child started inside the block counts from zero
            self._cpu0.setdefault(p.pid, self._own0 if p.pid == self._me else 0.0)
            self._cpu[p.pid] = t
        self.peak_rss_mb = max(self.peak_rss_mb, rss / 2**20)
        temp, freq = _read_int(self.TEMP), _read_int(self.FREQ)
        if temp is not None:
            self.max_temp_c = max(self.max_temp_c or 0, temp / 1000)
        if freq is not None:
            self.min_freq_mhz = min(self.min_freq_mhz or 1e9, freq / 1000)
        return sum(self._cpu[p] - self._cpu0[p] for p in self._cpu)

    def _sample_rss_only(self) -> float:
        rss = 0
        for p in self._tree():
            try:
                rss += p.memory_info().rss
            except psutil.Error:
                pass
        return rss / 2**20

    def _run(self):
        prev_t, prev_cpu = time.perf_counter(), 0.0
        while not self._stop.wait(self.interval):
            cpu = self._sample()
            now = time.perf_counter()
            self.peak_cores = max(self.peak_cores or 0.0, (cpu - prev_cpu) / (now - prev_t))
            prev_t, prev_cpu = now, cpu

    def __enter__(self):
        me = psutil.Process()
        self._me = me.pid
        c = me.cpu_times()
        self._own0 = c.user + c.system
        # children existing before the block: count only their CPU time from now on
        for ch in me.children(recursive=True):
            try:
                cc = ch.cpu_times()
                self._cpu0[ch.pid] = cc.user + cc.system
            except psutil.Error:
                pass
        t = _read_int(self.TEMP)
        self.temp_start_c = self.max_temp_c = t / 1000 if t is not None else None
        self.rss_start_mb = self._sample_rss_only()
        psutil.cpu_percent(interval=None)
        self._t0 = time.perf_counter()
        self._t = threading.Thread(target=self._run, daemon=True)
        self._t.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._t.join()
        self.cpu_seconds = self._sample()
        self.wall_seconds = time.perf_counter() - self._t0
        self.system_cpu_percent = psutil.cpu_percent(interval=None)
        t = _read_int(self.TEMP)
        self.temp_end_c = t / 1000 if t is not None else None
        if self.temp_end_c is not None:
            self.max_temp_c = max(self.max_temp_c or 0, self.temp_end_c)
        self.mean_cores = self.cpu_seconds / self.wall_seconds if self.wall_seconds > 0 else 0.0

    def record(self, prefix: str) -> dict:
        return {f"{prefix}_wall_s": round(self.wall_seconds, 3), f"{prefix}_cpu_s": round(self.cpu_seconds, 2),
                f"{prefix}_mean_cores": round(self.mean_cores, 2),
                f"{prefix}_peak_cores": None if self.peak_cores is None else round(self.peak_cores, 2),
                f"{prefix}_peak_rss_mb": round(self.peak_rss_mb, 1),
                f"{prefix}_rss_start_mb": round(self.rss_start_mb, 1),
                f"{prefix}_peak_rss_increase_mb": round(self.peak_rss_mb - self.rss_start_mb, 1),
                f"{prefix}_system_cpu_pct": round(self.system_cpu_percent, 1),
                f"{prefix}_temp_start_c": self.temp_start_c, f"{prefix}_temp_max_c": self.max_temp_c,
                f"{prefix}_temp_end_c": self.temp_end_c, f"{prefix}_min_freq_mhz": self.min_freq_mhz}
