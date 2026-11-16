"""Figures for PREREGISTRATION 5.4: Pareto plot per (scenario, consumer) and regret vs eps.

Static PNGs (light surface). Colours follow the dataviz reference palette: categorical slot 1
(blue) = B2, slot 2 (orange) = B3; B0/B1 are neutral reference points with direct labels.
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from .prereg import EPS_MAIN, EPSILONS  # noqa: E402

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
GRID = "#e4e3df"
BLUE = "#2a78d6"
ORANGE = "#eb6834"
NEUTRAL = "#52514e"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "text.color": INK, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
    "axes.spines.top": False, "axes.spines.right": False, "font.size": 9, "lines.linewidth": 2,
})


def _err(row, consumer):
    if consumer == "T1":
        return max(row["t1_mean_p95"], row["t1_peak_p95"])
    return row["t2_err"]


def _per_ue_hour(row):
    # cost summed over the scenario's runs -> kB per UE-hour
    n_runs = row["n_runs"]
    return row["cost_main"] / (n_runs * 46 * 0.5) / 1e3


def _pareto_axes(ax, rows, S, consumer):
    from .metrics import pareto_front
    sel = [r for r in rows if r["scenario"] == S]
    fam = {f: [r for r in sel if r["family"] == f] for f in ("B0", "B1", "B2", "B3")}

    def feasible(r):
        return consumer != "T1" or r["t1_fresh"]

    for f, colour, marker in (("B2", BLUE, "o"), ("B3", ORANGE, "D")):
        ok = [r for r in fam[f] if feasible(r)]
        bad = [r for r in fam[f] if not feasible(r)]
        ax.scatter([_per_ue_hour(r) for r in ok], [_err(r, consumer) for r in ok], s=36, c=colour,
                   marker=marker, edgecolors=SURFACE, linewidths=1.5, zorder=3, label=f)
        if bad:
            ax.scatter([_per_ue_hour(r) for r in bad], [_err(r, consumer) for r in bad], s=36,
                       facecolors="none", edgecolors=colour, marker=marker, linewidths=1.2, zorder=2,
                       label=f"{f}: k·p > 60 s (not fresh for T1)")
        if ok:
            pts = [(_per_ue_hour(r), _err(r, consumer)) for r in ok]
            front = sorted(pareto_front(pts), key=lambda i: pts[i][0])
            ax.step([pts[i][0] for i in front], [pts[i][1] for i in front], where="post", color=colour,
                    linewidth=1.2, alpha=0.6, zorder=1)
    for f in ("B0", "B1"):
        for r in fam[f]:
            x, y = _per_ue_hour(r), _err(r, consumer)
            ax.scatter([x], [y], s=48, c=NEUTRAL, marker="s", edgecolors=SURFACE, linewidths=1.5, zorder=3)
            ax.annotate(f, (x, y), xytext=(0, 7), textcoords="offset points", ha="center", color=INK2,
                        fontsize=8)
    ax.axhline(EPS_MAIN, color=INK2, linestyle=(0, (4, 3)), linewidth=1)
    ax.annotate("ε = 5 %", (1, EPS_MAIN), xycoords=("axes fraction", "data"), xytext=(-2, 3),
                textcoords="offset points", ha="right", va="bottom", color=INK2, fontsize=8)
    ax.set_xscale("log")
    ax.set_yscale("symlog", linthresh=0.01)
    ys = [_err(r, consumer) for r in sel] + [EPS_MAIN]
    lo, hi = min(ys), max(ys)
    lo = -0.002 if lo >= 0 else (lo * 1.6 if lo < -0.01 else -0.015)
    ax.set_ylim(lo, hi * 1.6)
    ax.set_xlabel("producer → A-DCCF, kB per UE-hour (log)")
    ax.set_ylabel("T1: max(mean p95, peak p95) rel. error" if consumer == "T1"
                  else "T2: MAE / MAE(full 1 s) − 1")
    ax.set_title(f"{S} × {consumer}", loc="left", color=INK, fontsize=10)


def pareto(rows, scenarios, outdir):
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    for S in scenarios:
        for T in ("T1", "T2"):
            fig, ax = plt.subplots(figsize=(6.4, 4.2))
            _pareto_axes(ax, rows, S, T)
            ax.legend(frameon=False, fontsize=8, loc="best")
            fig.tight_layout()
            fig.savefig(outdir / f"pareto_{S}_{T}.png", dpi=150)
            plt.close(fig)
    fig, axes = plt.subplots(len(scenarios), 2, figsize=(11, 3.4 * len(scenarios)), squeeze=False)
    for i, S in enumerate(scenarios):
        for j, T in enumerate(("T1", "T2")):
            _pareto_axes(axes[i][j], rows, S, T)
    h, lab = axes[0][0].get_legend_handles_labels()
    fig.legend(h, lab, loc="upper center", ncol=4, frameon=False, fontsize=8)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(outdir / "pareto_all.png", dpi=130)
    plt.close(fig)


def regret_curves(regret, outdir):
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    variants = ("main", "sensitivity")
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), sharey=True)
    series = []
    for ax, variant in zip(axes, variants):
        none_row = 0
        for T, colour in (("T1", BLUE), ("T2", ORANGE)):
            for kind, style, marker in (("static", "-", "o"), ("b3", (0, (4, 3)), "D")):
                key = "regret_static" if kind == "static" else "regret_b3"
                rs = [r for r in regret if r["variant"] == variant and r["consumer"] == T]
                xs = [r["eps"] * 100 for r in rs if r[key] is not None]
                ys = [r[key] * 100 for r in rs if r[key] is not None]
                missing = [r["eps"] * 100 for r in rs if r[key] is None]
                name = f"{T} {'best static B2' if kind == 'static' else 'B3 (best θ)'}"
                (h,) = ax.plot(xs, ys, linestyle=style, color=colour, marker=marker, markersize=6,
                               markeredgecolor=SURFACE, label=name)
                if variant == "main":
                    series.append(h)
                if missing:
                    # "no feasible setting" is drawn in a strip at the bottom of the axes
                    yy = 0.03 + 0.05 * none_row
                    none_row += 1
                    ax.scatter(missing, [yy] * len(missing), marker="x", color=colour, s=40, zorder=3,
                               transform=ax.get_xaxis_transform(), clip_on=False)
                    ax.annotate(f"{name}: none feasible", (missing[-1], yy), xycoords=("data", "axes fraction"),
                                xytext=(8, 0), textcoords="offset points", va="center", color=INK2, fontsize=7)
        for level, text, dy in ((30, "H2: 30 %", 3), (10, "B3 check: 10 %", -10)):
            ax.axhline(level, color=INK2, linestyle=(0, (1, 2)), linewidth=1)
            ax.annotate(text, (1, level), xycoords=("axes fraction", "data"), xytext=(-2, dy),
                        textcoords="offset points", ha="right", color=INK2, fontsize=8)
        ax.set_xscale("log")
        ax.set_yscale("symlog", linthresh=10)
        ax.set_xticks([e * 100 for e in EPSILONS])
        ax.set_xticklabels([f"{e * 100:g} %" for e in EPSILONS])
        ax.minorticks_off()
        ax.set_xlabel("accuracy limit ε")
        ax.set_title("main cost model (a = 556.7 B)" if variant == "main"
                     else "sensitivity (a = 884.8 B)", loc="left", color=INK, fontsize=10)
    axes[0].set_ylabel("regret vs Σ per-scenario best B2 (%, symlog)")
    fig.legend(handles=series, loc="lower center", ncol=4, frameon=False, fontsize=8)
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    fig.savefig(outdir / "regret_vs_eps.png", dpi=150)
    plt.close(fig)
