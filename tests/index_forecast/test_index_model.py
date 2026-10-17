"""Scores d at all limits of Table 1, class consistency (Table 2) and the
test cases / properties of I from task section 3.3."""

import numpy as np
import pandas as pd
import pytest

from iaq_index.config import INDICATORS, load_config
from iaq_index.index import compute_index_frame, dominance_shares, integral_index
from iaq_index.scores import class_from_score, class_from_value, deviation_score

CFG = load_config()


def d(name, x, cfg=CFG):
    return float(deviation_score([x], cfg.indicators[name], cfg)[0])


@pytest.mark.parametrize(
    "name,x,score,cls",
    [
        ("pm25", 15, 0, 0), ("pm25", 25, 25, 1), ("pm25", 37.5, 50, 2), ("pm25", 50, 75, 3), ("pm25", 62.5, 100, 4),
        ("pm25", 20, 12.5, 1), ("pm25", 1000, 100, 4), ("pm25", 0, 0, 0),
        ("pm10", 45, 0, 0), ("pm10", 50, 25, 1), ("pm10", 75, 50, 2), ("pm10", 100, 75, 3), ("pm10", 125, 100, 4),
        ("co2", 970, 0, 0), ("co2", 1220, 25, 1), ("co2", 1770, 50, 2), ("co2", 2000, 75, 3), ("co2", 2230, 100, 4),
        ("t", 21, 0, 0), ("t", 25.5, 0, 0), ("t", 20, 25, 1), ("t", 18, 50, 2), ("t", 16, 75, 3), ("t", 14, 100, 4),
        ("t", 26, 25, 1), ("t", 27, 50, 2), ("t", 28, 75, 3), ("t", 29, 100, 4), ("t", 23, 0, 0), ("t", 5, 100, 4),
        ("rh", 30, 0, 0), ("rh", 50, 0, 0), ("rh", 25, 25, 1), ("rh", 20, 50, 2), ("rh", 15, 75, 3), ("rh", 10, 100, 4),
        ("rh", 60, 25, 1), ("rh", 70, 50, 2), ("rh", 80, 75, 3), ("rh", 90, 100, 4),
    ],
)
def test_score_at_limits(name, x, score, cls):
    assert d(name, x) == pytest.approx(score, abs=1e-12)
    assert class_from_score([d(name, x)])[0] == cls
    assert class_from_value(x, CFG.indicators[name]) == cls


def test_breakpoints_from_config():
    assert CFG.indicators["co2"].high == (970, 1220, 1770, 2000, 2230)
    assert CFG.indicators["pm25"].high == (15, 25, 37.5, 50, 62.5)
    alt = CFG.with_overrides(co2_outdoor_ppm=400)
    assert alt.indicators["co2"].high == (950, 1200, 1750, 2000, 2250)
    t17 = CFG.with_overrides(t_low=[21, 20, 18, 17, 16])
    assert d("t", 17, t17) == 75 and d("t", 16, t17) == 100


@pytest.mark.parametrize("name", INDICATORS)
def test_score_class_equals_table_class_dense(name):
    """Class by score == class by Table 1 on a dense grid incl. every limit."""
    bp = CFG.indicators[name]
    pts = list(bp.high) + (list(bp.low) if bp.low else [])
    xs = np.unique(np.concatenate([np.linspace(0, 2500 if name == "co2" else 150, 20001), pts,
                                   np.array(pts) + 1e-9, np.array(pts) - 1e-9]))
    s = deviation_score(xs, bp, CFG)
    by_score = class_from_score(s)
    by_value = np.array([class_from_value(x, bp) for x in xs])
    assert (by_score == by_value).all()


def test_nan_propagates():
    assert np.isnan(deviation_score([np.nan], CFG.indicators["t"], CFG)[0])


@pytest.mark.parametrize(
    "q,delta,index,cls",
    [((60, 0, 0), 15, 45, 2), ((80, 0, 0), 0, 80, 4), ((0, 0, 0), 75, 0, 0), ((30, 30, 30), 45, 30, 2),
     ((50, 50, 0), 25, 100 / 3, 2)],
)
def test_index_cases(q, delta, index, cls):
    r = integral_index(np.array([q], dtype=float), CFG)
    assert r["Delta"][0] == pytest.approx(delta)
    assert r["I"][0] == pytest.approx(index)
    assert class_from_score(r["I"])[0] == cls


def test_case_50_50_0_mean():
    r = integral_index(np.array([[50, 50, 0]], dtype=float), CFG)
    assert r["Q_mean"][0] == pytest.approx(33.333, abs=1e-3)


@pytest.mark.parametrize("n_comp", [3, 4])
def test_index_properties_random(n_comp):
    rng = np.random.default_rng(42)
    Q = rng.uniform(0, 100, size=(100_000, n_comp))
    # include exact zeros and class limits
    Q[rng.random(Q.shape) < 0.1] = 0.0
    Q[rng.random(Q.shape) < 0.05] = rng.choice([25.0, 50.0, 75.0, 100.0], size=1)
    r = integral_index(Q, CFG)
    I, qmax = r["I"], r["Q_max"]
    assert (I <= qmax + 1e-12).all()
    worst_cls = class_from_score(qmax)
    assert (worst_cls - class_from_score(I) <= 1).all()
    assert np.allclose(I[qmax > 75], qmax[qmax > 75])
    assert ((I >= 0) & (I <= 100)).all()


def test_index_continuous_at_75():
    eps = np.array([1e-6, 1e-9])
    for other in ([0, 0], [40, 10], [75, 75]):
        lo = integral_index(np.array([[75 - e, *other] for e in eps]), CFG)["I"]
        at = integral_index(np.array([[75, *other]], dtype=float), CFG)["I"][0]
        hi = integral_index(np.array([[75 + e, *other] for e in eps]), CFG)["I"]
        assert np.allclose(lo, at, atol=1e-5) and np.allclose(hi, at, atol=1e-5)


def test_index_frame_requires_all_five():
    df = pd.DataFrame({"pm25": [30, np.nan], "pm10": [40, 40], "co2": [800, 800], "t": [22, 22], "rh": [40, 40]})
    f = compute_index_frame(df, CFG)
    assert f["I"].notna().tolist() == [True, False]
    assert f.loc[0, "Q_A"] == pytest.approx(25 * (1 + 5 / 12.5))


def test_four_component_variant():
    cfg4 = CFG.with_overrides(pm10_separate=True)
    df = pd.DataFrame({"pm25": [10.0], "pm10": [110.0], "co2": [800.0], "t": [22.0], "rh": [40.0]})
    f = compute_index_frame(df, cfg4)
    assert list(cfg4.components) == ["A", "P", "V", "M"]
    assert f.loc[0, "Q_A"] == 0 and f.loc[0, "Q_P"] == pytest.approx(85)
    assert f.loc[0, "Q_mean"] == pytest.approx(85 / 4)
    assert f.loc[0, "I"] == pytest.approx(85)


def test_dominance_shares():
    frame = pd.DataFrame({"Q_A": [60, 30, 0, 10], "Q_V": [59.5, 30, 0, 0], "Q_M": [0, 30, 0, 0]})
    r = integral_index(frame.to_numpy(dtype=float), CFG)
    frame = frame.assign(**r)
    s = dominance_shares(frame, CFG)
    assert s["N"] == 2  # I = 45 and 30 exceed 25; I(0,0,0)=0, I(10,0,0)=3.33 do not
    assert s["S_A"] == 1.0 and s["S_V"] == 1.0 and s["S_M"] == 0.5
    assert s["share_multi"] == 1.0
