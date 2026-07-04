"""Resolver-quality and ablation experiment.

Measures the resolver's intrinsic quality (independent of the baseline):

* **precision@1 / hit@k / MRR** on the evaluation suite.
* **Calibration (ECE)** of the top-1 confidence, plus a reliability table.
* **Grounded-miss correctness** — does the resolver correctly return NO_MATCH on
  unanswerable intents (instead of fabricating a tool)?
* **Ablations** — turn each resolver component off and measure the accuracy drop,
  attributing performance to semantic search, lexical recall, ontology tags,
  graph expansion, and type-fit.
* **k sweep** — accuracy vs the activation-set cap.

Outputs
-------
results/resolver_quality.csv   overall quality per T
results/ablation.csv           accuracy per ablation configuration
results/reliability.csv        calibration reliability bins
results/k_sweep.csv            accuracy vs k

Run:  python -m benchmarks.run_resolver_quality
"""

from __future__ import annotations

import csv
import os

from benchmarks.config import ExperimentConfig
from benchmarks.metrics import (
    bootstrap_ci,
    expected_calibration_error,
    hit_at_k,
    reciprocal_rank,
    reliability_bins,
)
from benchmarks.synthetic_catalog import build_catalog
from benchmarks.task_suite import build_eval_suite
from synapse.metaverbs import SynapseSession
from synapse.resolver import ResolverConfig

RESULTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "results")

ABLATIONS = {
    "hybrid_full": dict(),
    "no_semantic": dict(use_semantic=False),
    "no_lexical": dict(use_lexical=False),
    "no_tag": dict(use_tag=False),
    "no_expand": dict(use_expand=False),
    "no_type_fit": dict(use_type_fit=False),
    "semantic_only": dict(use_lexical=False, use_tag=False, use_expand=False, use_type_fit=False),
}


def _eval_config(cat, suite, cfg_kwargs, k):
    sess = SynapseSession(cat.ckg, ResolverConfig(k=k, **cfg_kwargs))
    real = [t for t in suite if not t.should_miss]
    miss = [t for t in suite if t.should_miss]
    succ, hit1, rr = [], [], []
    confs, correct = [], []
    for t in real:
        act = sess.intend(t.query, tags=t.tags, available_types=set(t.initial_types))
        ranked = [n.id for n in act.nodes]
        succ.append(hit_at_k(ranked, {t.gold_capability}, k))
        is_top1 = hit_at_k(ranked, {t.gold_capability}, 1)
        hit1.append(is_top1)
        rr.append(reciprocal_rank(ranked, {t.gold_capability}))
        if act.nodes:
            confs.append(act.nodes[0].confidence)
            correct.append(bool(is_top1))
    miss_ok = sum(1 for t in miss if SynapseSession(cat.ckg, ResolverConfig(k=k, **cfg_kwargs))
                  .intend(t.query, tags=t.tags).grounded_miss)
    return dict(
        success=succ, hit1=hit1, rr=rr, confs=confs, correct=correct,
        miss_ok=miss_ok, n_miss=len(miss),
    )


def run(cfg: ExperimentConfig | None = None, verbose: bool = True) -> dict:
    cfg = cfg or ExperimentConfig()
    os.makedirs(RESULTS_DIR, exist_ok=True)

    quality_rows, ablation_rows, reliability_rows, ksweep_rows = [], [], [], []
    # Aggregate calibration across all T/seeds for a stable reliability diagram.
    all_confs, all_correct = [], []

    for T in cfg.t_grid:
        for seed in cfg.seeds:
            cat = build_catalog(T=T, seed=seed, n_gold_families=cfg.n_gold_families,
                                distractors_per_family=cfg.distractors_per_family, embed_dim=cfg.embed_dim)
            suite = build_eval_suite(cat, seed=seed, variants_per_task=cfg.variants_per_task)

            base = _eval_config(cat, suite, {}, cfg.k)
            all_confs += base["confs"]; all_correct += base["correct"]
            ece = expected_calibration_error(base["confs"], base["correct"])
            quality_rows.append(dict(
                T=cat.T, seed=seed,
                precision1=sum(base["hit1"]) / len(base["hit1"]),
                hitk=sum(base["success"]) / len(base["success"]),
                mrr=sum(base["rr"]) / len(base["rr"]),
                ece=ece,
                grounded_miss_acc=base["miss_ok"] / max(1, base["n_miss"]),
            ))

            # Ablations only at a mid catalog size to save compute (seed loop still averages).
            if T == cfg.t_grid[len(cfg.t_grid) // 2]:
                for name, kw in ABLATIONS.items():
                    r = _eval_config(cat, suite, kw, cfg.k)
                    ablation_rows.append(dict(
                        ablation=name, T=cat.T, seed=seed,
                        precision1=sum(r["hit1"]) / len(r["hit1"]),
                        hitk=sum(r["success"]) / len(r["success"]),
                        mrr=sum(r["rr"]) / len(r["rr"]),
                    ))
                for k in (1, 2, 4, 8, 16):
                    r = _eval_config(cat, suite, {}, k)
                    ksweep_rows.append(dict(
                        k=k, T=cat.T, seed=seed,
                        hitk=sum(r["success"]) / len(r["success"]),
                        precision1=sum(r["hit1"]) / len(r["hit1"]),
                    ))
        if verbose:
            print(f"  resolver-quality done T={T}")

    # reliability bins on pooled data
    centers, accs, cfs, counts = reliability_bins(all_confs, all_correct, n_bins=10)
    for c, a, cf, n in zip(centers, accs, cfs, counts):
        reliability_rows.append(dict(bin_center=c, accuracy=a, confidence=cf, count=n))

    _write("resolver_quality.csv", quality_rows)
    _write("ablation.csv", ablation_rows)
    _write("reliability.csv", reliability_rows)
    _write("k_sweep.csv", ksweep_rows)
    pooled_ece = expected_calibration_error(all_confs, all_correct)

    if verbose:
        _summary(quality_rows, ablation_rows, ksweep_rows, pooled_ece)
    return dict(quality=quality_rows, ablation=ablation_rows, reliability=reliability_rows,
                ksweep=ksweep_rows, pooled_ece=pooled_ece)


def _write(name, rows):
    if not rows:
        return
    with open(os.path.join(RESULTS_DIR, name), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def _mean(rows, key, where=None):
    vals = [r[key] for r in rows if (where is None or where(r))]
    return sum(vals) / len(vals) if vals else float("nan")


def _summary(quality, ablation, ksweep, pooled_ece):
    print("\n=== Resolver quality (averaged over seeds) ===")
    Ts = sorted({r["T"] for r in quality})
    print(f"  {'T':>7} {'prec@1':>8} {'hit@k':>8} {'MRR':>8} {'ECE':>8} {'miss_acc':>9}")
    for T in Ts:
        w = lambda r: r["T"] == T
        print(f"  {T:>7} {_mean(quality,'precision1',w):>8.3f} {_mean(quality,'hitk',w):>8.3f} "
              f"{_mean(quality,'mrr',w):>8.3f} {_mean(quality,'ece',w):>8.3f} "
              f"{_mean(quality,'grounded_miss_acc',w):>9.3f}")
    print(f"  pooled ECE = {pooled_ece:.4f}")
    print("\n=== Ablations (accuracy drop attributes contribution) ===")
    names = []
    for r in ablation:
        if r["ablation"] not in names:
            names.append(r["ablation"])
    print(f"  {'config':>16} {'prec@1':>8} {'hit@k':>8} {'MRR':>8}")
    for name in names:
        w = lambda r: r["ablation"] == name
        print(f"  {name:>16} {_mean(ablation,'precision1',w):>8.3f} "
              f"{_mean(ablation,'hitk',w):>8.3f} {_mean(ablation,'mrr',w):>8.3f}")
    print("\n=== k sweep ===")
    for k in sorted({r["k"] for r in ksweep}):
        w = lambda r: r["k"] == k
        print(f"  k={k:>2}  hit@k={_mean(ksweep,'hitk',w):.3f}  prec@1={_mean(ksweep,'precision1',w):.3f}")


if __name__ == "__main__":
    run()
