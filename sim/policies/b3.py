"""B3: B2 + rule-based adaptation of p (PREREGISTRATION 4).

Every 60 s the CV of the last 60 s is compared with the thresholds: CV > theta_high -> one
level finer, CV < theta_low -> one level coarser. Levels {1, 2, 5, 10, 30, 60} s, summary
fixed to mean+max, k = the largest batch that meets the 60 s freshness limit.

Choices the preregistration leaves open (sim/README.md):
  cv_source  "producer": CV = std/mean of the producer's 60 one-second values (default; the
             producer has them, and with mean+max reports A-DCCF cannot compute a CV at p = 60)
             "received": CV of the interval means A-DCCF received in the last window
  p0         period in the first window (default 1 s = start at full resolution)
  k_mode     "max": k = floor(60 / p) (default), "grid": largest k in {1, 5, 10} with k p <= 60
  CV of an all-zero window is 0.
"""
import numpy as np

from ..prereg import B2_K, B3_LEVELS, B3_SUMMARY, SUMMARIES, T1_FRESHNESS_S, WINDOW_S, b3_theta_pairs
from .base import Collection, notifications_for_runs

DEFAULTS = {"cv_source": "producer", "p0": 1, "k_mode": "max"}


def _cv(v, axis=-1):
    m = v.mean(axis=axis)
    sd = v.std(axis=axis)
    return np.where(m > 0, sd / np.where(m > 0, m, 1.0), 0.0)


def b3_schedule(x, theta_high, theta_low, cv_source="producer", p0=1):
    """Return p_win (n_ue, n_windows) and the CV used for each decision (n_ue, n_windows)."""
    n_ue, T = x.shape
    W = T // WINDOW_S
    levels = np.array(B3_LEVELS)
    idx = np.full(n_ue, int(np.flatnonzero(levels == p0)[0]))
    p_win = np.empty((n_ue, W), dtype=np.int64)
    cvs = np.full((n_ue, W), np.nan)
    xw = x.reshape(n_ue, W, WINDOW_S)
    for w in range(W):
        p_win[:, w] = levels[idx]
        if cv_source == "producer":
            cv = _cv(xw[:, w, :])
        elif cv_source == "received":
            cv = np.empty(n_ue)
            for u in range(n_ue):
                p = int(p_win[u, w])
                cv[u] = _cv(xw[u, w, :].reshape(WINDOW_S // p, p).mean(axis=1))
        else:
            raise ValueError(cv_source)
        cvs[:, w] = cv
        idx = np.where(cv > theta_high, np.maximum(idx - 1, 0), idx)
        idx = np.where(cv < theta_low, np.minimum(idx + 1, len(levels) - 1), idx)
    return p_win, cvs


def k_for(p, k_mode="max"):
    if k_mode == "max":
        return max(1, T1_FRESHNESS_S // p)
    if k_mode == "grid":
        ok = [k for k in B2_K if k * p <= T1_FRESHNESS_S]
        return max(ok) if ok else 1
    raise ValueError(k_mode)


def b3(x, theta_high, theta_low, cv_source="producer", p0=1, k_mode="max"):
    p_win, cvs = b3_schedule(x, theta_high, theta_low, cv_source, p0)
    n_notif, n_rep, max_delay = notifications_for_runs(p_win, lambda p: k_for(p, k_mode))
    params = {"theta_high": theta_high, "theta_low": theta_low}
    opts = {"cv_source": cv_source, "p0": p0, "k_mode": k_mode}
    if opts != DEFAULTS:
        params.update(opts)
    return Collection("B3", params, p_win, SUMMARIES[B3_SUMMARY], n_notif, n_rep, n_subs=1,
                      max_delay_s=max_delay, extra={"cv": cvs})


def b3_grid():
    return b3_theta_pairs()
