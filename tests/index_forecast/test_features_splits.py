"""No feature leakage, the 24 + h gap, S2 home separation, identical
results on rerun with the same seed (task section 12)."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from iaq_index.config import INDICATORS, load_config
from iaq_index.features import add_targets, build_features, feature_columns, features_at, features_at_fast
from iaq_index.index import compute_index_frame

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "experiments" / "index_forecast"))
import models  # noqa: E402

CFG = load_config()
COMPS = [f"Q_{c}" for c in CFG.components]


def synth_grid(n_homes=3, hours=400, seed=0, missing=0.03):
    rng = np.random.default_rng(seed)
    parts = []
    for i in range(n_homes):
        t = pd.date_range("2024-03-25", periods=hours + 50 * i, freq="1h")
        n = len(t)
        df = pd.DataFrame({"home": f"H{i}", "time": t,
                           "pm25": rng.gamma(2, 8, n), "pm10": None, "co2": rng.normal(900, 250, n),
                           "t": rng.normal(22, 2, n), "rh": rng.normal(45, 10, n)})
        df["pm10"] = df.pm25 * rng.uniform(1.0, 1.3, n)
        for x in INDICATORS:
            df.loc[rng.random(n) < missing, x] = np.nan
        parts.append(df)
    g = pd.concat(parts, ignore_index=True)
    g["season"] = np.where(g.time.dt.month.isin([10, 11, 12, 1, 2, 3, 4]), "heating", "warm")
    return g


def with_index(g):
    return pd.concat([g.reset_index(drop=True), compute_index_frame(g.reset_index(drop=True), CFG)], axis=1)


def test_feature_count_and_no_nan():
    f = build_features(with_index(synth_grid()), COMPS)
    cols = feature_columns(COMPS)
    assert len(cols) == 5 + 60 + 5 + 4 + 4
    assert not f[cols].isna().any().any()


def test_no_feature_leakage_random_future_changes():
    """Changing values strictly after t must not change z(t)."""
    rng = np.random.default_rng(42)
    g = synth_grid()
    f0 = build_features(with_index(g), COMPS).set_index(["home", "time"])
    for _ in range(10):
        home = rng.choice(g.home.unique())
        times = g[g.home == home].time
        t_cut = times.iloc[rng.integers(30, len(times) - 30)]
        g2 = g.copy()
        fut = (g2.home == home) & (g2.time > t_cut)
        for x in INDICATORS:
            g2.loc[fut, x] = g2.loc[fut, x] * rng.uniform(0.2, 3.0) + rng.normal(0, 5)
        f1 = build_features(with_index(g2), COMPS).set_index(["home", "time"])
        past = f0.index[(f0.index.get_level_values(0) != home) | (f0.index.get_level_values(1) <= t_cut)]
        pd.testing.assert_frame_equal(f0.loc[past], f1.loc[past])


def test_features_at_matches_batch():
    gi = with_index(synth_grid(n_homes=1))
    f = build_features(gi, COMPS)
    for t in f.time.sample(20, random_state=1):
        one = features_at(gi, t, COMPS)
        assert one is not None
        np.testing.assert_allclose(one[feature_columns(COMPS)].to_numpy(float),
                                   f[f.time == t][feature_columns(COMPS)].to_numpy(float), rtol=1e-9, atol=1e-9)


def test_features_at_fast_matches_batch():
    gi = with_index(synth_grid(n_homes=1, missing=0.05))
    f = build_features(gi, COMPS).set_index("time")
    cols = feature_columns(COMPS)
    n_checked = 0
    for t in gi.time.iloc[30:400:3]:
        h = gi[(gi.time > t - pd.Timedelta(hours=24)) & (gi.time <= t)]
        row = gi[gi.time == t].iloc[0]
        z = features_at_fast(h.time.to_numpy(), h[INDICATORS].to_numpy(float), row[[*COMPS, "I"]].to_dict(), t,
                             int(row.season == "heating"), COMPS)
        if t in f.index:
            np.testing.assert_allclose(z, f.loc[t, cols].to_numpy(float), rtol=1e-9, atol=1e-9)
            n_checked += 1
        else:
            assert z is None
    assert n_checked > 50


def test_targets_by_timestamp():
    gi = with_index(synth_grid(n_homes=1, missing=0))
    tg = add_targets(gi[["home", "time", "I"]], [3], ["I"])
    assert tg["I__h3"].iloc[0] == gi["I"].iloc[3]
    assert np.isnan(tg["I__h3"].iloc[-1])
    assert tg["I__h3_lag24"].iloc[21] == gi["I"].iloc[0]


def _span(df):
    span = df.groupby("home").time.agg(["min", "max"])
    span["cut"] = span["min"] + 0.75 * (span["max"] - span["min"])
    return span


@pytest.mark.parametrize("h", [1, 3, 6])
def test_gap_24_plus_h(h):
    df = synth_grid(n_homes=4)
    span = _span(df)
    homes = sorted(df.home.unique())
    tr, te = models.split_masks(df, homes, homes, span, h)
    assert not (tr & te).any()
    for home in homes:
        m = df.home == home
        last_target = df.time[tr & m].max() + pd.Timedelta(hours=h)
        first_test = df.time[te & m].min()
        assert last_target < span.loc[home, "cut"]
        assert first_test >= span.loc[home, "cut"] + pd.Timedelta(hours=24 + h)
        # test features reach back 24 h: still after every training target
        assert first_test - pd.Timedelta(hours=24) >= last_target


def test_s2_no_test_homes_in_training():
    df = synth_grid(n_homes=10, hours=200)
    span = _span(df)
    homes = sorted(df.home.unique())
    groups = [sorted(g.tolist()) for g in np.array_split(np.random.default_rng(42).permutation(homes), 5)]
    assert sorted(sum(groups, [])) == homes
    for g in groups:
        train_homes = sorted(set(homes) - set(g))
        tr, te = models.split_masks(df, train_homes, g, span, 3)
        assert set(df.home[tr]).isdisjoint(g)
        assert set(df.home[te]) <= set(g)
        inner = models.inner_splits_s2(df[tr].reset_index(drop=True), 3)
        sub = df[tr].reset_index(drop=True)
        for a, b in inner:
            assert set(sub.home.iloc[a]).isdisjoint(set(sub.home.iloc[b]))


def test_time_series_split_is_forward():
    times = np.random.default_rng(0).permutation(pd.date_range("2024-01-01", periods=300, freq="1h").to_numpy())
    for a, b in models.inner_splits_s1(times):
        assert times[a].max() < times[b].min()


@pytest.mark.parametrize("method", models.METHODS)
def test_rerun_identical(method):
    """Same seed -> identical tuned parameters and predictions."""
    rng = np.random.default_rng(0)
    X = rng.normal(size=(400, 6)).astype(np.float32)
    y = np.clip(30 + 10 * X[:, 0] + rng.normal(size=400), 0, 100)
    yc = np.clip(np.ceil(y / 25), 0, 4).astype(int)
    splits = models.inner_splits_s1(np.arange(400))
    for task, target in (("reg", y), ("clf", yc)):
        res = []
        for _ in range(2):
            best, _t = models.tune(method, task, X, target, splits, (0, 100) if task == "reg" else None)
            est = models.fit_model(method, task, best, X, target)
            res.append((repr(best), est.predict(X)))
        assert res[0][0] == res[1][0]
        # RF/ET with n_jobs=4 sum the trees' outputs in thread-completion
        # order, so floating-point results can differ in the last ulp
        np.testing.assert_allclose(res[0][1], res[1][1], rtol=1e-12, atol=1e-12)
