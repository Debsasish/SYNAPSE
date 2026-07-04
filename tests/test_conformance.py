"""Conformance + unit tests for the SYNAPSE reference implementation.

These tests encode the ten conformance MUSTs from the specification
(docs 12.5) plus core correctness properties. Run with:

    pytest -q            (if pytest is installed)
    python -m tests.test_conformance   (standalone; no pytest required)
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from benchmarks.synthetic_catalog import build_catalog
from benchmarks.task_suite import build_eval_suite
from synapse.metaverbs import META_VERB_SCHEMAS, SynapseSession, meta_verb_context_text
from synapse.resolver import ResolverConfig
from synapse.tokens import count_tokens
from synapse.types import CapabilityNode, TrustLevel


def _catalog(T=1000, seed=1):
    return build_catalog(T=T, seed=seed, n_gold_families=20, distractors_per_family=6)


# MUST 1 — expose exactly the six meta-verbs, nothing capability-specific.
def test_exactly_six_meta_verbs():
    names = [v["name"] for v in META_VERB_SCHEMAS]
    assert names == ["intend", "focus", "plan", "invoke", "observe", "feedback"]
    assert len(META_VERB_SCHEMAS) == 6


# MUST 2 — per-turn context independent of T.
def test_constant_context_across_T():
    ctxs = []
    for T in (300, 3000, 30000):
        cat = _catalog(T=T)
        sess = SynapseSession(cat.ckg, ResolverConfig(k=8))
        gt = [t for t in cat.gold_tasks if not t.should_miss][0]
        act = sess.intend(gt.goal, tags=gt.tags, available_types=set(gt.initial_types))
        tc = sess.turn_context(act, focus_ids=[n.id for n in act.nodes][:1])
        ctxs.append(count_tokens(tc.full_text()))
    # Context must not grow with T: spread stays tiny (bounded by summary text).
    assert max(ctxs) - min(ctxs) < 300, ctxs
    # And must be orders of magnitude below the flat catalog cost.
    assert max(ctxs) < 2000, ctxs


# MUST 3 — intend returns tier-1 summaries; focus reveals more (progressive disclosure).
def test_progressive_disclosure():
    cat = _catalog()
    sess = SynapseSession(cat.ckg, ResolverConfig(k=8))
    gt = [t for t in cat.gold_tasks if not t.should_miss][0]
    act = sess.intend(gt.goal, tags=gt.tags)
    assert act.nodes, "expected a non-empty activation set"
    cid = act.nodes[0].id
    tier1 = act.nodes[0].summary
    tier3 = sess.focus(cid)
    assert len(tier3) > len(tier1)
    assert "schema" in tier3 or "consumes" in tier3


# MUST 4/5 — signed, chained receipts for intend and invoke.
def test_receipts_signed_and_chained():
    cat = _catalog()
    sess = SynapseSession(cat.ckg, ResolverConfig(k=8))
    gt = [t for t in cat.gold_tasks if not t.should_miss][0]
    act = sess.intend(gt.goal, tags=gt.tags, available_types=set(gt.initial_types))
    assert act.receipt.verify(sess.secret)
    _, exec_receipt = sess.invoke(act.nodes[0].id, {"x": 1})
    assert exec_receipt.verify(sess.secret)
    # execution receipt chains to the resolution receipt
    assert exec_receipt.parent_id == act.receipt.receipt_id


# MUST 6 — grant-scoped resolution: out-of-grant nodes are invisible.
def test_grant_scoping():
    cat = _catalog()
    gt = [t for t in cat.gold_tasks if not t.should_miss][0]
    # Grant everything EXCEPT the gold -> gold must never appear.
    all_ids = set(cat.ckg.capabilities.keys())
    grants = all_ids - {gt.gold_capability}
    sess = SynapseSession(cat.ckg, ResolverConfig(k=8), grants=grants)
    act = sess.intend(gt.goal, tags=gt.tags, available_types=set(gt.initial_types))
    assert gt.gold_capability not in [n.id for n in act.nodes]


# MUST 7 — plans are type-checked before execution.
def test_plans_are_type_safe():
    cat = _catalog()
    sess = SynapseSession(cat.ckg, ResolverConfig(k=8))
    gt = [t for t in cat.gold_tasks if not t.should_miss][0]
    sess.intend(gt.goal, tags=gt.tags, available_types=set(gt.initial_types))
    plan = sess.plan(goal_type=gt.goal_type, initial_types=gt.initial_types)
    # Every edge must satisfy the subtype relation.
    for e in plan.edges:
        prod = cat.ckg.capabilities[e.src]
        assert any(cat.ckg.is_subtype(p, e.type_id) for p in prod.produces)
    if plan.valid:
        assert plan.reason == "ok"


def test_planner_rejects_type_mismatch():
    # A hand-built mismatched chain must be flagged, not executed.
    from synapse.ckg import CKG
    from synapse.embedding import HashingEmbedder
    from synapse.planner import Planner
    from synapse.types import TypeNode

    ckg = CKG(embedder=HashingEmbedder(dim=64))
    ckg.add_type(TypeNode("type.a"))
    ckg.add_type(TypeNode("type.b"))
    ckg.add_type(TypeNode("type.c"))
    ckg.add_capability(CapabilityNode(id="p", summary="produces a", consumes=[], produces=["type.a"]))
    ckg.add_capability(CapabilityNode(id="q", summary="needs c makes b", consumes=["type.c"], produces=["type.b"]))
    ckg.index()
    plan = Planner(ckg).plan(activated=["p", "q"], goal_type="type.b", initial_types=set())
    # type.c is never produced, so the goal is unreachable -> invalid plan.
    assert not plan.valid


# MUST 8 — grounded misses instead of fabricated tools.
def test_grounded_miss():
    cat = _catalog()
    sess = SynapseSession(cat.ckg, ResolverConfig(k=8))
    miss = [t for t in cat.gold_tasks if t.should_miss]
    for t in miss:
        act = sess.intend(t.goal, tags=t.tags)
        assert act.grounded_miss
        assert act.nodes == []
        assert act.nearest, "a grounded miss should still offer nearest options"


# MUST 9 — trust levels enforced (filter drops over-trust nodes).
def test_trust_ceiling_enforced():
    cat = _catalog()
    sess = SynapseSession(cat.ckg, ResolverConfig(k=8))
    gt = [t for t in cat.gold_tasks if not t.should_miss][0]
    act = sess.intend(gt.goal, tags=gt.tags, available_types=set(gt.initial_types),
                      trust_ceiling=TrustLevel.SANDBOXED)
    for n in act.nodes:
        assert cat.ckg.capabilities[n.id].trust_level <= TrustLevel.SANDBOXED


# Integrity — tampered nodes are never indexed/resolvable.
def test_tampered_node_excluded():
    cat = _catalog(T=300)
    victim = next(iter(cat.ckg.capabilities.values()))
    victim.summary = "TAMPERED WITHOUT RE-SIGNING"  # break the signature
    cat.ckg.index()
    assert victim.id not in cat.ckg._id_pos


# Reproducibility — same snapshot + intent => identical activation set.
def test_resolution_reproducible():
    cat = _catalog()
    gt = [t for t in cat.gold_tasks if not t.should_miss][0]
    s1 = SynapseSession(cat.ckg, ResolverConfig(k=8))
    s2 = SynapseSession(cat.ckg, ResolverConfig(k=8))
    a1 = s1.intend(gt.goal, tags=gt.tags, available_types=set(gt.initial_types))
    a2 = s2.intend(gt.goal, tags=gt.tags, available_types=set(gt.initial_types))
    assert [n.id for n in a1.nodes] == [n.id for n in a2.nodes]


# Bounded activation set — never exceeds k.
def test_activation_set_bounded():
    cat = _catalog()
    for k in (1, 4, 8):
        sess = SynapseSession(cat.ckg, ResolverConfig(k=k))
        gt = [t for t in cat.gold_tasks if not t.should_miss][0]
        act = sess.intend(gt.goal, tags=gt.tags)
        assert len(act.nodes) <= k


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        fn()
        print(f"  PASS {fn.__name__}")
        passed += 1
    print(f"\n{passed}/{len(fns)} conformance/unit tests passed.")


if __name__ == "__main__":
    _run_all()
