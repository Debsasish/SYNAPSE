"""Summarise Jev-baseline results: accuracy, shortlist recall, and an error breakdown.

Usage (from experiments/jev, after export_catalog.py and jev_bench.mjs):
    python summarize.py results/T300_s1_synapse8-synapse32-lexical32.json results/T1000_s1_...json
"""
import json
import os
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ARM_LIST = {"synapse8": "synapse_k8", "synapse32": "synapse_k32", "lexical32": "lexical_k32", "synapse_only": "synapse_k8"}


def verb_obj(cap):
    return cap["summary"].split(" using")[0]


def error_kind(caps, gold, pred):
    if pred is None:
        return "abstained"
    g, p = caps[gold], caps[pred]
    if verb_obj(p) == verb_obj(g):
        return "look-alike (same verb+object, differs in output type)"
    return "different capability"


def summarise(path):
    rows = json.load(open(path))
    T, seed = rows[0]["T"], rows[0]["seed"]
    data = json.load(open(os.path.join(HERE, "data", f"T{T}_s{seed}.json")))
    caps = {c["id"]: c for c in data["capabilities"]}
    tasks = {t["task_id"]: t for t in data["tasks"]}

    by_arm = defaultdict(list)
    for r in rows:
        by_arm[r["arm"]].append(r)

    print(f"\n## T = {T}, seed = {seed}\n")
    print("| arm | hit@1 | with tag | no tag | gold in list | hit@1 when gold in list | abstain (real) | miss abstain |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|")
    for arm in ARM_LIST:
        rs = by_arm.get(arm, [])
        real = [r for r in rs if not r["should_miss"]]
        if not real:
            continue
        miss = [r for r in rs if r["should_miss"]]
        tag = [r for r in real if r["has_tag"]]
        notag = [r for r in real if not r["has_tag"]]
        inl = [r for r in real if r["gold"] in tasks[r["task"]]["shortlists"][ARM_LIST[arm]]["ids"]]
        mean = lambda xs: sum(xs) / len(xs) if xs else float("nan")
        print(f"| {arm} | {mean([r['correct'] for r in real]):.3f} | {mean([r['correct'] for r in tag]):.3f} "
              f"| {mean([r['correct'] for r in notag]):.3f} | {len(inl) / len(real):.3f} "
              f"| {mean([r['correct'] for r in inl]):.3f} | {mean([r['pred'] is None for r in real]):.3f} "
              f"| {sum(r['correct'] for r in miss)}/{len(miss)} |")
    print(f"\nn = {len([r for r in by_arm['synapse_only'] if not r['should_miss']])} real tasks + "
          f"{len([r for r in by_arm['synapse_only'] if r['should_miss']])} should-miss tasks per arm.")

    print("\nErrors on real tasks where the gold capability WAS in the shortlist:\n")
    print("| arm | errors | look-alike | different capability | abstained |")
    print("|---|---:|---:|---:|---:|")
    for arm in ARM_LIST:
        c = Counter()
        for r in by_arm.get(arm, []):
            if r["should_miss"] or r["correct"]:
                continue
            if r["gold"] not in tasks[r["task"]]["shortlists"][ARM_LIST[arm]]["ids"]:
                continue
            c[error_kind(caps, r["gold"], r["pred"])] += 1
        n = sum(c.values())
        print(f"| {arm} | {n} | {c['look-alike (same verb+object, differs in output type)']} "
              f"| {c['different capability']} | {c['abstained']} |")


if __name__ == "__main__":
    for p in sys.argv[1:]:
        summarise(p)
