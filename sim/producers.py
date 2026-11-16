"""Ground truth loading and producer-side computations.

A producer is one UE's 1 s UL throughput series at the UPF (traces/README.md):
x[u, j] = ul_bytes[u, j] * 8  [bit/s] for second j = 0..1799 on the UE's own grid.

A collection *stream* is described by `p_win`, an int array (n_ue, n_windows) giving the
reporting period used inside each 60 s analysis window. All allowed periods divide 60, so
report intervals never cross a window boundary. B0/B1 are p = 1 raw, B2 is a constant p, B3
changes p per window and per UE.
"""
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from .prereg import DURATION_S, WINDOW_S

ROOT = Path(__file__).resolve().parent.parent
TRACES = ROOT / "traces"


@dataclass
class Run:
    name: str               # e.g. "S2-seed1"
    scenario: str
    seed: int
    supis: list
    x: np.ndarray           # (n_ue, T) float64 bit/s
    missing: np.ndarray     # (n_ue, T) bool
    valid: bool
    attempt: int
    meta: dict = field(default_factory=dict)

    @property
    def n_ue(self):
        return self.x.shape[0]

    @property
    def T(self):
        return self.x.shape[1]

    def subset(self, supis):
        idx = [self.supis.index(s) for s in supis]
        return Run(self.name, self.scenario, self.seed, list(supis), self.x[idx], self.missing[idx],
                   self.valid, self.attempt, self.meta)


def pivot_trace(df, T=DURATION_S):
    """upf_1s.parquet rows -> (supis, x[bit/s], missing). Rows with k outside [0, T) are ignored."""
    df = df[(df["k"] >= 0) & (df["k"] < T)]
    supis = sorted(df["supi"].unique())
    x = df.pivot(index="supi", columns="k", values="ul_bytes").reindex(index=supis, columns=range(T))
    miss = df.pivot(index="supi", columns="k", values="missing").reindex(index=supis, columns=range(T))
    missing = miss.isna().to_numpy() | (miss.to_numpy(dtype=object) == True)  # noqa: E712
    xb = x.fillna(0).to_numpy(dtype=np.float64) * 8.0
    return supis, xb, missing


def load_run(name, traces=TRACES):
    d = Path(traces) / name
    final = json.loads((d / "FINAL.json").read_text())
    a = d / f"a{final['final_attempt']}"
    meta = json.loads((a / "meta.json").read_text())
    supis, x, missing = pivot_trace(pd.read_parquet(a / "upf_1s.parquet"), meta.get("duration_s", DURATION_S))
    sc, seed = name.split("-seed")
    return Run(name, sc, int(seed), supis, x, missing, bool(final["valid"]), int(final["final_attempt"]), meta)


def run_names(scenarios, seeds):
    return [f"{s}-seed{n}" for s in scenarios for n in seeds]


# ----------------------------------------------------------------------------------------------
# Streams


def constant_p_win(n_ue, T, p):
    assert WINDOW_S % p == 0, p
    return np.full((n_ue, T // WINDOW_S), p, dtype=np.int64)


def interval_index(p_win, T):
    """Per second j: id of the report interval containing j, unique within a UE, ascending in time.

    Returns (start, end) arrays (n_ue, T): interval [start, end) containing each second.
    """
    n_ue, W = p_win.shape
    assert W * WINDOW_S == T
    p_sec = np.repeat(p_win, WINDOW_S, axis=1)               # (n_ue, T) period in force
    j = np.arange(T)[None, :]
    start = (j // p_sec) * p_sec                              # p | 60 so windows align
    end = start + p_sec
    return start, end


def summaries(x, p_win):
    """Producer-side summaries broadcast to every second of their interval.

    Returns dict of (n_ue, T) arrays: mean, max, var (population variance of the 1 s values),
    plus 'start'/'end' of the interval. For p = 1, mean = x, max = x, var = 0.
    """
    n_ue, T = x.shape
    start, end = interval_index(p_win, T)
    out = {"mean": np.empty_like(x), "max": np.empty_like(x), "var": np.empty_like(x),
           "start": start, "end": end}
    for p in np.unique(p_win):
        p = int(p)
        mask = np.repeat(p_win == p, WINDOW_S, axis=1)       # seconds whose interval has period p
        xr = x.reshape(n_ue, T // p, p)
        m = xr.mean(axis=2)
        mx = xr.max(axis=2)
        v = xr.var(axis=2)
        for key, val in (("mean", m), ("max", mx), ("var", v)):
            out[key][mask] = np.repeat(val, p, axis=1)[mask]
    return out


def n_reports(p_win):
    """Reports per UE: sum over windows of 60/p."""
    return (WINDOW_S // p_win).sum(axis=1)
