"""T1: per UE and 60 s window, mean throughput and peak throughput (max 1 s throughput).

Estimates use only what the stream delivers: the per-interval summaries.
  mean:  average of the interval means (exact when p divides 60, PREREGISTRATION 4 note)
  peak:  max of the interval maxima if 'max' is reported, otherwise max of the interval means
"""

from ..prereg import WINDOW_S


def ground_truth(x):
    n_ue, T = x.shape
    xw = x.reshape(n_ue, T // WINDOW_S, WINDOW_S)
    return xw.mean(axis=2), xw.max(axis=2)


def estimate(summ, stats):
    n_ue, T = summ["mean"].shape
    W = T // WINDOW_S
    mean_est = summ["mean"].reshape(n_ue, W, WINDOW_S).mean(axis=2)
    peak_src = summ["max"] if "max" in stats else summ["mean"]
    peak_est = peak_src.reshape(n_ue, W, WINDOW_S).max(axis=2)
    return mean_est, peak_est
