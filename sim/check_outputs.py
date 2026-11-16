#!/usr/bin/env python3
"""Independent cross-check of a run_grid output directory.

Recomputes a few numbers directly from the traces, without the run_grid cache or the policy
classes, and compares them with <out>/tables/configs.csv and regret.csv:
  - B1 / B2 / B0 bytes from the closed-form cost model
  - T1 p95 of mean-only B2 and of B1 straight from the traces
  - regret at every eps from configs.csv with a brute-force search
Usage: python3 -m sim.check_outputs <out> [--seeds 1,2,3]
"""
import argparse
import csv
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent


def load_x(run):
    d = ROOT / "traces" / run
    att = json.loads((d / "FINAL.json").read_text())["final_attempt"]
    df = pd.read_parquet(d / f"a{att}" / "upf_1s.parquet")
    df = df[(df.k >= 0) & (df.k < 1800)]
    return df.pivot(index="supi", columns="k", values="ul_bytes").sort_index().to_numpy(float) * 8


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--seeds", default="1,2,3")
    a = ap.parse_args()
    seeds = [int(s) for s in a.seeds.split(",")]
    rows = list(csv.DictReader(open(a.out / "tables" / "configs.csv")))
    by = {(r["scenario"], r["config"]): r for r in rows}
    prm = json.loads((ROOT / "cost" / "sim_params.json").read_text())
    A, R, S_, BRAW = prm["a"], prm["r"], prm["s"], prm["b_raw"]
    n_ue, T, nrun = 46, 1800, len(seeds)
    bad = 0

    def check(name, got, want, tol=1e-6):
        nonlocal bad
        ok = math.isclose(got, want, rel_tol=tol, abs_tol=1e-9)
        bad += not ok
        print(("OK  " if ok else "FAIL"), name, got, want)

    for S in ("S1", "S2", "S3", "S4"):
        check(f"{S} B1 bytes", float(by[(S, "B1")]["cost_main"]), nrun * n_ue * T * (A + BRAW))
        check(f"{S} B0 bytes", float(by[(S, "B0")]["cost_main"]), 2 * nrun * n_ue * T * (A + BRAW))
        for p, k, sm, ns in ((10, 5, "mean+max", 2), (60, 1, "mean", 1), (1, 10, "mean+max+var", 3)):
            reps = T // p
            want = nrun * n_ue * (math.ceil(reps / k) * A + reps * (R + ns * S_))
            check(f"{S} B2 p{p} k{k} {sm} bytes", float(by[(S, f"B2_p{p}_k{k}_{sm}")]["cost_main"]), want)
        xs = [load_x(f"{S}-seed{n}") for n in seeds]
        for p in (5, 30, 60):
            errs = []
            for x in xs:
                w = x.reshape(n_ue, 30, 60)
                gt = w.max(axis=2)
                est = x.reshape(n_ue, 30, 60 // p, p).mean(axis=3).max(axis=2)
                errs.append(np.abs(est - gt) / np.maximum(gt, 1e4))
            check(f"{S} T1 peak p95 B2 p{p} mean", float(by[(S, f"B2_p{p}_k1_mean")]["t1_peak_p95"]),
                  float(np.percentile(np.concatenate([e.ravel() for e in errs]), 95)))
        check(f"{S} T1 B1 peak p95", float(by[(S, "B1")]["t1_peak_p95"]), 0.0)
        check(f"{S} T2 B1 err", float(by[(S, "B1")]["t2_err"]), 0.0)

    # brute-force regret from configs.csv
    reg = list(csv.DictReader(open(a.out / "tables" / "regret.csv")))
    scen = ("S1", "S2", "S3", "S4")
    for rr in reg:
        variant, T_, eps = rr["variant"], rr["consumer"], float(rr["eps"])
        cfgs = sorted({r["config"] for r in rows if r["family"] == "B2"})

        def ok(r):
            if T_ == "T1":
                return (r["t1_fresh"] == "True" and float(r["t1_mean_p95"]) <= eps
                        and float(r["t1_peak_p95"]) <= eps)
            return float(r["t2_err"]) <= eps

        cstar = []
        for Sx in scen:
            c = [float(by[(Sx, c)][f"cost_{variant}"]) for c in cfgs if ok(by[(Sx, c)])]
            cstar.append(min(c) if c else None)
        stat = [sum(float(by[(Sx, c)][f"cost_{variant}"]) for Sx in scen) for c in cfgs
                if all(ok(by[(Sx, c)]) for Sx in scen)]
        if None in cstar or not stat:
            want = None
        else:
            want = min(stat) / sum(cstar) - 1
        got = rr["regret_static"]
        name = f"regret {variant} {T_} eps={eps}"
        if want is None:
            okk = got == ""
            bad += not okk
            print("OK  " if okk else "FAIL", name, got or None, None)
        else:
            check(name, float(got), want)
    print("FAILURES:", bad)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
