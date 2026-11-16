"""T2: predict the mean throughput of the next 10 s from the past 60 s at the stream's resolution.

Implementation (sim/README.md):
- Prediction instants: t = 60 + (u mod stride) + stride * i, so instants are spread over all
  phases relative to the report grid; target window [t, t + 10) must lie inside the run.
- At instant t, A-DCCF has the reports whose interval ended at b <= t (latest such end).
  Features = the delivered statistics over [b - 60, b), one column per report interval
  ("compact", constant p) or one column per second ("per_second", piecewise constant; used
  when p varies, i.e. B3), plus age = t - b. Both carry the same information.
- One model per run, all UEs pooled. Train: instants whose target ends <= 0.7 T;
  test: instants with t >= 0.7 T (time split, no target overlap).
- Model: sklearn GradientBoostingRegressor(), defaults, random_state = 0. Unit kbit/s.
"""
import numpy as np
from sklearn.ensemble import GradientBoostingRegressor

from ..prereg import T2_HISTORY_S, T2_HORIZON_S, T2_RANDOM_STATE, T2_TRAIN_FRAC

DEFAULT_STRIDE = 1


def instants(n_ue, T, stride=DEFAULT_STRIDE):
    """List of (u, t) prediction instants."""
    out = []
    for u in range(n_ue):
        t = T2_HISTORY_S + (u % stride)
        while t + T2_HORIZON_S <= T:
            out.append((u, t))
            t += stride
    return np.array(out, dtype=np.int64)


def split_mask(t, T):
    cut = T2_TRAIN_FRAC * T
    train = t + T2_HORIZON_S <= cut
    test = t >= cut
    return train, test


def targets(x, ut):
    cs = np.concatenate([np.zeros((x.shape[0], 1)), np.cumsum(x, axis=1)], axis=1)
    u, t = ut[:, 0], ut[:, 1]
    return (cs[u, t + T2_HORIZON_S] - cs[u, t]) / T2_HORIZON_S


def features(summ, stats, ut, p_win=None, repr_="auto"):
    """Feature matrix for the instants ut given the delivered summaries."""
    start, end = summ["start"], summ["end"]
    u, t = ut[:, 0], ut[:, 1]
    # latest interval end <= t: the interval containing second t - 1 ends at t or later;
    # if it ends after t it is still open, take the end of the one before it.
    e = end[u, t - 1]
    b = np.where(e <= t, e, start[u, t - 1])
    age = (t - b).astype(np.float64)
    if repr_ == "auto":
        const = p_win is not None and np.all(p_win == p_win.flat[0])
        repr_ = "compact" if const else "per_second"
    if repr_ == "compact":
        p = int(p_win.flat[0])
        cols = b[:, None] - T2_HISTORY_S + p * np.arange(T2_HISTORY_S // p)[None, :]
    else:
        cols = b[:, None] - T2_HISTORY_S + np.arange(T2_HISTORY_S)[None, :]
    assert cols.min() >= 0
    blocks = [summ[s][u[:, None], cols] / 1e3 for s in stats]   # kbit/s ('var' in (kbit/s)^2 *1e3,
    return np.concatenate(blocks + [age[:, None]], axis=1)      # scale is irrelevant for trees)


def fit_predict(X, y, train, test):
    m = GradientBoostingRegressor(random_state=T2_RANDOM_STATE)
    m.fit(X[train], y[train])
    return m.predict(X[test])


def evaluate(x, summ, stats, p_win, stride=DEFAULT_STRIDE, repr_="auto"):
    """Return dict with test MAE (kbit/s) and the per-instant absolute errors."""
    n_ue, T = x.shape
    ut = instants(n_ue, T, stride)
    y = targets(x, ut) / 1e3
    X = features(summ, stats, ut, p_win, repr_)
    train, test = split_mask(ut[:, 1], T)
    pred = fit_predict(X, y, train, test)
    ae = np.abs(pred - y[test])
    return {"mae": float(ae.mean()), "n_train": int(train.sum()), "n_test": int(test.sum()),
            "n_features": int(X.shape[1]), "abs_err": ae}
