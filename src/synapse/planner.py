"""The Planner — goal -> type-safe executable DAG.

Capability nodes carry preconditions/effects and typed produces/consumes edges,
so SYNAPSE can *compute* a multi-step plan instead of asking the model to guess
a tool sequence. Two guarantees (docs 06):

1. **Type-safe composition** — a plan edge A->B exists only if A's output type
   is a subtype of B's input type (checked against the CKG type lattice).
2. **Bounded search** — planning runs over the small *activated* subgraph the
   resolver already pruned, so the classic planning blow-up cannot occur.

The search is a best-first (GOAP-style) regression/progression over operators.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .ckg import CKG


@dataclass
class PlanStep:
    capability_id: str
    consumes: list[str]
    produces: list[str]


@dataclass
class PlanEdge:
    src: str          # producer capability id
    dst: str          # consumer capability id
    type_id: str      # the data type flowing across the edge


@dataclass
class Plan:
    steps: list[PlanStep]
    edges: list[PlanEdge]
    goal_type: Optional[str]
    valid: bool
    reason: str = "ok"

    @property
    def order(self) -> list[str]:
        return [s.capability_id for s in self.steps]


class Planner:
    def __init__(self, ckg: CKG):
        self.ckg = ckg

    def plan(
        self,
        activated: list[str],
        goal_type: Optional[str] = None,
        goal_effect: Optional[str] = None,
        initial_types: Optional[set[str]] = None,
        max_steps: int = 8,
    ) -> Plan:
        """Compute a type-safe DAG over the activated subgraph.

        Progression search: starting from ``initial_types``, repeatedly add an
        applicable operator (all inputs available, or a source op) that makes
        progress toward producing ``goal_type`` / ``goal_effect``.
        """
        subgraph = [cid for cid in activated if cid in self.ckg.capabilities]
        available: set[str] = set(initial_types or set())
        produced_effects: set[str] = set()
        steps: list[PlanStep] = []
        edges: list[PlanEdge] = []
        used: set[str] = set()

        def inputs_satisfied(cap) -> bool:
            return all(
                any(self.ckg.is_subtype(have, needed) for have in available)
                for needed in cap.consumes
            ) if cap.consumes else True

        for _ in range(max_steps):
            if self._goal_reached(goal_type, goal_effect, available, produced_effects):
                break
            progressed = False
            # best-first: prefer operators that unlock the goal or have high success
            ordered = sorted(
                (cid for cid in subgraph if cid not in used),
                key=lambda cid: -self._operator_score(cid, goal_type, goal_effect, available),
            )
            for cid in ordered:
                cap = self.ckg.capabilities[cid]
                if not inputs_satisfied(cap):
                    continue
                # wire type-safe edges from producers already in the plan
                for needed in cap.consumes:
                    producer = self._find_producer(steps, needed)
                    if producer is not None:
                        edges.append(PlanEdge(src=producer, dst=cid, type_id=needed))
                steps.append(PlanStep(cap.id, list(cap.consumes), list(cap.produces)))
                used.add(cid)
                available.update(cap.produces)
                produced_effects.update(cap.effects)
                progressed = True
                break
            if not progressed:
                break

        valid, reason = self._validate(steps, edges, goal_type, goal_effect, produced_effects, available)
        return Plan(steps=steps, edges=edges, goal_type=goal_type, valid=valid, reason=reason)

    # --- helpers ---------------------------------------------------------
    def _find_producer(self, steps: list[PlanStep], type_id: str) -> Optional[str]:
        for s in steps:
            if any(self.ckg.is_subtype(p, type_id) for p in s.produces):
                return s.capability_id
        return None

    def _operator_score(self, cid: str, goal_type, goal_effect, available: set[str]) -> float:
        cap = self.ckg.capabilities[cid]
        score = cap.success_rate
        if goal_type and any(self.ckg.is_subtype(p, goal_type) for p in cap.produces):
            score += 2.0
        if goal_effect and goal_effect in cap.effects:
            score += 2.0
        # prefer ops whose inputs are already available (ready to fire)
        if cap.consumes and all(
            any(self.ckg.is_subtype(h, n) for h in available) for n in cap.consumes
        ):
            score += 0.5
        return score

    def _goal_reached(self, goal_type, goal_effect, available: set[str], effects: set[str]) -> bool:
        if goal_type is not None and any(self.ckg.is_subtype(a, goal_type) for a in available):
            return True
        if goal_effect is not None and goal_effect in effects:
            return True
        return False

    def _validate(self, steps, edges, goal_type, goal_effect, effects, available):
        # every edge must be type-safe
        for e in edges:
            prod = self.ckg.capabilities[e.src]
            cons = self.ckg.capabilities[e.dst]
            out_ok = any(self.ckg.is_subtype(p, e.type_id) for p in prod.produces)
            in_ok = e.type_id in cons.consumes or any(
                self.ckg.is_subtype(e.type_id, c) for c in cons.consumes
            )
            if not (out_ok and in_ok):
                return False, f"TYPE_MISMATCH on edge {e.src}->{e.dst}"
        # acyclicity (progression search cannot create cycles, but assert)
        if self._has_cycle(steps, edges):
            return False, "CYCLE"
        if not steps:
            return False, "EMPTY_PLAN"
        if not self._goal_reached(goal_type, goal_effect, available, effects):
            return False, "GOAL_UNREACHED"
        return True, "ok"

    @staticmethod
    def _has_cycle(steps, edges) -> bool:
        adj: dict[str, list[str]] = {s.capability_id: [] for s in steps}
        for e in edges:
            adj.setdefault(e.src, []).append(e.dst)
        color: dict[str, int] = {}

        def dfs(u: str) -> bool:
            color[u] = 1
            for v in adj.get(u, ()):
                if color.get(v, 0) == 1:
                    return True
                if color.get(v, 0) == 0 and dfs(v):
                    return True
            color[u] = 2
            return False

        return any(color.get(s.capability_id, 0) == 0 and dfs(s.capability_id) for s in steps)
