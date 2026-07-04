"""Scale-invariance experiment (the headline KPI).

Fix a task suite; vary catalog size ``T`` over >2 orders of magnitude; for both
SYNAPSE and the MCP flat baseline measure, per task:

    context_tokens_per_turn   (exact, cl100k_base)
    task_success  (hit@k: is the correct capability in the returned set?)
    hit@1, reciprocal rank
    resolver / selection latency
    cost_per_task_usd  (context tokens x turns x price)

Outputs
-------
results/scale_raw.csv        one row per (system, T, seed, task)
results/scale_agg.csv        aggregated mean + 95% bootstrap CI per (system, T)
results/scale_slopes.csv     OLS slope-vs-log10(T) test per (system, metric)

Run:  python -m benchmarks.run_scale_invariance
"""

from __future__ import annotations

import csv
import os
import time

import numpy as np

from benchmarks.config import ExperimentConfig
from benchmarks.metrics import (
    bootstrap_ci,
    cohens_d,
    hit_at_k,
    reciprocal_rank,
    slope_vs_logT,
    slope_vs_T,
)
from benchmarks.synthetic_catalog import build_catalog
from benchmarks.task_suite import build_eval_suite
from baselines.mcp_baseline import MCPBaseline
from synapse.metaverbs import SynapseSession
from synapse.resolver import ResolverConfig
from synapse.tokens import count_tokens

RESULTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "results")


def _ensure_dir():
    os.makedirs(RESULTS_DIR, exist_ok=True)


def run(cfg: ExperimentConfig | None = None, verbose: bool = True) -> dict:
    cfg = cfg or ExperimentConfig()
    _ensure_dir()
    raw_rows = []

    for T in cfg.t_grid:
        for seed in cfg.seeds:
            cat = build_catalog(
                T=T,
                seed=seed,
                n_gold_families=cfg.n_gold_families,
                distractors_per_family=cfg.distractors_per_family,
                embed_dim=cfg.embed_dim,
            )
            actual_T = cat.T
            suite = build_eval_suite(cat, seed=seed, variants_per_task=cfg.variants_per_task)
            real_tasks = [t for t in suite if not t.should_miss]

            sess = SynapseSession(cat.ckg, ResolverConfig(k=cfg.k))
            mcp = MCPBaseline(cat.ckg, window_tokens=cfg.mcp_window_tokens, order_seed=cfg.mcp_order_seed)
            mcp_full_ctx = mcp.context_tokens_full()

            for t in real_tasks:
                # --- SYNAPSE ---
                t0 = time.perf_counter()
                act = sess.intend(t.query, tags=t.tags, available_types=set(t.initial_types))
                syn_latency = (time.perf_counter() - t0) * 1000.0
                ranked = [n.id for n in act.nodes]
                tc = sess.turn_context(act, focus_ids=ranked[:1])
                syn_ctx = count_tokens(tc.full_text())
                raw_rows.append(dict(
                    system="SYNAPSE", T=actual_T, seed=seed, task=t.task_id,
                    variant=t.variant, has_tag=int(bool(t.tags)),
                    ctx_tokens=syn_ctx,
                    success=hit_at_k(ranked, {t.gold_capability}, cfg.k),
                    hit1=hit_at_k(ranked, {t.gold_capability}, 1),
                    rr=reciprocal_rank(ranked, {t.gold_capability}),
                    latency_ms=syn_latency,
                    cost_usd=syn_ctx * cfg.turns_per_task * cfg.price_per_input_token,
                ))

                # --- MCP baseline ---
                t0 = time.perf_counter()
                m = mcp.select(t.query, t.tags, top=cfg.k)
                mcp_latency = (time.perf_counter() - t0) * 1000.0
                raw_rows.append(dict(
                    system="MCP", T=actual_T, seed=seed, task=t.task_id,
                    variant=t.variant, has_tag=int(bool(t.tags)),
                    ctx_tokens=mcp_full_ctx,
                    success=hit_at_k(m.ranked, {t.gold_capability}, cfg.k),
                    hit1=hit_at_k(m.ranked, {t.gold_capability}, 1),
                    rr=reciprocal_rank(m.ranked, {t.gold_capability}),
                    latency_ms=mcp_latency,
                    cost_usd=mcp_full_ctx * cfg.turns_per_task * cfg.price_per_input_token,
                ))
            if verbose:
                print(f"  done T={actual_T} seed={seed}")

    _write_raw(raw_rows)
    agg = _aggregate(raw_rows)
    _write_agg(agg)
    slopes = _slope_tests(agg)
    _write_slopes(slopes)
    tagbreak = _tag_breakdown(raw_rows)
    _write("scale_by_tag.csv", tagbreak)
    endpoints = _endpoint_effects(raw_rows)
    _write("scale_endpoints.csv", endpoints)
    if verbose:
        _print_summary(agg, slopes, endpoints)
    return {"raw": raw_rows, "agg": agg, "slopes": slopes,
            "tag_breakdown": tagbreak, "endpoints": endpoints}


# --- aggregation ---------------------------------------------------------
METRICS = ["ctx_tokens", "success", "hit1", "rr", "latency_ms", "cost_usd"]


def _aggregate(raw_rows) -> list[dict]:
    keys = sorted({(r["system"], r["T"]) for r in raw_rows})
    out = []
    for system, T in keys:
        sub = [r for r in raw_rows if r["system"] == system and r["T"] == T]
        row = {"system": system, "T": T, "n": len(sub)}
        for m in METRICS:
            vals = [r[m] for r in sub]
            est = bootstrap_ci(vals, n_boot=2000, seed=0)
            row[f"{m}_mean"] = est.mean
            row[f"{m}_lo"] = est.lo
            row[f"{m}_hi"] = est.hi
        out.append(row)
    return out


def _slope_tests(agg) -> list[dict]:
    """Both log-T and linear-T fits; the appropriate one is chosen per metric."""
    out = []
    for system in ("SYNAPSE", "MCP"):
        rows = sorted([r for r in agg if r["system"] == system], key=lambda r: r["T"])
        Ts = [r["T"] for r in rows]
        for m in METRICS:
            ys = [r[f"{m}_mean"] for r in rows]
            log_st = slope_vs_logT(Ts, ys)
            lin_st = slope_vs_T(Ts, ys)
            out.append(dict(
                system=system, metric=m,
                logT_slope=log_st.slope, logT_flat=log_st.flat, logT_r2=log_st.r_squared,
                linT_slope=lin_st.slope, linT_ci_lo=lin_st.ci_lo, linT_ci_hi=lin_st.ci_hi,
                linT_p=lin_st.p_value, linT_r2=lin_st.r_squared, linT_flat=lin_st.flat,
            ))
    return out


def _tag_breakdown(raw_rows) -> list[dict]:
    """SYNAPSE success split by whether the ontology tag was provided.

    Isolates the mechanism behind SYNAPSE's mild decay: with the structured
    ontology hint, retrieval is near scale-invariant; without it, the resolver
    falls back to pure semantics and degrades — an honest, explanatory result.
    """
    out = []
    Ts = sorted({r["T"] for r in raw_rows})
    for T in Ts:
        for has_tag in (1, 0):
            sub = [r for r in raw_rows if r["system"] == "SYNAPSE" and r["T"] == T and r["has_tag"] == has_tag]
            if not sub:
                continue
            est = bootstrap_ci([r["success"] for r in sub], n_boot=1500, seed=0)
            out.append(dict(T=T, has_tag=has_tag, n=len(sub),
                            success_mean=est.mean, success_lo=est.lo, success_hi=est.hi))
    return out


def _endpoint_effects(raw_rows) -> list[dict]:
    """Effect size + ratio between the smallest and largest catalog."""
    Ts = sorted({r["T"] for r in raw_rows})
    t_lo, t_hi = Ts[0], Ts[-1]
    out = []
    for system in ("SYNAPSE", "MCP"):
        for m in METRICS:
            lo_vals = [r[m] for r in raw_rows if r["system"] == system and r["T"] == t_lo]
            hi_vals = [r[m] for r in raw_rows if r["system"] == system and r["T"] == t_hi]
            lo_mean = sum(lo_vals) / len(lo_vals)
            hi_mean = sum(hi_vals) / len(hi_vals)
            ratio = (hi_mean / lo_mean) if lo_mean != 0 else float("inf")
            out.append(dict(
                system=system, metric=m, T_lo=t_lo, T_hi=t_hi,
                mean_lo=lo_mean, mean_hi=hi_mean, ratio=ratio,
                cohens_d=cohens_d(lo_vals, hi_vals),
            ))
    return out


# --- IO ------------------------------------------------------------------
def _write_raw(rows):
    path = os.path.join(RESULTS_DIR, "scale_raw.csv")
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def _write_agg(agg):
    path = os.path.join(RESULTS_DIR, "scale_agg.csv")
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(agg[0].keys()))
        w.writeheader()
        w.writerows(agg)


def _write_slopes(slopes):
    path = os.path.join(RESULTS_DIR, "scale_slopes.csv")
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(slopes[0].keys()))
        w.writeheader()
        w.writerows(slopes)


def _write(name, rows):
    if not rows:
        return
    path = os.path.join(RESULTS_DIR, name)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def _print_summary(agg, slopes, endpoints):
    print("\n=== Scale-invariance summary (mean [95% CI]) ===")
    for system in ("SYNAPSE", "MCP"):
        print(f"\n{system}")
        rows = sorted([r for r in agg if r["system"] == system], key=lambda r: r["T"])
        print(f"  {'T':>7} {'ctx/turn':>12} {'success':>18} {'hit@1':>8} {'lat_ms':>8} {'$/task':>10}")
        for r in rows:
            print(f"  {r['T']:>7} {r['ctx_tokens_mean']:>12.0f} "
                  f"{r['success_mean']:>7.3f}[{r['success_lo']:.2f},{r['success_hi']:.2f}] "
                  f"{r['hit1_mean']:>8.3f} {r['latency_ms_mean']:>8.2f} {r['cost_usd_mean']:>10.5f}")
    print("\n=== Growth model fits (context & cost) ===")
    for s in slopes:
        if s["metric"] in ("ctx_tokens", "cost_usd"):
            print(f"  {s['system']:>8} {s['metric']:>11}: "
                  f"linear-in-T slope={s['linT_slope']:.4g} (R2={s['linT_r2']:.3f}) | "
                  f"per-decade(logT)={s['logT_slope']:.4g}")
    print("\n=== Endpoint effect (T_lo -> T_hi) ===")
    for e in endpoints:
        if e["metric"] in ("ctx_tokens", "success", "cost_usd"):
            print(f"  {e['system']:>8} {e['metric']:>11}: {e['mean_lo']:.4g} -> {e['mean_hi']:.4g} "
                  f"(ratio x{e['ratio']:.3g}, d={e['cohens_d']:.2f})")


if __name__ == "__main__":
    run()
