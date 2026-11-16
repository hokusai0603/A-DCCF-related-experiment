#!/usr/bin/env python3
"""Parameter sweep of B0-B3 over the P2 traces (PREREGISTRATION 4-5).

Usage (from ~/Research-data-collection):

    setsid nohup python3 -m sim.run_grid --out results > results/run_grid.log 2>&1 &

Stages
  compute    per run: costs and T1 errors of every setting (one task per run), and one T2
             model per (run, feature representation). Every task writes its own file under
             <out>/cache/, finished tasks are skipped, so an interrupted sweep resumes.
  aggregate  pools seeds per scenario and writes the tables, criteria numbers and figures.

The analysis follows PREREGISTRATION.md; choices it leaves open are listed in sim/README.md.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "sim"

from sim import metrics                                       # noqa: E402
from sim.consumers import t1, t2                               # noqa: E402
from sim.cost_model import load_all                            # noqa: E402
from sim.policies import b0, b1, b2, b2_grid, b3, b3_grid      # noqa: E402
from sim.policies.base import cost_from_counts                 # noqa: E402
from sim.prereg import (EPS_MAIN, EPSILONS, H3_UE_COUNTS, SCENARIOS, SEEDS,  # noqa: E402
                        SUMMARIES)
from sim.producers import TRACES, load_run, run_names, summaries  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CONSUMERS = ("T1", "T2")


def log(msg):
    print(time.strftime("%Y-%m-%dT%H:%M:%S"), msg, flush=True)


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1, default=float))
    os.replace(tmp, path)


# ---------------------------------------------------------------------------------------------
# settings


def b3_opts(args):
    return {"cv_source": args.b3_cv_source, "p0": args.b3_p0, "k_mode": args.b3_k_mode}


def settings(args):
    """Ordered list of (config_id, family, params, t2_key)."""
    out = [("B0", "B0", {}, "full"), ("B1", "B1", {}, "full")]
    for p, k, sm in b2_grid():
        key = "full" if (p == 1 and sm == "mean") else f"B2_p{p}_{sm}"
        out.append((f"B2_p{p}_k{k}_{sm}", "B2", {"p": p, "k": k, "summary": sm}, key))
    for hi, lo in b3_grid():
        cid = f"B3_hi{hi}_lo{lo}"
        out.append((cid, "B3", {"theta_high": hi, "theta_low": lo}, cid))
    return out


def build(family, params, run, args):
    n, T = run.x.shape
    if family == "B0":
        return b0(n, T)
    if family == "B1":
        return b1(n, T)
    if family == "B2":
        return b2(n, T, params["p"], params["k"], params["summary"])
    if family == "B3":
        return b3(run.x, params["theta_high"], params["theta_low"], **b3_opts(args))
    raise ValueError(family)


# ---------------------------------------------------------------------------------------------
# compute stage


def task_base(run_name, out, args):
    """Costs (per UE) and T1 relative errors of every setting for one run."""
    path = out / "cache" / run_name / "base.npz"
    if path.exists():
        return run_name, "base", "cached", 0.0
    t0 = time.time()
    run = load_run(run_name, args.traces)
    gm, gp = t1.ground_truth(run.x)
    arrays, info = {}, {}
    for cid, fam, params, _ in settings(args):
        c = build(fam, params, run, args)
        s = summaries(run.x, c.p_win)
        me, pe = t1.estimate(s, c.view_stats)
        arrays[f"{cid}|t1_mean"] = metrics.rel_err(me, gm)
        arrays[f"{cid}|t1_peak"] = metrics.rel_err(pe, gp)
        arrays[f"{cid}|n_notif"] = c.n_notif
        arrays[f"{cid}|n_reports"] = c.n_reports
        if fam == "B3":
            arrays[f"{cid}|p_win"] = c.p_win
        info[cid] = {"family": fam, "params": params, "label": c.label, "n_subs": c.n_subs,
                     "raw": c.raw, "n_stat": c.n_stat, "max_delay_s": c.max_delay_s}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("base.tmp.npz")
    np.savez_compressed(tmp, **arrays)
    os.replace(tmp, path)
    write_json(path.with_suffix(".json"), {"run": run_name, "valid": run.valid, "attempt": run.attempt,
                                           "supis": run.supis, "settings": info})
    return run_name, "base", "done", time.time() - t0


def t2_spec(key, args):
    """Representation key -> (family, params, stats) to build the stream."""
    if key == "full":
        return "B1", {}, ("mean",)
    if key.startswith("B2_"):
        p, sm = key[4:].split("_", 1)
        return "B2", {"p": int(p), "k": 1, "summary": sm}, SUMMARIES[sm]
    if key.startswith("B3_"):
        hi, lo = key[5:].split("_lo")
        return "B3", {"theta_high": float(hi), "theta_low": float(lo)}, SUMMARIES["mean+max"]
    raise ValueError(key)


def task_t2(run_name, key, out, args):
    path = out / "cache" / run_name / "t2" / f"{key}.json"
    if path.exists():
        return run_name, key, "cached", 0.0
    t0 = time.time()
    run = load_run(run_name, args.traces)
    fam, params, stats = t2_spec(key, args)
    c = build(fam, params, run, args)
    s = summaries(run.x, c.p_win)
    r = t2.evaluate(run.x, s, stats, c.p_win, stride=args.t2_stride)
    ae = r.pop("abs_err")
    r.update({"run": run_name, "key": key, "sum_abs_err": float(ae.sum()), "seconds": time.time() - t0})
    write_json(path, r)
    return run_name, key, "done", r["seconds"]


def t2_keys(args):
    keys = []
    for _, _, _, k in settings(args):
        if k not in keys:
            keys.append(k)
    return keys


def compute(args, out, runs):
    from joblib import Parallel, delayed
    jobs = [delayed(task_base)(r, out, args) for r in runs]
    # longest T2 fits first (many features), so the pool stays busy at the end
    weight = {k: (3 if k.startswith("B3") else 2 if "_p1_" in k else 1) for k in t2_keys(args)}
    keys = sorted(t2_keys(args), key=lambda k: -weight[k])
    jobs += [delayed(task_t2)(r, k, out, args) for k in keys for r in runs]
    todo = len(jobs)
    log(f"compute: {len(runs)} runs, {todo} tasks, n_jobs={args.jobs}")
    done = 0
    for run_name, what, status, secs in Parallel(n_jobs=args.jobs, return_as="generator_unordered")(jobs):
        done += 1
        if status != "cached" or done == todo:
            log(f"[{done}/{todo}] {run_name} {what} {status} {secs:.1f}s")
    log("compute: finished")


# ---------------------------------------------------------------------------------------------
# aggregate stage


class Store:
    """Cached per-run results."""

    def __init__(self, out, runs, args):
        self.args = args
        self.runs = runs
        self.base, self.info, self.t2 = {}, {}, {}
        for r in runs:
            d = out / "cache" / r
            self.base[r] = dict(np.load(d / "base.npz"))
            self.info[r] = json.loads((d / "base.json").read_text())
            self.t2[r] = {p.stem: json.loads(p.read_text()) for p in (d / "t2").glob("*.json")}
        self.settings = settings(args)
        self.cms = load_all()

    def ue_index(self, run, n_ue):
        """First n_ue UEs in the order 001-006, 101-120, 201-220 (sorted SUPI = this order)."""
        supis = self.info[run]["supis"]
        assert supis == sorted(supis)
        return np.arange(n_ue)

    def cost(self, run, cid, cm, n_ue=None):
        inf = self.info[run]["settings"][cid]
        nn = self.base[run][f"{cid}|n_notif"]
        nr = self.base[run][f"{cid}|n_reports"]
        if n_ue is not None:
            idx = self.ue_index(run, n_ue)
            nn, nr = nn[idx], nr[idx]
        return cost_from_counts(nn, nr, inf["n_subs"], None if inf["raw"] else inf["n_stat"], cm)


def scenario_rows(store, scenarios, seeds):
    """One row per (scenario, setting) with seeds pooled, plus per-run rows."""
    rows, run_rows = [], []
    for S in scenarios:
        rns = [f"{S}-seed{n}" for n in seeds]
        full_sum = sum(store.t2[r]["full"]["sum_abs_err"] for r in rns)
        full_n = sum(store.t2[r]["full"]["n_test"] for r in rns)
        for cid, fam, params, key in store.settings:
            row = {"scenario": S, "config": cid, "family": fam, **_flat(params),
                   "label": store.info[rns[0]]["settings"][cid]["label"]}
            for variant, cm in store.cms.items():
                cs = [store.cost(r, cid, cm) for r in rns]
                row[f"cost_{variant}"] = sum(c["bytes_up"] for c in cs)
                if variant == "main":
                    for f in ("notifications", "reports", "bytes_down", "storage_bytes"):
                        row[f] = sum(c[f] for c in cs)
                    row["duplicate_ratio"] = cs[0]["duplicate_ratio"]
            delay = max(store.info[r]["settings"][cid]["max_delay_s"] for r in rns)
            row["max_delay_s"] = delay
            row["t1_fresh"] = metrics.t1_fresh(delay)
            em = np.concatenate([store.base[r][f"{cid}|t1_mean"].ravel() for r in rns])
            ep = np.concatenate([store.base[r][f"{cid}|t1_peak"].ravel() for r in rns])
            row.update({"t1_mean_p95": metrics.p95(em), "t1_mean_median": metrics.median(em),
                        "t1_peak_p95": metrics.p95(ep), "t1_peak_median": metrics.median(ep)})
            pol_sum = sum(store.t2[r][key]["sum_abs_err"] for r in rns)
            pol_n = sum(store.t2[r][key]["n_test"] for r in rns)
            row["t2_mae"] = pol_sum / pol_n
            row["t2_mae_full"] = full_sum / full_n
            row["t2_err"] = metrics.t2_error(row["t2_mae"], row["t2_mae_full"])
            row["n_runs"] = len(rns)
            row["all_runs_valid"] = all(store.info[r]["valid"] for r in rns)
            rows.append(row)
            for r in rns:
                c = store.cost(r, cid, store.cms["main"])
                c2 = store.cost(r, cid, store.cms["sensitivity"])
                e1 = store.base[r][f"{cid}|t1_mean"]
                e2 = store.base[r][f"{cid}|t1_peak"]
                run_rows.append({"run": r, "scenario": S, "config": cid, "family": fam, **_flat(params),
                                 "cost_main": c["bytes_up"], "cost_sensitivity": c2["bytes_up"],
                                 "notifications": c["notifications"],
                                 "max_delay_s": store.info[r]["settings"][cid]["max_delay_s"],
                                 "t1_mean_p95": metrics.p95(e1), "t1_peak_p95": metrics.p95(e2),
                                 "t1_mean_median": metrics.median(e1), "t1_peak_median": metrics.median(e2),
                                 "t2_mae": store.t2[r][key]["mae"], "t2_mae_full": store.t2[r]["full"]["mae"],
                                 "t2_err": store.t2[r][key]["mae"] / store.t2[r]["full"]["mae"] - 1,
                                 "valid": store.info[r]["valid"]})
    return rows, run_rows


def _flat(params):
    return {k: params.get(k) for k in ("p", "k", "summary", "theta_high", "theta_low")}


def acc_of(row, consumer):
    if consumer == "T1":
        return {"mean_p95": row["t1_mean_p95"], "peak_p95": row["t1_peak_p95"]}
    return {"err": row["t2_err"]}


def ok_fn(row, consumer):
    acc, delay = acc_of(row, consumer), row["max_delay_s"]
    return lambda eps: metrics.satisfies(consumer, acc, eps, delay)


def family_table(rows, family, consumer, variant, scenarios):
    tab = {}
    for r in rows:
        if r["family"] == family:
            tab.setdefault(r["config"], {})[r["scenario"]] = (r[f"cost_{variant}"], ok_fn(r, consumer))
    return {c: v for c, v in tab.items() if all(S in v for S in scenarios)}


def regret_rows(rows, scenarios):
    out, details = [], {}
    for variant in ("main", "sensitivity"):
        for T in CONSUMERS:
            b2t = family_table(rows, "B2", T, variant, scenarios)
            b3t = family_table(rows, "B3", T, variant, scenarios)
            for eps in EPSILONS:
                rg = metrics.regret(b2t, scenarios, eps)
                r3 = metrics.regret_of_family(b3t, rg["denominator"], scenarios, eps)
                row = {"variant": variant, "consumer": T, "eps": eps,
                       "c_static": rg["c_static"][0] if rg["c_static"] else None,
                       "c_static_cost": rg["c_static"][1] if rg["c_static"] else None,
                       "sum_c_star_cost": rg["denominator"],
                       "regret_static": rg["regret"], "no_static": rg["no_static"],
                       "scenarios_without_c_star": ";".join(rg["no_cstar"]),
                       "b3_best": r3["best"][0] if r3["best"] else None,
                       "b3_best_cost": r3["best"][1] if r3["best"] else None,
                       "regret_b3": r3["regret"], "b3_no_feasible": r3["no_feasible"]}
                for S in scenarios:
                    cs = rg["c_star"][S]
                    row[f"c_star_{S}"] = cs[0] if cs else None
                    row[f"c_star_cost_{S}"] = cs[1] if cs else None
                out.append(row)
                details[(variant, T, eps)] = (rg, r3)
    return out, details


def h1_rows(rows, scenarios, details):
    """B1 cost vs c*(S, T, eps) per scenario and over all scenarios (H1 uses T1, eps = 5 %)."""
    out = []
    by = {(r["scenario"], r["config"]): r for r in rows}
    for (variant, T, eps), (rg, _) in details.items():
        b1_tot, cs_tot, complete = 0.0, 0.0, True
        for S in scenarios:
            b1c = by[(S, "B1")][f"cost_{variant}"]
            cs = rg["c_star"][S]
            red = None if cs is None else 1 - cs[1] / b1c
            out.append({"variant": variant, "consumer": T, "eps": eps, "scenario": S, "b1_cost": b1c,
                        "c_star": cs[0] if cs else None, "c_star_cost": cs[1] if cs else None,
                        "reduction_vs_b1": red})
            b1_tot += b1c
            if cs is None:
                complete = False
            else:
                cs_tot += cs[1]
        out.append({"variant": variant, "consumer": T, "eps": eps, "scenario": "all", "b1_cost": b1_tot,
                    "c_star": None, "c_star_cost": cs_tot if complete else None,
                    "reduction_vs_b1": (1 - cs_tot / b1_tot) if complete else None})
    return out


def h3_rows(store, rows, details, scenarios, seeds):
    """Notifications and bytes vs UE count (6, 26, 46), summed over all runs, with R^2."""
    strategies = [("B0", "B0"), ("B1", "B1")]
    for T in CONSUMERS:
        rg, _ = details[("main", T, EPS_MAIN)]
        if rg["c_static"]:
            strategies.append((f"B2 c_static({T}, eps=5%)", rg["c_static"][0]))
    strategies += [(cid, cid) for cid, fam, _, _ in store.settings if fam == "B3"]
    out, fits = [], []
    runs = [f"{S}-seed{n}" for S in scenarios for n in seeds]
    cm = store.cms["main"]
    for name, cid in strategies:
        ys = {"notifications": [], "bytes_up": []}
        for n_ue in H3_UE_COUNTS:
            tot = {"notifications": 0.0, "bytes_up": 0.0}
            for r in runs:
                c = store.cost(r, cid, cm, n_ue=n_ue)
                tot["notifications"] += c["notifications"]
                tot["bytes_up"] += c["bytes_up"]
            out.append({"strategy": name, "config": cid, "n_ue": n_ue, **tot})
            for f in ys:
                ys[f].append(tot[f])
        for f in ys:
            fit = metrics.linreg_r2(H3_UE_COUNTS, ys[f])
            fits.append({"strategy": name, "config": cid, "metric": f, **fit})
    return out, fits


def criteria(rows, h1, regret, h3fit, scenarios):
    """The numbers each preregistered criterion (PREREGISTRATION 5.3) is read from.

    Only arithmetic comparisons with the preregistered thresholds; the written judgement is P4's.
    """
    def rg(variant, T, eps):
        return next(r for r in regret if r["variant"] == variant and r["consumer"] == T and r["eps"] == eps)

    out = {"scenarios": list(scenarios), "variants": {}}
    for variant in ("main", "sensitivity"):
        h1s = [r for r in h1 if r["variant"] == variant and r["consumer"] == "T1" and r["eps"] == EPS_MAIN]
        per = {r["scenario"]: r["reduction_vs_b1"] for r in h1s}
        h2 = {}
        for eps in (0.02, 0.05, 0.10):
            h2[str(eps)] = {T: {"regret": rg(variant, T, eps)["regret_static"],
                                "no_static": rg(variant, T, eps)["no_static"],
                                "ge_30pct_or_no_static": bool(rg(variant, T, eps)["no_static"] or
                                                              (rg(variant, T, eps)["regret_static"] or 0) >= 0.30)}
                            for T in CONSUMERS}
        b3 = {T: {str(eps): {"regret_b3": rg(variant, T, eps)["regret_b3"],
                             "b3_no_feasible": rg(variant, T, eps)["b3_no_feasible"],
                             "le_10pct": (rg(variant, T, eps)["regret_b3"] is not None and
                                          rg(variant, T, eps)["regret_b3"] <= 0.10)}
                  for eps in EPSILONS} for T in CONSUMERS}
        out["variants"][variant] = {
            "H1": {"rule": "eps = 5 %: T1 lowest-cost B2 is >= 50 % cheaper than B1; primary reading "
                           "(PREREGISTRATION 7, 2026-11-12): in every scenario; pooled reported alongside",
                   "reduction_vs_b1": per,
                   "every_scenario_ge_50pct": all(v is not None and v >= 0.5 for k, v in per.items() if k != "all"),
                   "all_scenarios_pooled_ge_50pct": per.get("all") is not None and per["all"] >= 0.5},
            "H2": {"rule": "eps = 5 %: regret(T1) or regret(T2) >= 30 % or no feasible static setting; "
                           "same direction at eps = 2 % and 10 %",
                   "by_eps": h2},
            "B3": {"rule": "B3 regret <= 10 %", "by_consumer": b3},
        }
    out["H3"] = {"rule": "R^2 >= 0.95 of notifications and bytes vs UE count (6, 26, 46)",
                 "fits": h3fit, "min_r2": min(f["r2"] for f in h3fit)}
    return out


def write_csv(path, rows):
    import csv
    if not rows:
        return
    keys = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in keys})


def aggregate(args, out, scenarios, seeds):
    runs = run_names(scenarios, seeds)
    store = Store(out, runs, args)
    rows, run_rows = scenario_rows(store, scenarios, seeds)
    regret, details = regret_rows(rows, scenarios)
    h1 = h1_rows(rows, scenarios, details)
    h3, h3fit = h3_rows(store, rows, details, scenarios, seeds)
    crit = criteria(rows, h1, regret, h3fit, scenarios)
    tables = out / "tables"
    tables.mkdir(parents=True, exist_ok=True)
    write_csv(tables / "configs.csv", rows)
    write_csv(tables / "runs.csv", run_rows)
    write_csv(tables / "regret.csv", regret)
    write_csv(tables / "h1.csv", h1)
    write_csv(tables / "h3.csv", h3)
    write_csv(tables / "h3_fit.csv", h3fit)
    write_json(out / "criteria.json", crit)
    b3w = {r: {cid: store.base[r][f"{cid}|p_win"].tolist() for cid, fam, _, _ in store.settings if fam == "B3"}
           for r in runs}
    write_json(tables / "b3_periods.json", b3w)
    invalid = [r for r in runs if not store.info[r]["valid"]]
    log(f"aggregate: wrote {tables} and criteria.json; invalid runs: {invalid or 'none'}")
    if not args.no_plots:
        from sim import plots
        plots.pareto(rows, scenarios, out / "figures")
        plots.regret_curves(regret, out / "figures")
        log(f"aggregate: wrote figures to {out / 'figures'}")


# ---------------------------------------------------------------------------------------------


def parse(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=ROOT / "results")
    ap.add_argument("--traces", type=Path, default=TRACES)
    ap.add_argument("--scenarios", default=",".join(SCENARIOS))
    ap.add_argument("--seeds", default=",".join(map(str, SEEDS)))
    ap.add_argument("--stage", choices=("all", "compute", "aggregate"), default="all")
    ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--t2-stride", type=int, default=t2.DEFAULT_STRIDE)
    ap.add_argument("--b3-cv-source", choices=("producer", "received"), default="producer")
    ap.add_argument("--b3-p0", type=int, default=1)
    ap.add_argument("--b3-k-mode", choices=("max", "grid"), default="max")
    ap.add_argument("--no-plots", action="store_true")
    return ap.parse_args(argv)


def main(argv=None):
    args = parse(argv)
    out = args.out.resolve()
    scenarios = tuple(args.scenarios.split(","))
    seeds = tuple(int(s) for s in args.seeds.split(","))
    cfg = {"t2_stride": args.t2_stride, "b3": b3_opts(args), "traces": str(args.traces.resolve())}
    cfg_path = out / "cache" / "config.json"
    if cfg_path.exists():
        old = json.loads(cfg_path.read_text())
        if old != cfg:
            sys.exit(f"cache in {out} was made with {old}, not {cfg}; use another --out")
    else:
        write_json(cfg_path, cfg)
    log(f"run_grid: out={out} scenarios={scenarios} seeds={seeds} cfg={cfg}")
    t0 = time.time()
    if args.stage in ("all", "compute"):
        compute(args, out, run_names(scenarios, seeds))
    if args.stage in ("all", "aggregate"):
        aggregate(args, out, scenarios, seeds)
    log(f"run_grid: DONE in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
