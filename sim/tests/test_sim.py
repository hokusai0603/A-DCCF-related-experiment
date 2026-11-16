"""Unit tests for the P3 simulator. Run from ~/Research-data-collection:  python3 -m pytest sim/tests

Fixture: tests/data/fixture_240s.parquet = the first 240 s (4 windows) of three real P2 UEs:
  0  imsi-...206 @ S2-seed1   bursty on/off (40 % of seconds on)
  1  imsi-...001 @ S1-seed1   constant rate
  2  imsi-...003 @ S3-seed1   idle (all zero)
"""
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from sim import metrics
from sim.consumers import t1, t2
from sim.cost_model import CostModel
from sim.policies import b0, b1, b2, b2_grid, b3, b3_grid, b3_schedule
from sim.policies.base import notifications_for_runs
from sim.policies.b3 import k_for
from sim.prereg import SUMMARIES
from sim.producers import TRACES, constant_p_win, load_run, pivot_trace, summaries

DATA = Path(__file__).parent / "data" / "fixture_240s.parquet"
T = 240


@pytest.fixture(scope="module")
def fx():
    supis, x, missing = pivot_trace(pd.read_parquet(DATA), T=T)
    order = [next(i for i, s in enumerate(supis) if s.endswith(tag)) for tag in ("S2-seed1", "S1-seed1", "S3-seed1")]
    return [supis[i] for i in order], x[order], missing[order]


@pytest.fixture(scope="module")
def cm():
    return CostModel.load()


# ---------------------------------------------------------------------------------------------
# fixture sanity


def test_fixture_shape(fx):
    supis, x, missing = fx
    assert x.shape == (3, T)
    assert not missing.any()
    assert supis[0].startswith("imsi-208930000000206@S2")
    assert (x[2] == 0).all() and (x[1] > 0).all()
    assert 0.3 < (x[0] > 0).mean() < 0.5
    # bit/s = bytes * 8
    raw = pd.read_parquet(DATA)
    v = raw[(raw.supi == supis[1]) & (raw.k == 7)].ul_bytes.iloc[0]
    assert x[1, 7] == v * 8


def test_pivot_marks_missing_cells():
    df = pd.DataFrame({"supi": ["a"] * 3, "k": [0, 1, 3], "ul_bytes": [1, 2, 4],
                       "missing": [False, True, False]})
    supis, x, missing = pivot_trace(df, T=4)
    assert missing.tolist() == [[False, True, True, False]]
    assert x.tolist() == [[8.0, 16.0, 0.0, 32.0]]


def test_load_real_run():
    r = load_run("S2-seed1", TRACES)
    assert r.x.shape == (46, 1800) and r.valid and r.attempt == 1
    assert not r.missing.any()
    sub = r.subset(r.supis[:6])
    assert sub.n_ue == 6 and np.array_equal(sub.x, r.x[:6])


# ---------------------------------------------------------------------------------------------
# cost model: the worked examples of cost/README.md section 7 (one UE, one minute)


def test_cost_examples(cm):
    assert cm.raw_notification_bytes == pytest.approx(556.7 + 488.93)
    assert 60 * cm.raw_notification_bytes == pytest.approx(62_738, abs=1)          # B1
    assert cm.bytes(6, 6, 2) == pytest.approx(5_118, abs=1)                         # p10 k1 mean+max
    assert cm.bytes(6, 60, 2) == pytest.approx(21_117, abs=1)                       # p1 k10 mean+max
    assert cm.bytes(1, 1, 2) == pytest.approx(853, abs=1)                           # p60 k1 mean+max
    assert cm.report_bytes(1) == pytest.approx(248.1 + 24.09)
    assert cm.report_bytes(3) == pytest.approx(248.1 + 3 * 24.09)
    assert CostModel.load("sensitivity").a == 884.8


def test_collection_costs(cm):
    n, TT = 2, 120
    c0, c1 = b0(n, TT), b1(n, TT)
    k0, k1 = c0.cost(cm), c1.cost(cm)
    assert k1["notifications"] == n * TT and k0["notifications"] == 2 * n * TT
    assert k1["bytes_up"] == pytest.approx(n * TT * cm.raw_notification_bytes)
    assert k0["bytes_up"] == pytest.approx(2 * k1["bytes_up"])
    assert k0["duplicate_ratio"] == 0.5 and k1["duplicate_ratio"] == 0.0
    assert k0["storage_bytes"] == k1["storage_bytes"] == pytest.approx(n * TT * 488.93)
    # B2 p=10 k=5 mean+max over 120 s: 12 reports, ceil(12/5) = 3 notifications per UE
    c = b2(n, TT, 10, 5, "mean+max")
    assert c.n_reports.tolist() == [12, 12] and c.n_notif.tolist() == [3, 3]
    assert c.cost(cm)["bytes_up"] == pytest.approx(n * (3 * cm.a + 12 * (cm.r + 2 * cm.s)))
    assert c.max_delay_s == 50


def test_b2_grid_and_freshness():
    g = b2_grid()
    assert len(g) == 45 and len(set(g)) == 45
    fresh = {(p, k) for p, k, _ in g if metrics.t1_fresh(k * p)}
    assert fresh == {(1, 1), (1, 5), (1, 10), (5, 1), (5, 5), (5, 10), (10, 1), (10, 5), (30, 1), (60, 1)}


# ---------------------------------------------------------------------------------------------
# producer summaries


@pytest.mark.parametrize("p", [1, 2, 5, 10, 30, 60])
def test_summaries_match_bruteforce(fx, p):
    _, x, _ = fx
    s = summaries(x, constant_p_win(3, T, p))
    for u in range(3):
        for i in range(T // p):
            seg = x[u, i * p:(i + 1) * p]
            for j in range(i * p, (i + 1) * p):
                assert s["mean"][u, j] == pytest.approx(seg.mean())
                assert s["max"][u, j] == seg.max()
                assert s["var"][u, j] == pytest.approx(seg.var())        # population variance
                assert (s["start"][u, j], s["end"][u, j]) == (i * p, (i + 1) * p)
    if p == 1:
        assert np.array_equal(s["mean"], x) and np.array_equal(s["max"], x) and not s["var"].any()


def test_summaries_mixed_periods(fx):
    _, x, _ = fx
    p_win = np.array([[1, 5, 60, 2]] * 3)
    s = summaries(x, p_win)
    assert s["mean"][0, 65] == pytest.approx(x[0, 65:70].mean())
    assert s["max"][1, 130] == x[1, 120:180].max()
    assert s["end"][0, 181] == 182 and s["start"][0, 181] == 180
    assert np.array_equal(s["mean"][:, :60], x[:, :60])


# ---------------------------------------------------------------------------------------------
# T1


def test_t1_ground_truth(fx):
    _, x, _ = fx
    gm, gp = t1.ground_truth(x)
    assert gm.shape == (3, 4)
    for u in range(3):
        for w in range(4):
            assert gm[u, w] == pytest.approx(x[u, 60 * w:60 * w + 60].mean())
            assert gp[u, w] == x[u, 60 * w:60 * w + 60].max()


@pytest.mark.parametrize("p", [1, 5, 10, 30, 60])
def test_t1_estimates(fx, p):
    _, x, _ = fx
    gm, gp = t1.ground_truth(x)
    s = summaries(x, constant_p_win(3, T, p))
    for summary, stats in SUMMARIES.items():
        me, pe = t1.estimate(s, stats)
        # mean is exact for every p that divides 60 (PREREGISTRATION 4 note)
        assert np.allclose(me, gm, rtol=1e-12)
        if "max" in stats:
            assert np.array_equal(pe, gp)            # max summary gives the exact peak
        else:
            manual = x.reshape(3, 4, 60 // p, p).mean(axis=3).max(axis=2)
            assert np.allclose(pe, manual)
            assert (pe <= gp + 1e-9).all()
    if p == 1:
        _, pe = t1.estimate(s, ("mean",))
        assert np.array_equal(pe, gp)


def test_t1_peak_error_bursty_vs_constant(fx):
    _, x, _ = fx
    gm, gp = t1.ground_truth(x)
    s = summaries(x, constant_p_win(3, T, 60))
    _, pe = t1.estimate(s, ("mean",))
    e = metrics.rel_err(pe, gp)
    assert (e[0] > 0.3).all()      # bursty UE: window mean is far below its peak
    assert (e[1] < 0.05).all()     # constant-rate UE: peak ~ mean
    assert (e[2] == 0).all()       # idle UE: 0 vs 0


def test_rel_err_floor_and_quantiles():
    e = metrics.rel_err([5_000, 19_000, 0, 1_000_000], [0, 20_000, 0, 900_000])
    assert e.tolist() == pytest.approx([0.5, 0.05, 0.0, 1 / 9])
    v = np.arange(101)
    assert metrics.p95(v) == 95.0 and metrics.median(v) == 50.0
    assert metrics.p95(np.array([[0.0] * 19 + [1.0]])) == pytest.approx(0.05)  # linear interpolation


def test_satisfies():
    acc = {"mean_p95": 0.0, "peak_p95": 0.04}
    assert metrics.satisfies("T1", acc, 0.05, 60)
    assert not metrics.satisfies("T1", acc, 0.05, 100)            # stale for T1
    assert not metrics.satisfies("T1", acc, 0.02, 10)
    assert metrics.satisfies("T2", {"err": -0.3}, 0.01, 1e9)        # T2 has no freshness limit
    assert not metrics.satisfies("T2", {"err": 0.06}, 0.05, 1)
    assert metrics.t2_error(1.1, 1.0) == pytest.approx(0.1)


# ---------------------------------------------------------------------------------------------
# B3


def test_b3_theta_pairs():
    pairs = b3_grid()
    assert len(pairs) == 8 and all(lo < hi for hi, lo in pairs)
    assert (0.2, 0.2) not in pairs and (1.0, 0.2) in pairs


def test_b3_constant_traffic_coarsens_one_level_per_window():
    x = np.full((1, 600), 5e5)
    p_win, cv = b3_schedule(x, 0.5, 0.1)
    assert p_win[0].tolist() == [1, 2, 5, 10, 30, 60, 60, 60, 60, 60]
    assert (cv == 0).all()


def test_b3_bursty_traffic_refines(fx):
    x = np.zeros((1, 300))
    x[0, ::10] = 1e6                                   # CV = 3
    p_win, cv = b3_schedule(x, 1.0, 0.2, p0=60)
    assert p_win[0].tolist() == [60, 30, 10, 5, 2]
    assert cv[0, 0] == pytest.approx(3.0)
    # between the thresholds the period stays
    y = np.tile([1.0, 2.0], 150)[None, :] * 1e5        # CV = 1/3
    assert b3_schedule(y, 0.5, 0.2, p0=10)[0][0].tolist() == [10] * 5
    # idle UE: CV = 0 -> coarsens
    assert b3_schedule(np.zeros((1, 180)), 0.2, 0.05)[0][0].tolist() == [1, 2, 5]


def test_b3_cv_uses_last_window_only():
    x = np.concatenate([np.full(60, 1e5), np.tile([0.0, 2e5], 30)])[None, :]
    p_win, cv = b3_schedule(x, 0.5, 0.1)
    assert cv[0].tolist() == pytest.approx([0.0, 1.0])
    assert p_win[0].tolist() == [1, 2]                 # decision at end of w0 applies to w1


def test_b3_received_cv():
    x = np.tile([0.0, 2e5], 60)[None, :]               # producer CV 1, but 2 s means are flat
    p_win, cv = b3_schedule(x, 0.5, 0.1, cv_source="received", p0=2)
    assert cv[0, 0] == 0.0 and p_win[0].tolist() == [2, 5]
    assert b3_schedule(x, 0.5, 0.1, cv_source="producer", p0=2)[1][0, 0] == pytest.approx(1.0)


def test_b3_batching(cm):
    assert [k_for(p) for p in (1, 2, 5, 10, 30, 60)] == [60, 30, 12, 6, 2, 1]
    assert [k_for(p, "grid") for p in (1, 2, 5, 10, 30, 60)] == [10, 10, 10, 5, 1, 1]
    x = np.full((1, 600), 5e5)
    c = b3(x, 0.5, 0.1)
    # one notification per window (k = 60/p), reports = sum 60/p
    assert c.n_notif.tolist() == [10]
    assert c.n_reports.tolist() == [60 + 30 + 12 + 6 + 2 + 1 * 5]
    assert c.max_delay_s == 60 and metrics.t1_fresh(c.max_delay_s)
    assert c.cost(cm)["bytes_up"] == pytest.approx(10 * cm.a + 115 * (cm.r + 2 * cm.s))
    g = b3(x, 0.5, 0.1, k_mode="grid")
    # periods 1,2,5,10,30,60x5 -> reports 60,30,12,6,2,5 -> notif ceil(60/10)+ceil(30/10)+
    # ceil(12/10)+ceil(6/5)+2+5 = 6+3+2+2+2+5
    assert g.n_notif.tolist() == [20] and g.max_delay_s <= 60
    assert g.params["k_mode"] == "grid" and "k_mode" not in c.params


def test_notifications_for_runs_never_mixes_periods():
    n, r, d = notifications_for_runs(np.array([[5, 5, 10]]), lambda p: 5)
    assert r.tolist() == [24 + 6] and n.tolist() == [5 + 2] and d == 50


def test_b3_t1_exact(fx):
    _, x, _ = fx
    c = b3(x, 0.5, 0.1)
    gm, gp = t1.ground_truth(x)
    me, pe = t1.estimate(summaries(x, c.p_win), c.view_stats)
    assert np.allclose(me, gm) and np.array_equal(pe, gp)


# ---------------------------------------------------------------------------------------------
# T2


def test_t2_instants_split_targets(fx):
    _, x, _ = fx
    ut = t2.instants(3, T, stride=1)
    assert ut[:, 1].min() == 60 and ut[:, 1].max() == T - 10
    assert len(ut) == 3 * (T - 10 - 60 + 1)
    train, test = t2.split_mask(ut[:, 1], T)
    cut = 0.7 * T
    assert (ut[train, 1] + 10 <= cut).all() and (ut[test, 1] >= cut).all()
    assert not (train & test).any()
    y = t2.targets(x, ut)
    for i in (0, 57, len(ut) - 1):
        u, t = ut[i]
        assert y[i] == pytest.approx(x[u, t:t + 10].mean())
    ut5 = t2.instants(3, T, stride=5)
    assert ut5[ut5[:, 0] == 2, 1].min() == 62


def test_t2_features_compact_and_age(fx):
    _, x, _ = fx
    p_win = constant_p_win(3, T, 10)
    s = summaries(x, p_win)
    ut = np.array([[0, 125], [1, 120], [0, 60]])
    X = t2.features(s, ("mean", "max"), ut, p_win)
    assert X.shape == (3, 6 + 6 + 1)
    # t = 125 -> last complete interval ends at b = 120; history [60, 120)
    assert X[0, :6] * 1e3 == pytest.approx(x[0, 60:120].reshape(6, 10).mean(axis=1))
    assert X[0, 6:12] * 1e3 == pytest.approx(x[0, 60:120].reshape(6, 10).max(axis=1))
    assert X[0, -1] == 5 and X[1, -1] == 0 and X[2, -1] == 0
    # raw p = 1: features are the previous 60 one-second values
    s1 = summaries(x, constant_p_win(3, T, 1))
    X1 = t2.features(s1, ("mean",), ut, constant_p_win(3, T, 1))
    assert X1[0, :60] * 1e3 == pytest.approx(x[0, 65:125])


def test_t2_per_second_equals_compact_information(fx):
    _, x, _ = fx
    p_win = constant_p_win(3, T, 30)
    s = summaries(x, p_win)
    ut = t2.instants(3, T)
    Xc = t2.features(s, ("mean",), ut, p_win, "compact")
    Xs = t2.features(s, ("mean",), ut, p_win, "per_second")
    assert np.array_equal(np.repeat(Xc[:, :2], 30, axis=1), Xs[:, :60])
    assert np.array_equal(Xc[:, -1], Xs[:, -1])
    assert set(Xc[:, -1]) == set(range(30))            # every phase relative to the grid


def test_t2_features_variable_period(fx):
    _, x, _ = fx
    p_win = np.array([[1, 60, 5, 5]] * 3)
    s = summaries(x, p_win)
    ut = np.array([[0, 130], [0, 119], [0, 183]])
    X = t2.features(s, ("mean",), ut, p_win)
    assert X.shape == (3, 61)
    # t = 130: window 2 has p = 5 -> b = 130, history [70,130): 50 s of the one 60 s mean of
    # [60,120), then two 5 s means
    assert X[0, -1] == 0
    assert np.allclose(X[0, :50] * 1e3, x[0, 60:120].mean())
    assert np.allclose(X[0, 50:55] * 1e3, x[0, 120:125].mean())
    assert np.allclose(X[0, 55:60] * 1e3, x[0, 125:130].mean())
    # t = 119 -> b = 60, history = raw seconds 0..59
    assert X[1, :60] * 1e3 == pytest.approx(x[0, 0:60]) and X[1, -1] == 59
    # t = 183 -> b = 180 (end of the 60 s interval)
    assert X[2, -1] == 3


def test_t2_evaluate_full_equals_p1_summaries(fx):
    _, x, _ = fx
    s = summaries(x, constant_p_win(3, T, 1))
    full = t2.evaluate(x, s, ("mean",), constant_p_win(3, T, 1))
    mm = t2.evaluate(x, s, ("mean", "max"), constant_p_win(3, T, 1))
    assert full["n_features"] == 61 and mm["n_features"] == 121
    # max == mean at p = 1: same information, but the duplicated columns change the order in
    # which the tree builder visits features, so ties between features break differently.
    # This is the T2 noise floor of the preregistered model, not an error in the features.
    assert full["mae"] == pytest.approx(mm["mae"], rel=0.02)
    # B2 p = 1 'mean' is exactly the full-data model
    b2m = t2.evaluate(x, s, b2(3, T, 1, 1, "mean").view_stats, constant_p_win(3, T, 1))
    assert b2m["mae"] == full["mae"]
    assert full["n_test"] == 3 * (T - 10 - math.ceil(0.7 * T) + 1)
    again = t2.evaluate(x, s, ("mean",), constant_p_win(3, T, 1))
    assert again["mae"] == full["mae"]                          # random_state = 0 -> deterministic


# ---------------------------------------------------------------------------------------------
# regret and other aggregates


def _ok(flag):
    return lambda eps: flag


def test_regret_toy():
    S = ("S1", "S2")
    table = {
        "cheap":  {"S1": (10, _ok(True)), "S2": (10, _ok(False))},
        "mid":    {"S1": (20, _ok(False)), "S2": (20, _ok(True))},
        "dear":   {"S1": (50, _ok(True)), "S2": (50, _ok(True))},
    }
    r = metrics.regret(table, S, 0.05)
    assert r["c_star"] == {"S1": ("cheap", 10), "S2": ("mid", 20)}
    assert r["c_static"] == ("dear", 100) and r["regret"] == pytest.approx(100 / 30 - 1)
    del table["dear"]
    r = metrics.regret(table, S, 0.05)
    assert r["no_static"] and r["regret"] is None
    fam = {"x": {"S1": (12, _ok(True)), "S2": (30, _ok(True))},
           "y": {"S1": (5, _ok(True)), "S2": (5, _ok(False))}}
    b = metrics.regret_of_family(fam, 30, S, 0.05)
    assert b["best"] == ("x", 42) and b["regret"] == pytest.approx(0.4)
    assert metrics.regret_of_family({"y": fam["y"]}, 30, S, 0.05)["no_feasible"]


def test_regret_eps_dependence():
    S = ("S1",)
    table = {"a": {"S1": (1, lambda e: e >= 0.1)}, "b": {"S1": (3, lambda e: True)}}
    assert metrics.regret(table, S, 0.05)["c_star"]["S1"] == ("b", 3)
    assert metrics.regret(table, S, 0.10)["c_star"]["S1"] == ("a", 1)


def test_pareto_and_linreg():
    pts = [(1, 0.5), (2, 0.1), (3, 0.2), (4, 0.0), (1, 0.6)]
    assert metrics.pareto_front(pts) == [0, 1, 3]
    fit = metrics.linreg_r2([6, 26, 46], [12, 52, 92])
    assert fit["r2"] == pytest.approx(1.0) and fit["slope"] == pytest.approx(2.0)
    assert metrics.linreg_r2([6, 26, 46], [0, 10, 0])["r2"] == pytest.approx(0.0)
