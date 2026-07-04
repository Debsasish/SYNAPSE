"""The fixed six-verb meta-interface.

This is the crux of scale invariance: the model is ever only exposed to these
six verbs, whose schemas are constant regardless of how many capabilities exist
in the CKG. Everything else (which capability, which plan, which provider) is
resolved *outside* the model and returned as bounded, progressively-disclosed
summaries.

    intend   state a goal      -> ranked activation set (tier-1 summaries)
    focus    expand one node   -> full signature/schema (tier-3)
    plan     compute a path     -> type-safe DAG over the activated subgraph
    invoke   execute            -> result + signed execution receipt
    observe  query memory       -> prior results / correlations
    feedback report usefulness  -> updates learned edge weights

``META_VERB_SCHEMAS`` is the exact text a host would place in the model's
system context. Its token count is the fixed component of per-turn context and
is what the benchmark measures against the linear MCP baseline.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional

from .ckg import CKG
from .executor import Executor
from .planner import Plan, Planner
from .resolver import ActivationSet, Resolver, ResolverConfig
from .types import IntentRecord, TrustLevel
from .receipts import hash_value, new_id


# The only tool schemas the model ever sees. Fixed size, independent of T.
META_VERB_SCHEMAS = [
    {
        "name": "intend",
        "description": "State a goal and constraints; receive a small ranked set of relevant capabilities as one-line summaries.",
        "parameters": {
            "type": "object",
            "properties": {
                "goal": {"type": "string", "description": "What you want to accomplish."},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Optional ontology tags (e.g. cwe:89)."},
                "constraints": {"type": "object", "description": "Optional trust/budget/side-effect limits."},
            },
            "required": ["goal"],
        },
    },
    {
        "name": "focus",
        "description": "Expand full detail (typed signature, schema, examples) for one capability id from the activation set.",
        "parameters": {
            "type": "object",
            "properties": {"capability_id": {"type": "string"}},
            "required": ["capability_id"],
        },
    },
    {
        "name": "plan",
        "description": "Ask the resolver to compute a type-safe executable path over the activated subgraph toward a goal type or effect.",
        "parameters": {
            "type": "object",
            "properties": {
                "goal_type": {"type": "string"},
                "goal_effect": {"type": "string"},
                "initial_types": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
    {
        "name": "invoke",
        "description": "Execute one capability or a whole plan handle; returns results and a signed execution receipt.",
        "parameters": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "capability id or plan handle"},
                "inputs": {"type": "object"},
            },
            "required": ["target"],
        },
    },
    {
        "name": "observe",
        "description": "Query the working-memory / knowledge subgraph for prior results and correlations.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "feedback",
        "description": "Report usefulness/quality of a prior activation so the graph updates its learned edge weights.",
        "parameters": {
            "type": "object",
            "properties": {
                "receipt_id": {"type": "string"},
                "outcome": {"type": "string", "enum": ["success", "partial", "failure"]},
            },
            "required": ["receipt_id", "outcome"],
        },
    },
]


def meta_verb_context_text() -> str:
    """The exact fixed text placed in the model's context (all six verbs)."""
    return json.dumps(META_VERB_SCHEMAS, indent=2)


@dataclass
class TurnContext:
    """Everything the model holds for a single turn (for token accounting)."""
    meta_verbs_text: str
    activation_text: str
    focus_text: str = ""
    working_state_text: str = ""

    def full_text(self) -> str:
        return "\n".join(
            t for t in [self.meta_verbs_text, self.activation_text, self.focus_text, self.working_state_text] if t
        )


class SynapseSession:
    """A stateful session exposing exactly the six meta-verbs."""

    def __init__(
        self,
        ckg: CKG,
        config: Optional[ResolverConfig] = None,
        principal: str = "anon",
        grants: Optional[set[str]] = None,
        secret: bytes = b"synapse-demo-key",
    ):
        self.ckg = ckg
        self.resolver = Resolver(ckg, config, secret=secret)
        self.planner = Planner(ckg)
        self.executor = Executor(ckg, secret=secret)
        self.principal = principal
        self.grants = grants
        self.secret = secret
        self._last_activation: Optional[ActivationSet] = None
        self.intents_log: list[IntentRecord] = []

    # --- the six verbs ---------------------------------------------------
    def intend(self, goal: str, tags: Optional[list[str]] = None, **constraints) -> ActivationSet:
        act = self.resolver.resolve(
            goal=goal,
            tags=tags or [],
            principal_grants=self.grants,
            principal=self.principal,
            **constraints,
        )
        self._last_activation = act
        return act

    def focus(self, capability_id: str) -> str:
        cap = self.ckg.capabilities.get(capability_id)
        if cap is None:
            return json.dumps({"error": "NO_SUCH_CAPABILITY", "id": capability_id})
        return cap.tier3_schema_text()

    def plan(self, goal_type=None, goal_effect=None, initial_types=None, max_steps: int = 8) -> Plan:
        activated = [it.id for it in (self._last_activation.nodes if self._last_activation else [])]
        return self.planner.plan(
            activated=activated,
            goal_type=goal_type,
            goal_effect=goal_effect,
            initial_types=set(initial_types or []),
            max_steps=max_steps,
        )

    def invoke(self, target: str, inputs: Optional[dict] = None, plan: Optional[Plan] = None, seed: int = 0):
        if plan is not None:
            return self.executor.run_plan(plan, seed=seed)
        parent = self._last_activation.receipt.receipt_id if self._last_activation else "root"
        return self.executor.invoke(target, inputs, parent_id=parent, seed=seed)

    def observe(self, query: str) -> list:
        q = query.lower()
        return [r for r in self.executor.memory.values() if q in json.dumps(r.value).lower()]

    def feedback(self, activated: list[str], outcome: str = "success", boost: float = 0.05) -> None:
        """Update learned composes_with weights among co-activated capabilities."""
        delta = boost if outcome == "success" else -boost
        for i, a in enumerate(activated):
            for b in activated[i + 1 :]:
                self._bump_edge(a, b, delta)
        self.intents_log.append(
            IntentRecord(
                id=new_id("intent"),
                intent_hash=hash_value({"activated": sorted(activated)}),
                resolved_to=list(activated),
                outcome=outcome,
            )
        )

    def _bump_edge(self, a: str, b: str, delta: float) -> None:
        updated = False
        for i, (other, w) in enumerate(self.ckg.composes.get(a, [])):
            if other == b:
                self.ckg.composes[a][i] = (b, max(0.0, min(1.0, w + delta)))
                updated = True
        if not updated and delta > 0:
            self.ckg.add_composes_with(a, b, delta)

    # --- context accounting ---------------------------------------------
    def turn_context(self, activation: ActivationSet, focus_ids: Optional[list[str]] = None, working_state: str = "") -> TurnContext:
        """Build the exact per-turn context the model would hold under SYNAPSE."""
        act_lines = [f"{it.id}: {it.summary} (conf {it.confidence:.2f})" for it in activation.nodes]
        activation_text = "ACTIVATION SET:\n" + "\n".join(act_lines) if act_lines else "ACTIVATION SET: (grounded miss)"
        focus_text = ""
        if focus_ids:
            focus_text = "\n".join(self.focus(cid) for cid in focus_ids)
        return TurnContext(
            meta_verbs_text=meta_verb_context_text(),
            activation_text=activation_text,
            focus_text=focus_text,
            working_state_text=working_state,
        )
