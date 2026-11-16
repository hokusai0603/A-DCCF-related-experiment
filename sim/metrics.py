"""Accuracy and cost metrics, feasibility, c*, c_static and regret (PREREGISTRATION 3, 5)."""
import math

import numpy as np

from .prereg import T1_FLOOR_BPS, T1_FRESHNESS_S


def rel_err(est, gt, floor=T1_FLOOR_BPS):
    """|est - gt| / max(gt, 10 kbps)."""
    return np.abs(np.asarray(est, float) - np.asarray(gt, float)) / np.maximum(np.asarray(gt, float), floor)


def p95(v):
    return float(np.percentile(np.asarray(v, float).ravel(), 95))


def median(v):
    return float(np.median(np.asarray(v, float).ravel()))


def t2_error(mae_policy, mae_full):
    return mae_policy / mae_full - 1.0


def t1_fresh(max_delay_s):
    return max_delay_s <= T1_FRESHNESS_S


def satisfies(consumer, acc, eps, max_delay_s):
    """acc: T1 -> {'mean_p95','peak_p95'}; T2 -> {'err'}. Freshness only constrains T1."""
    if consumer == "T1":
        return t1_fresh(max_delay_s) and acc["mean_p95"] <= eps and acc["peak_p95"] <= eps
    if consumer == "T2":
        return acc["err"] <= eps
    raise ValueError(consumer)


def regret(table, scenarios, eps):
    """table[config][scenario] = (cost, ok_fn). Returns dict with c*, c_static and regret.

    c*(S): cheapest config feasible in S. c_static: config feasible in every S with the lowest
    total cost over S. regret = sum_S cost(c_static, S) / sum_S cost(c*(S), S) - 1.
    """
    cstar = {}
    for S in scenarios:
        best = None
        for cfg, per in table.items():
            cost, ok = per[S]
            if ok(eps) and (best is None or cost < best[1]):
                best = (cfg, cost)
        cstar[S] = best
    if any(v is None for v in cstar.values()):
        denom = None
    else:
        denom = sum(v[1] for v in cstar.values())
    static = None
    for cfg, per in table.items():
        if all(per[S][1](eps) for S in scenarios):
            tot = sum(per[S][0] for S in scenarios)
            if static is None or tot < static[1]:
                static = (cfg, tot)
    if static is None or denom is None:
        rg = None
    else:
        rg = static[1] / denom - 1.0
    return {"c_star": cstar, "c_static": static, "denominator": denom, "regret": rg,
            "no_static": static is None, "no_cstar": [S for S, v in cstar.items() if v is None]}


def regret_of_family(fam_table, cstar_denominator, scenarios, eps):
    """B3 regret: among settings feasible in every scenario, the lowest sum_S cost(B3, S),
    divided by sum_S cost(c*(S)) (c* from B2) - 1."""
    best = None
    for cfg, per in fam_table.items():
        if all(per[S][1](eps) for S in scenarios):
            tot = sum(per[S][0] for S in scenarios)
            if best is None or tot < best[1]:
                best = (cfg, tot)
    if best is None or cstar_denominator is None:
        return {"best": best, "regret": None, "no_feasible": best is None}
    return {"best": best, "regret": best[1] / cstar_denominator - 1.0, "no_feasible": False}


def pareto_front(points):
    """points: list of (cost, err). Returns indices of non-dominated points (min cost, min err)."""
    order = sorted(range(len(points)), key=lambda i: (points[i][0], points[i][1]))
    front, best_err = [], math.inf
    for i in order:
        if points[i][1] < best_err:
            front.append(i)
            best_err = points[i][1]
    return front


def linreg_r2(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    A = np.vstack([x, np.ones_like(x)]).T
    coef, *_ = np.linalg.lstsq(A, y, rcond=None)
    yhat = A @ coef
    ss_res = float(((y - yhat) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 1.0
    return {"slope": float(coef[0]), "intercept": float(coef[1]), "r2": r2}
