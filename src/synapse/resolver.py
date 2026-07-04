"""The Resolver — intent -> minimal activation set.

Implements the hybrid RESOLVE algorithm from the specification (docs 06):

    SEED  (semantic ANN  U  lexical  U  tag/ontology)
 -> EXPAND (bounded graph traversal: compositional recall)
 -> FILTER (trust ceiling, allowed side-effects, grant scope, budget)
 -> SCORE  (alpha sem + beta edge + gamma type-fit + delta trust
            + zeta corroboration - epsilon cost)
 -> PRUNE  (collapse substitute-classes, keep top-k)
 -> RETURN (tier-1 summaries + confidence + signed resolution receipt)

Every stage is toggleable so the ablation study can attribute accuracy to each
component. The output that reaches the model is bounded by ``k`` and never
references the catalog size ``T`` — the source of scale invariance.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .ckg import CKG
from .receipts import ResolutionReceipt, hash_value, new_id
from .types import TrustLevel


@dataclass
class ResolverConfig:
    k: int = 8                 # activation-set cap (bounded, independent of T)
    seed_n: int = 40           # ANN seed breadth
    expand_depth: int = 2      # graph-expansion hops
    confidence_floor: float = 0.30  # (kept for API compat; see relevance_floor)
    relevance_floor: float = 0.45   # min absolute semantic fit to not be a grounded miss
    # scoring weights
    alpha: float = 1.0   # semantic fit
    beta: float = 0.35   # learned edge weight / co-success
    gamma: float = 0.30  # type-fit (are inputs available?)
    delta: float = 0.05  # trust preference
    zeta: float = 0.20   # corroboration with memory
    epsilon: float = 0.10  # cost penalty
    # ablation toggles
    use_semantic: bool = True
    use_lexical: bool = True
    use_tag: bool = True
    use_expand: bool = True
    use_type_fit: bool = True


@dataclass
class ActivationItem:
    id: str
    summary: str
    score: float
    confidence: float
    sem_sim: float


@dataclass
class ActivationSet:
    nodes: list[ActivationItem]
    plan_available: bool
    receipt: ResolutionReceipt
    grounded_miss: bool = False
    nearest: list[str] = field(default_factory=list)
    candidate_count: int = 0        # diagnostics: size before prune

    @property
    def top(self) -> Optional[ActivationItem]:
        return self.nodes[0] if self.nodes else None


class Resolver:
    def __init__(self, ckg: CKG, config: Optional[ResolverConfig] = None, secret: bytes = b"synapse-demo-key"):
        self.ckg = ckg
        self.cfg = config or ResolverConfig()
        self.secret = secret
        self.ckg_version = f"ckg-{ckg.n_capabilities}"

    # --- public API ------------------------------------------------------
    def resolve(
        self,
        goal: str,
        tags: Optional[list[str]] = None,
        principal_grants: Optional[set[str]] = None,
        trust_ceiling: TrustLevel = TrustLevel.PRIVILEGED,
        allowed_side_effects: Optional[set[str]] = None,
        budget_usd: float = math.inf,
        latency_budget_ms: float = math.inf,
        available_types: Optional[set[str]] = None,
        memory_effects: Optional[set[str]] = None,
        principal: str = "anon",
    ) -> ActivationSet:
        cfg = self.cfg
        tags = tags or []
        query_vec = self.ckg.embedder.embed(goal + " " + " ".join(tags))

        # 1. SEED
        seeds: set[str] = set()
        if cfg.use_semantic:
            seeds |= {cid for cid, _ in self.ckg.ann(query_vec, cfg.seed_n)}
        if cfg.use_lexical:
            seeds |= self.ckg.lexical_match(goal)
        if cfg.use_tag:
            seeds |= self.ckg.tag_match(tags)

        # 2. EXPAND
        candidates = self.ckg.expand(seeds, depth=cfg.expand_depth) if cfg.use_expand else set(seeds)
        if not candidates:
            candidates = set(seeds)

        # 3. FILTER (policy / feasibility / least-privilege)
        filtered: list[str] = []
        for cid in candidates:
            cap = self.ckg.capabilities.get(cid)
            if cap is None:
                continue
            if cap.trust_level > trust_ceiling:
                continue
            if allowed_side_effects is not None and not set(cap.side_effects).issubset(allowed_side_effects):
                continue
            if principal_grants is not None and cid not in principal_grants:
                continue  # out-of-grant nodes are invisible
            if cap.cost_usd > budget_usd or cap.est_latency_ms > latency_budget_ms:
                continue
            filtered.append(cid)

        candidate_count = len(filtered)
        if not filtered:
            return self._grounded_miss(query_vec, goal, principal)

        # 4. SCORE
        scored: list[tuple[str, float, float]] = []  # (id, score, sem_sim)
        avail = available_types or set()
        mem = memory_effects or set()
        for cid in filtered:
            cap = self.ckg.capabilities[cid]
            sem = self.ckg.similarity(cid, query_vec) if cfg.use_semantic else 0.0
            edge = self._edge_weight(cid, seeds)
            type_fit = self._type_fit(cap, avail) if cfg.use_type_fit else 0.0
            trust = int(cap.trust_level) / int(TrustLevel.PRIVILEGED)
            corr = self._corroboration(cap, mem)
            cost = cap.cost_usd
            score = (
                cfg.alpha * sem
                + cfg.beta * edge
                + cfg.gamma * type_fit
                + cfg.delta * trust
                + cfg.zeta * corr
                - cfg.epsilon * cost
            )
            scored.append((cid, score, sem))

        scored.sort(key=lambda x: -x[1])

        # 5. PRUNE — collapse substitute-classes, keep top-k
        pruned = self._collapse_substitutes(scored)
        topk = pruned[: cfg.k]

        # Grounded-miss gate on ABSOLUTE relevance of the best candidate, not on
        # relative margin: a genuine best-of-many-similar answer must not be
        # discarded just because near-duplicates cluster beneath it. We only
        # declare a miss when nothing is actually relevant to the intent.
        top_sem = topk[0][2]
        if top_sem < cfg.relevance_floor:
            return self._grounded_miss(query_vec, goal, principal, scored=scored)

        confidences = self._confidences(topk)

        items = [
            ActivationItem(
                id=cid,
                summary=self.ckg.capabilities[cid].summary,
                score=score,
                confidence=conf,
                sem_sim=sem,
            )
            for (cid, score, sem), conf in zip(topk, confidences)
        ]

        receipt = ResolutionReceipt(
            receipt_id=new_id("res"),
            ckg_version=self.ckg_version,
            intent_hash=hash_value({"goal": goal, "tags": sorted(tags)}),
            principal=principal,
            activated=[it.id for it in items],
            scores=[it.score for it in items],
        ).sign(self.secret)

        return ActivationSet(
            nodes=items,
            plan_available=self._has_composable_path([it.id for it in items]),
            receipt=receipt,
            candidate_count=candidate_count,
        )

    # --- scoring helpers -------------------------------------------------
    def _edge_weight(self, cid: str, seeds: set[str]) -> float:
        """Learned co-success proxy: max composes_with weight to a seed, plus
        the node's historical success rate (both structural signals the LLM
        cannot see when scanning a flat list)."""
        cap = self.ckg.capabilities[cid]
        best = 0.0
        for other, w in self.ckg.composes.get(cid, ()):
            if other in seeds and w > best:
                best = w
        return 0.5 * best + 0.5 * cap.success_rate

    def _type_fit(self, cap, available_types: set[str]) -> float:
        if not cap.consumes:
            return 0.5  # source capabilities need no inputs
        satisfied = 0
        for needed in cap.consumes:
            if any(self.ckg.is_subtype(have, needed) for have in available_types):
                satisfied += 1
        return satisfied / len(cap.consumes)

    def _corroboration(self, cap, memory_effects: set[str]) -> float:
        if not memory_effects:
            return 0.0
        pre = set(cap.preconditions)
        if not pre:
            return 0.0
        return len(pre & memory_effects) / len(pre)

    def _collapse_substitutes(self, scored: list[tuple[str, float, float]]):
        seen_class: set[str] = set()
        out = []
        for cid, score, sem in scored:
            cls = self.ckg.capabilities[cid].semhash
            if cls in seen_class:
                continue  # keep only the best member of a substitute class
            seen_class.add(cls)
            out.append((cid, score, sem))
        return out

    @staticmethod
    def _confidences(topk: list[tuple[str, float, float]]) -> list[float]:
        """Calibrated top-1 confidence + descending per-item confidences.

        The top item's confidence is a logistic function of two signals:
        its absolute semantic fit ``sem`` and its score margin over the
        runner-up. Both rising => high confidence; a strong but ambiguous
        match (small margin) => tempered confidence. This makes confidence
        predictive of correctness, which is what the ECE metric checks.
        Lower-ranked items receive proportionally attenuated confidence.
        """
        if not topk:
            return []
        scores = [s for _, s, _ in topk]
        sem_top = topk[0][2]
        margin = (scores[0] - scores[1]) if len(scores) > 1 else scores[0]
        # logistic on a blend of absolute fit and margin
        raw = 3.2 * sem_top + 2.5 * margin - 1.15
        conf_top = 1.0 / (1.0 + math.exp(-raw))
        conf_top = float(min(0.99, max(0.01, conf_top)))
        # attenuate the rest by their score ratio to the top
        out = [conf_top]
        s0 = scores[0] if scores[0] != 0 else 1e-9
        for s in scores[1:]:
            ratio = max(0.0, min(1.0, s / s0)) if s0 > 0 else 0.0
            out.append(float(conf_top * ratio * 0.9))
        return out

    def _has_composable_path(self, ids: list[str]) -> bool:
        """Does the activation set contain a producer->consumer chain?"""
        produced: set[str] = set()
        for cid in ids:
            produced.update(self.ckg.capabilities[cid].produces)
        for cid in ids:
            cap = self.ckg.capabilities[cid]
            if any(t in produced for t in cap.consumes):
                return True
        return False

    def _grounded_miss(self, query_vec, goal, principal, scored=None) -> ActivationSet:
        nearest = [cid for cid, _ in self.ckg.ann(query_vec, 3)]
        receipt = ResolutionReceipt(
            receipt_id=new_id("res"),
            ckg_version=self.ckg_version,
            intent_hash=hash_value({"goal": goal}),
            principal=principal,
            activated=[],
            scores=[],
        ).sign(self.secret)
        return ActivationSet(
            nodes=[],
            plan_available=False,
            receipt=receipt,
            grounded_miss=True,
            nearest=nearest,
            candidate_count=0,
        )
