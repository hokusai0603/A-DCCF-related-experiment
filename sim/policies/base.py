"""What a policy delivers to A-DCCF and what it costs."""
from dataclasses import dataclass, field

import numpy as np

from ..prereg import SUMMARIES


@dataclass
class Collection:
    """One collection configuration applied to one run.

    p_win        (n_ue, n_windows) reporting period in force in each 60 s window
    stats        statistics carried per report; "raw" = full 1 s measurement (10 fields)
    n_notif      (n_ue,) notifications per subscription
    n_reports    (n_ue,) reports per subscription
    n_subs       producer subscriptions (B0 = 2, one per consumer; otherwise 1)
    max_delay_s  max age of a measurement when its notification is sent (k x p)
    """
    family: str
    params: dict
    p_win: np.ndarray
    stats: tuple
    n_notif: np.ndarray
    n_reports: np.ndarray
    n_subs: int
    max_delay_s: float
    extra: dict = field(default_factory=dict)

    @property
    def raw(self):
        return self.stats == ("raw",)

    @property
    def n_stat(self):
        return None if self.raw else len(self.stats)

    @property
    def view_stats(self):
        """Statistics the consumers can use (a raw 1 s report = its own mean/max, var 0)."""
        return ("mean",) if self.raw else self.stats

    @property
    def label(self):
        if not self.params:
            return self.family
        return self.family + "(" + ",".join(f"{k}={v}" for k, v in self.params.items()) + ")"

    def cost(self, cm):
        """Producer -> A-DCCF bytes and notifications, summed over UEs and subscriptions."""
        return cost_from_counts(self.n_notif, self.n_reports, self.n_subs, self.n_stat, cm)


def cost_from_counts(n_notif, n_reports, n_subs, n_stat, cm):
    """n_notif, n_reports: per-UE counts of one subscription; n_stat None = raw measurement."""
    n_stat = cm.n_stat_raw if n_stat is None else n_stat
    uniq = float(np.sum(n_reports))
    notif, reps = float(np.sum(n_notif)) * n_subs, uniq * n_subs
    up = cm.bytes(notif, reps, n_stat)
    return {
        "notifications": notif,
        "reports": reps,
        "bytes_up": up,
        # A-DCCF -> consumers: both consumers receive the stream as it arrived; under B0 each
        # consumer's own subscription is forwarded once.
        "bytes_down": up if n_subs == 2 else 2 * up,
        # A-ADRF storage: one copy of each unique report (report part of the cost model)
        "storage_bytes": uniq * cm.report_bytes(n_stat),
        "duplicate_ratio": 1.0 - uniq / reps if reps else 0.0,
    }


def stats_of(summary):
    return SUMMARIES[summary]


def notifications_for_runs(p_win, k_of_p):
    """Batch consecutive reports of the same period; a batch never mixes periods.

    k_of_p maps a period to the batch size used while that period is in force.
    Returns (n_notif, n_reports, max_delay) per UE / overall.
    """
    n_ue, W = p_win.shape
    n_notif = np.zeros(n_ue, dtype=np.int64)
    n_rep = np.zeros(n_ue, dtype=np.int64)
    max_delay = 0
    for u in range(n_ue):
        w = 0
        while w < W:
            p = int(p_win[u, w])
            w2 = w
            while w2 < W and p_win[u, w2] == p:
                w2 += 1
            reps = (w2 - w) * (60 // p)
            k = k_of_p(p)
            n_notif[u] += -(-reps // k)
            n_rep[u] += reps
            max_delay = max(max_delay, min(k, reps) * p)
            w = w2
    return n_notif, n_rep, max_delay
