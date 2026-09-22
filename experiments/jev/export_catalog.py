"""Export SYNAPSE catalogues + eval tasks + resolver shortlists to JSON for the Jev harness.

Usage (from experiments/jev): python export_catalog.py --T 300 1000 --seeds 1 [--shortlist 8 32]
Writes data/T{T}_s{seed}.json
"""
import argparse
import json
import os
import subprocess
import sys

# SYNAPSE iterates over sets of string ids, so resolver shortlists depend on the hash seed.
# Pin it (re-exec once) so exports are identical across runs and machines.
if os.environ.get("PYTHONHASHSEED") != "0":
    sys.exit(subprocess.call([sys.executable, *sys.argv], env={**os.environ, "PYTHONHASHSEED": "0"}))

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path[:0] = [os.path.join(ROOT, "src"), ROOT]

from benchmarks.config import ExperimentConfig  # noqa: E402
from benchmarks.synthetic_catalog import build_catalog  # noqa: E402
from benchmarks.task_suite import build_eval_suite  # noqa: E402
from baselines.mcp_baseline import MCPBaseline  # noqa: E402
from synapse.resolver import Resolver, ResolverConfig  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--T", type=int, nargs="+", default=[300, 1000])
    ap.add_argument("--seeds", type=int, nargs="+", default=[1])
    ap.add_argument("--shortlist", type=int, nargs="+", default=[8, 32])
    args = ap.parse_args()
    cfg = ExperimentConfig()
    os.makedirs(os.path.join(HERE, "data"), exist_ok=True)

    for T in args.T:
        for seed in args.seeds:
            cat = build_catalog(T=T, seed=seed, n_gold_families=cfg.n_gold_families,
                                distractors_per_family=cfg.distractors_per_family,
                                embed_dim=cfg.embed_dim)
            suite = build_eval_suite(cat, seed=seed, variants_per_task=cfg.variants_per_task)
            resolvers = {k: Resolver(cat.ckg, ResolverConfig(k=k)) for k in args.shortlist}
            mcp = MCPBaseline(cat.ckg, window_tokens=cfg.mcp_window_tokens, order_seed=cfg.mcp_order_seed)

            caps = [
                dict(id=c.id, summary=c.summary, tags=c.tags, consumes=c.consumes, produces=c.produces)
                for c in cat.ckg.capabilities.values()
            ]
            tasks = []
            for t in suite:
                shortlists = {}
                for k, r in resolvers.items():
                    act = r.resolve(t.query, tags=t.tags, available_types=set(t.initial_types),
                                    trust_ceiling=t.trust_ceiling)
                    shortlists[f"synapse_k{k}"] = dict(
                        ids=[n.id for n in act.nodes],
                        conf=[n.confidence for n in act.nodes],
                        grounded_miss=act.grounded_miss,
                    )
                kmax = max(args.shortlist)
                shortlists[f"lexical_k{kmax}"] = dict(ids=mcp.select(t.query, t.tags, top=kmax).ranked)
                tasks.append(dict(
                    task_id=t.task_id, query=t.query, tags=t.tags, variant=t.variant,
                    initial_types=t.initial_types, goal_type=t.goal_type,
                    gold=t.gold_capability, should_miss=t.should_miss,
                    shortlists=shortlists,
                ))
            out = os.path.join(HERE, "data", f"T{cat.T}_s{seed}.json")
            with open(out, "w") as f:
                json.dump(dict(T=cat.T, seed=seed, capabilities=caps, tasks=tasks), f)
            print(f"wrote {out}: {len(caps)} caps, {len(tasks)} tasks")


if __name__ == "__main__":
    main()
