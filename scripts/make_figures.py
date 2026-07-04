"""Generate publication-quality figures from the results CSVs.

Produces both PNG (for quick viewing / camera-ready raster) and PDF (vector, for
LaTeX inclusion) versions of every figure. All figures are regenerated
deterministically from ``results/*.csv``.

Run:  python -m scripts.make_figures   (after running the experiments)
"""

from __future__ import annotations

import csv
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(ROOT, "results")
FIGURES = os.path.join(ROOT, "figures")

plt.rcParams.update({
    "figure.dpi": 140,
    "savefig.dpi": 300,
    "font.size": 11,
    "axes.grid": True,
    "grid.alpha": 0.3,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "legend.frameon": False,
})

SYN_COLOR = "#1b7837"
MCP_COLOR = "#b2182b"


def _read(name):
    path = os.path.join(RESULTS, name)
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def _save(fig, stem):
    os.makedirs(FIGURES, exist_ok=True)
    fig.savefig(os.path.join(FIGURES, stem + ".png"), bbox_inches="tight")
    fig.savefig(os.path.join(FIGURES, stem + ".pdf"), bbox_inches="tight")
    plt.close(fig)


def _series(agg, system, metric):
    rows = sorted([r for r in agg if r["system"] == system], key=lambda r: float(r["T"]))
    T = [float(r["T"]) for r in rows]
    mean = [float(r[f"{metric}_mean"]) for r in rows]
    lo = [float(r[f"{metric}_lo"]) for r in rows]
    hi = [float(r[f"{metric}_hi"]) for r in rows]
    return np.array(T), np.array(mean), np.array(lo), np.array(hi)


def _plot_metric(ax, agg, metric, ylabel, logy=False):
    for system, color in (("SYNAPSE", SYN_COLOR), ("MCP", MCP_COLOR)):
        T, mean, lo, hi = _series(agg, system, metric)
        ax.plot(T, mean, "-o", color=color, label=system, markersize=5)
        ax.fill_between(T, lo, hi, color=color, alpha=0.18)
    ax.set_xscale("log")
    if logy:
        ax.set_yscale("log")
    ax.set_xlabel("Catalog size $T$ (capabilities)")
    ax.set_ylabel(ylabel)
    ax.legend()


def fig_context(agg):
    fig, ax = plt.subplots(figsize=(5.4, 3.8))
    _plot_metric(ax, agg, "ctx_tokens", "Context tokens per turn", logy=True)
    ax.set_title("Per-turn model context vs catalog size")
    _save(fig, "fig1_context_per_turn")


def fig_success(agg):
    fig, ax = plt.subplots(figsize=(5.4, 3.8))
    _plot_metric(ax, agg, "success", "Task success (hit@k)")
    ax.set_ylim(-0.03, 1.03)
    ax.set_title("Correct-capability retrieval vs catalog size")
    _save(fig, "fig2_success_rate")


def fig_cost(agg):
    fig, ax = plt.subplots(figsize=(5.4, 3.8))
    _plot_metric(ax, agg, "cost_usd", "Cost per task (USD)", logy=True)
    ax.set_title("Economic cost per task vs catalog size")
    _save(fig, "fig3_cost_per_task")


def fig_latency(agg):
    fig, ax = plt.subplots(figsize=(5.4, 3.8))
    _plot_metric(ax, agg, "latency_ms", "Selection latency (ms)")
    ax.set_title("Resolver / selection latency vs catalog size")
    _save(fig, "fig4_latency")


def fig_combined(agg):
    fig, axes = plt.subplots(2, 2, figsize=(9.6, 7.2))
    _plot_metric(axes[0, 0], agg, "ctx_tokens", "Context tokens / turn", logy=True)
    axes[0, 0].set_title("(a) Per-turn context")
    _plot_metric(axes[0, 1], agg, "success", "Task success (hit@k)")
    axes[0, 1].set_ylim(-0.03, 1.03)
    axes[0, 1].set_title("(b) Task success")
    _plot_metric(axes[1, 0], agg, "cost_usd", "Cost / task (USD)", logy=True)
    axes[1, 0].set_title("(c) Cost per task")
    _plot_metric(axes[1, 1], agg, "hit1", "Precision@1")
    axes[1, 1].set_ylim(-0.03, 1.03)
    axes[1, 1].set_title("(d) Precision@1")
    fig.suptitle("Scale-invariance: SYNAPSE vs MCP flat baseline", fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    _save(fig, "fig5_scale_invariance_grid")


def fig_ablation():
    if not os.path.exists(os.path.join(RESULTS, "ablation.csv")):
        return
    rows = _read("ablation.csv")
    names, means = [], []
    order = ["hybrid_full", "no_type_fit", "no_expand", "no_tag", "no_lexical", "no_semantic", "semantic_only"]
    for name in order:
        sub = [float(r["hitk"]) for r in rows if r["ablation"] == name]
        if sub:
            names.append(name.replace("_", "\n"))
            means.append(np.mean(sub))
    fig, ax = plt.subplots(figsize=(7.2, 3.8))
    colors = [SYN_COLOR if n.startswith("hybrid") else "#4393c3" for n in names]
    ax.bar(range(len(names)), means, color=colors)
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, fontsize=9)
    ax.set_ylabel("hit@k")
    ax.set_ylim(0, 1.03)
    ax.set_title("Resolver ablation: contribution of each component")
    for i, m in enumerate(means):
        ax.text(i, m + 0.02, f"{m:.2f}", ha="center", fontsize=9)
    _save(fig, "fig6_ablation")


def fig_reliability():
    if not os.path.exists(os.path.join(RESULTS, "reliability.csv")):
        return
    rows = _read("reliability.csv")
    conf, acc, cnt = [], [], []
    for r in rows:
        if r["confidence"] and r["confidence"] != "nan" and int(float(r["count"])) > 0:
            conf.append(float(r["confidence"]))
            acc.append(float(r["accuracy"]))
            cnt.append(float(r["count"]))
    fig, ax = plt.subplots(figsize=(4.6, 4.4))
    ax.plot([0, 1], [0, 1], "--", color="gray", label="perfect calibration")
    ax.scatter(conf, acc, s=[20 + 3 * c for c in cnt], color=SYN_COLOR, label="observed", zorder=3)
    ax.set_xlabel("Predicted confidence")
    ax.set_ylabel("Empirical accuracy")
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.set_title("Confidence calibration (reliability)")
    ax.legend()
    _save(fig, "fig7_reliability")


def fig_ksweep():
    if not os.path.exists(os.path.join(RESULTS, "k_sweep.csv")):
        return
    rows = _read("k_sweep.csv")
    ks = sorted({int(r["k"]) for r in rows})
    hitk = [np.mean([float(r["hitk"]) for r in rows if int(r["k"]) == k]) for k in ks]
    p1 = [np.mean([float(r["precision1"]) for r in rows if int(r["k"]) == k]) for k in ks]
    fig, ax = plt.subplots(figsize=(5.0, 3.6))
    ax.plot(ks, hitk, "-o", color=SYN_COLOR, label="hit@k")
    ax.plot(ks, p1, "-s", color="#4393c3", label="precision@1")
    ax.set_xlabel("Activation-set cap $k$")
    ax.set_ylabel("Accuracy")
    ax.set_ylim(0, 1.03)
    ax.set_title("Accuracy vs activation-set size $k$")
    ax.legend()
    _save(fig, "fig8_k_sweep")


def fig_tag_breakdown():
    if not os.path.exists(os.path.join(RESULTS, "scale_by_tag.csv")):
        return
    rows = _read("scale_by_tag.csv")
    fig, ax = plt.subplots(figsize=(5.4, 3.8))
    for has_tag, color, label, marker in (
        ("1", SYN_COLOR, "with ontology tag", "o"),
        ("0", "#d6604d", "tag dropped (semantic-only fallback)", "s"),
    ):
        sub = sorted([r for r in rows if r["has_tag"] == has_tag], key=lambda r: float(r["T"]))
        T = [float(r["T"]) for r in sub]
        mean = [float(r["success_mean"]) for r in sub]
        lo = [float(r["success_lo"]) for r in sub]
        hi = [float(r["success_hi"]) for r in sub]
        ax.plot(T, mean, "-" + marker, color=color, label=label, markersize=5)
        ax.fill_between(T, lo, hi, color=color, alpha=0.18)
    ax.set_xscale("log")
    ax.set_ylim(-0.03, 1.03)
    ax.set_xlabel("Catalog size $T$ (capabilities)")
    ax.set_ylabel("SYNAPSE task success (hit@k)")
    ax.set_title("Where SYNAPSE's decay comes from")
    ax.legend()
    _save(fig, "fig9_tag_breakdown")


def main():
    agg = _read("scale_agg.csv")
    fig_context(agg)
    fig_success(agg)
    fig_cost(agg)
    fig_latency(agg)
    fig_combined(agg)
    fig_ablation()
    fig_reliability()
    fig_ksweep()
    fig_tag_breakdown()
    print("Figures written to", FIGURES)


if __name__ == "__main__":
    main()
