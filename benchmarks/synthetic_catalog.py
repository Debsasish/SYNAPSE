"""Synthetic capability-catalog generator.

Generates catalogs of arbitrary size ``T`` with a realistic structure so that
retrieval difficulty is *emergent*, not hand-imposed:

* Capabilities are organised into ``domains`` (e.g. security, data, comms). Each
  domain has a vocabulary; summaries are sampled from templates over that
  vocabulary so within-domain capabilities are genuinely similar (hard
  negatives), while cross-domain capabilities are dissimilar.
* Each gold "task family" has one designated *gold* capability plus many
  near-duplicate distractors that share most vocabulary but differ in a key
  discriminating token and, crucially, in typed I/O and ontology tags — the
  structural signal SYNAPSE exploits and a flat text list cannot.
* Typed produces/consumes edges and composes_with edges are generated so the
  planner and compositional recall have real structure to traverse.

The generator is fully seeded and deterministic.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from synapse.ckg import CKG
from synapse.embedding import HashingEmbedder
from synapse.types import CapabilityNode, ConceptNode, ProviderNode, TrustLevel, TypeNode


DOMAINS = {
    "security": {
        "verbs": ["detect", "probe", "scan", "fuzz", "exploit", "audit", "enumerate"],
        "objects": ["sql injection", "xss", "csrf", "ssrf", "path traversal", "open port",
                     "weak cipher", "auth bypass", "idor", "xxe", "rce", "deserialization"],
        "tools": ["scanner", "prober", "analyzer", "engine", "checker", "harness"],
        "concepts": ["cwe:89", "cwe:79", "cwe:352", "cwe:918", "cwe:22", "owasp:A03",
                      "owasp:A01", "cwe:611", "cwe:502"],
        "side_effects": ["network.write", "network.read"],
    },
    "data": {
        "verbs": ["extract", "transform", "load", "aggregate", "join", "filter", "dedupe"],
        "objects": ["csv rows", "json records", "parquet columns", "time series",
                     "sql table", "graph edges", "log lines", "embeddings"],
        "tools": ["pipeline", "transformer", "loader", "reducer", "mapper"],
        "concepts": ["domain:etl", "domain:analytics", "domain:warehouse", "domain:stream"],
        "side_effects": ["fs.read", "fs.write", "db.read", "db.write"],
    },
    "comms": {
        "verbs": ["send", "notify", "publish", "subscribe", "route", "translate"],
        "objects": ["email", "sms", "webhook", "slack message", "push notification",
                     "queue message", "event"],
        "tools": ["gateway", "dispatcher", "broker", "relay", "connector"],
        "concepts": ["domain:messaging", "domain:notify", "domain:pubsub"],
        "side_effects": ["network.write"],
    },
    "media": {
        "verbs": ["resize", "transcode", "caption", "detect", "segment", "classify"],
        "objects": ["image", "video frame", "audio clip", "thumbnail", "object", "face"],
        "tools": ["encoder", "model", "processor", "detector", "renderer"],
        "concepts": ["domain:vision", "domain:audio", "domain:render"],
        "side_effects": ["fs.read", "fs.write"],
    },
    "finance": {
        "verbs": ["quote", "settle", "reconcile", "charge", "refund", "score"],
        "objects": ["invoice", "payment", "ledger entry", "risk", "transaction", "wallet"],
        "tools": ["processor", "engine", "gateway", "ledger", "scorer"],
        "concepts": ["domain:payments", "domain:risk", "domain:ledger"],
        "side_effects": ["db.write", "network.write"],
    },
}

TRUST_CHOICES = [TrustLevel.SANDBOXED, TrustLevel.ISOLATED, TrustLevel.TRUSTED, TrustLevel.PRIVILEGED]


@dataclass
class GoldTask:
    """A task with a known-correct capability (and an optional 2-step plan)."""
    task_id: str
    goal: str
    tags: list[str]
    gold_capability: str                 # the single correct capability id
    gold_plan: list[str] = field(default_factory=list)   # ordered ids (>=1)
    goal_type: str = ""
    initial_types: list[str] = field(default_factory=list)
    should_miss: bool = False            # true => resolver *should* return no match
    trust_ceiling: TrustLevel = TrustLevel.PRIVILEGED
    allowed_side_effects: list[str] = field(default_factory=list)


@dataclass
class Catalog:
    ckg: CKG
    gold_tasks: list[GoldTask]
    T: int
    seed: int


def _summary(rng, dom_key, obj, verb, tool) -> str:
    dom = DOMAINS[dom_key]
    extra = rng.choice(["fast", "robust", "scalable", "precise", "streaming", "batch",
                         "adaptive", "low-latency", "high-recall", "distributed"])
    return f"{verb} {obj} using a {extra} {tool}"


def _register_types(ckg: CKG):
    # a small type lattice shared across the catalog
    base_types = [
        "type.http.request", "type.http.response", "type.probe_result", "type.finding",
        "type.record", "type.dataset", "type.report", "type.message", "type.receipt",
        "type.image", "type.detection", "type.invoice", "type.settlement", "type.void",
    ]
    for t in base_types:
        ckg.add_type(TypeNode(t))
    # subtype relations (type.finding is a kind of report; detection is a finding-like)
    ckg.add_type(TypeNode("type.security_finding", subtype_of=["type.finding"]))
    ckg.add_type(TypeNode("type.dataset", subtype_of=["type.record"]))


def _domain_type_pair(dom_key):
    return {
        "security": ("type.http.request", "type.finding"),
        "data": ("type.record", "type.dataset"),
        "comms": ("type.message", "type.receipt"),
        "media": ("type.image", "type.detection"),
        "finance": ("type.invoice", "type.settlement"),
    }[dom_key]


def build_catalog(
    T: int,
    seed: int = 0,
    n_gold_families: int = 40,
    distractors_per_family: int = 6,
    embed_dim: int = 256,
) -> Catalog:
    """Build a CKG with ``T`` capabilities and a gold task suite.

    ``n_gold_families`` capability families are 'planted' with a designated gold
    capability + near-duplicate distractors; the remaining capacity is filled
    with random capabilities across all domains. As ``T`` grows, the number of
    plausible-but-wrong distractors surrounding each gold item grows, which is
    exactly what makes flat selection harder at scale.
    """
    rng = random.Random(seed)
    embedder = HashingEmbedder(dim=embed_dim)
    ckg = CKG(embedder=embedder)
    _register_types(ckg)

    for dom_key in DOMAINS:
        for c in DOMAINS[dom_key]["concepts"]:
            ckg.add_concept(ConceptNode(c, ontology=c.split(":")[0], label=c))
    provider = ProviderNode("provider.synth", kind="service", trust_tier="COMMUNITY")
    ckg.add_provider(provider)

    corpus_for_idf: list[str] = []
    gold_tasks: list[GoldTask] = []
    used_ids: set[str] = set()

    def make_cap(dom_key, obj, verb, tool, tags, in_t, out_t, trust, cid=None, effects=None) -> CapabilityNode:
        base = cid or f"{dom_key}.{verb}.{obj}.{tool}".replace(" ", "_")
        cid = base
        n = 1
        while cid in used_ids:
            n += 1
            cid = f"{base}.{n}"
        used_ids.add(cid)
        summ = _summary(rng, dom_key, obj, verb, tool)
        corpus_for_idf.append(summ + " " + " ".join(tags))
        cap = CapabilityNode(
            id=cid,
            summary=summ,
            consumes=[in_t],
            produces=[out_t],
            effects=list(effects or []),
            tags=list(tags),
            trust_level=trust,
            side_effects=list(DOMAINS[dom_key]["side_effects"]),
            provider=provider.id,
            cost_usd=round(rng.uniform(0.0, 0.5), 4),
            est_latency_ms=round(rng.uniform(5, 80), 2),
            success_rate=round(rng.uniform(0.75, 0.98), 3),
        )
        return cap

    # 1. Planted gold families (with hard-negative distractors + 2-step plans)
    dom_keys = list(DOMAINS.keys())
    for fam in range(n_gold_families):
        dom_key = dom_keys[fam % len(dom_keys)]
        dom = DOMAINS[dom_key]
        verb = rng.choice(dom["verbs"])
        obj = dom["objects"][fam % len(dom["objects"])]
        tool = rng.choice(dom["tools"])
        concept = dom["concepts"][fam % len(dom["concepts"])]
        in_t, out_t = _domain_type_pair(dom_key)

        # Stage-1 gold produces an intermediate type; stage-2 consumes it and
        # produces the goal type. Both share the gold ontology tag. All final
        # I/O is fixed BEFORE the node is signed (integrity-critical).
        mid_type = "type.probe_result" if dom_key == "security" else "type.record"
        gold = make_cap(dom_key, obj, verb, tool, [concept], in_t, mid_type,
                        TrustLevel.ISOLATED, effects=[f"effect.{obj}".replace(" ", "_")])
        ckg.add_capability(gold)

        stage2 = make_cap(dom_key, obj, "analyze", "engine", [concept], mid_type, out_t,
                          TrustLevel.SANDBOXED,
                          cid=f"{dom_key}.analyze.{obj}.stage2".replace(" ", "_"),
                          effects=[f"effect.report.{obj}".replace(" ", "_")])
        ckg.add_capability(stage2)
        ckg.add_composes_with(gold.id, stage2.id, 0.85)

        # hard-negative distractors: same domain/vocab, DIFFERENT concept + different type
        for d in range(distractors_per_family):
            wrong_concept = rng.choice([c for c in dom["concepts"] if c != concept])
            wrong_obj = rng.choice([o for o in dom["objects"] if o != obj])
            dist = make_cap(dom_key, wrong_obj, verb, tool, [wrong_concept], in_t, out_t, TrustLevel.ISOLATED)
            ckg.add_capability(dist)

        gold_tasks.append(
            GoldTask(
                task_id=f"task_{fam:03d}",
                goal=f"{verb} {obj}",
                tags=[concept],
                gold_capability=gold.id,
                gold_plan=[gold.id, stage2.id],
                goal_type=out_t,
                initial_types=[in_t],
                trust_ceiling=TrustLevel.PRIVILEGED,
                allowed_side_effects=list(dom["side_effects"]),
            )
        )

    # 2. A few should-miss tasks (goal has no matching capability at all)
    for i in range(5):
        gold_tasks.append(
            GoldTask(
                task_id=f"miss_{i:03d}",
                goal=f"quantum teleport a {rng.choice(['unicorn','dragon','phoenix'])} across dimension {i}",
                tags=["domain:nonexistent"],
                gold_capability="",
                should_miss=True,
            )
        )

    # 3. Fill remaining capacity with random capabilities (the "distractor sea")
    while ckg.n_capabilities < T:
        dom_key = rng.choice(dom_keys)
        dom = DOMAINS[dom_key]
        verb = rng.choice(dom["verbs"])
        obj = rng.choice(dom["objects"])
        tool = rng.choice(dom["tools"])
        concept = rng.choice(dom["concepts"])
        in_t, out_t = _domain_type_pair(dom_key)
        trust = rng.choice(TRUST_CHOICES)
        cap = make_cap(dom_key, obj, verb, tool, [concept], in_t, out_t, trust)
        ckg.add_capability(cap)

    # Fit IDF on the full corpus, then index.
    embedder.fit(corpus_for_idf + [c.summary for c in ckg.capabilities.values()])
    ckg.index()
    return Catalog(ckg=ckg, gold_tasks=gold_tasks, T=ckg.n_capabilities, seed=seed)
