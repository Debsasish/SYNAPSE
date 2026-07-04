"""Realistic evaluation task suite.

The raw gold tasks in :mod:`synthetic_catalog` are *clean*: the query verb/object
match the gold summary and the exact ontology tag is supplied. Real users are
messier. This module derives a harder, more credible evaluation suite from the
catalog by applying controlled perturbations, each of which models a real
phenomenon:

* **Paraphrase** — the user phrases the goal with synonyms, so lexical overlap
  with the gold summary drops (tests semantic robustness).
* **Tag dropout** — with probability ``p_drop_tag`` the user does not supply the
  precise ontology tag (tests whether the resolver still recovers without the
  structured hint).
* **Lexical noise** — filler words are added (tests distractor robustness).

Multiple variants per family also increase the sample size ``N`` for tighter
confidence intervals. All perturbations are seeded and deterministic.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from benchmarks.synthetic_catalog import Catalog, GoldTask


VERB_SYNONYMS = {
    "detect": ["find", "identify", "uncover", "spot"],
    "probe": ["test", "check", "inspect", "examine"],
    "scan": ["sweep", "survey", "search"],
    "fuzz": ["stress-test", "randomly test"],
    "exploit": ["leverage", "abuse"],
    "audit": ["review", "assess"],
    "enumerate": ["list", "discover"],
    "extract": ["pull", "retrieve", "get"],
    "transform": ["convert", "reshape", "map"],
    "load": ["ingest", "import"],
    "aggregate": ["summarise", "roll up"],
    "join": ["merge", "combine"],
    "filter": ["select", "narrow"],
    "dedupe": ["deduplicate", "remove duplicates from"],
    "send": ["deliver", "dispatch", "transmit"],
    "notify": ["alert", "ping"],
    "publish": ["broadcast", "post"],
    "subscribe": ["listen for", "watch"],
    "route": ["forward", "direct"],
    "translate": ["convert", "localise"],
    "resize": ["rescale", "shrink"],
    "transcode": ["re-encode", "convert"],
    "caption": ["annotate", "describe"],
    "segment": ["partition", "split"],
    "classify": ["categorise", "label"],
    "quote": ["price", "estimate"],
    "settle": ["clear", "finalise"],
    "reconcile": ["match", "balance"],
    "charge": ["bill", "debit"],
    "refund": ["reimburse", "return funds for"],
    "score": ["rate", "evaluate"],
}

FILLERS = ["please", "for me", "quickly", "right now", "if possible", "on this input", "in production"]


@dataclass
class EvalTask:
    task_id: str
    query: str                       # the (possibly perturbed) natural-language goal
    tags: list[str]                  # possibly empty (tag dropout)
    gold_capability: str
    gold_plan: list[str]
    goal_type: str
    initial_types: list[str]
    should_miss: bool
    trust_ceiling: object
    allowed_side_effects: list[str]
    variant: str = "clean"


def _paraphrase(goal: str, rng: random.Random) -> str:
    parts = goal.split()
    if not parts:
        return goal
    verb = parts[0]
    rest = " ".join(parts[1:])
    syns = VERB_SYNONYMS.get(verb)
    new_verb = rng.choice(syns) if syns and rng.random() < 0.8 else verb
    out = f"{new_verb} {rest}".strip()
    if rng.random() < 0.5:
        out = f"{out} {rng.choice(FILLERS)}"
    return out


def build_eval_suite(
    catalog: Catalog,
    seed: int = 0,
    variants_per_task: int = 3,
    p_drop_tag: float = 0.4,
    p_paraphrase: float = 0.8,
) -> list[EvalTask]:
    rng = random.Random(seed)
    suite: list[EvalTask] = []
    for gt in catalog.gold_tasks:
        if gt.should_miss:
            suite.append(_from_gold(gt, gt.goal, gt.tags, "miss"))
            continue
        # one clean variant (baseline difficulty) ...
        suite.append(_from_gold(gt, gt.goal, gt.tags, "clean"))
        # ... plus perturbed variants
        for v in range(variants_per_task - 1):
            query = _paraphrase(gt.goal, rng) if rng.random() < p_paraphrase else gt.goal
            tags = [] if rng.random() < p_drop_tag else list(gt.tags)
            suite.append(_from_gold(gt, query, tags, f"perturbed_{v}"))
    return suite


def _from_gold(gt: GoldTask, query: str, tags: list[str], variant: str) -> EvalTask:
    return EvalTask(
        task_id=f"{gt.task_id}::{variant}",
        query=query,
        tags=list(tags),
        gold_capability=gt.gold_capability,
        gold_plan=list(gt.gold_plan),
        goal_type=gt.goal_type,
        initial_types=list(gt.initial_types),
        should_miss=gt.should_miss,
        trust_ceiling=gt.trust_ceiling,
        allowed_side_effects=list(gt.allowed_side_effects),
        variant=variant,
    )
