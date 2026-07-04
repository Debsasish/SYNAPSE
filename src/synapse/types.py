"""Core data types for the Capability Knowledge Graph (CKG).

These dataclasses mirror the node/edge schema in the SYNAPSE data-model
specification (docs 04). Identity is content-addressed via ``semhash`` and a
lightweight HMAC ``signature`` stands in for a full JWS provider signature so
the reference implementation can verify integrity without external PKI.
"""

from __future__ import annotations

import enum
import hashlib
import hmac
import json
from dataclasses import dataclass, field
from typing import Optional


class TrustLevel(enum.IntEnum):
    """Ordered trust tiers; higher is more privileged.

    Ordering matters: a constraint ``trust_level`` acts as a *ceiling* — a
    capability whose tier exceeds what the principal allows is filtered out.
    """

    SANDBOXED = 0
    ISOLATED = 1
    TRUSTED = 2
    PRIVILEGED = 3

    @classmethod
    def parse(cls, value) -> "TrustLevel":
        if isinstance(value, TrustLevel):
            return value
        if isinstance(value, int):
            return cls(value)
        return cls[str(value).strip().upper()]


class EdgeType(str, enum.Enum):
    PRODUCES = "produces"          # Capability -> Type
    CONSUMES = "consumes"          # Type -> Capability
    REQUIRES = "requires"          # Capability -> Capability
    COMPOSES_WITH = "composes_with"  # Capability <-> Capability (weighted)
    SUBSTITUTES = "substitutes"    # Capability <-> Capability (same semhash class)
    CONFLICTS_WITH = "conflicts_with"
    SIMILAR_TO = "similar_to"
    TAGGED_AS = "tagged_as"        # Capability -> Concept
    PROVIDED_BY = "provided_by"    # Capability -> Provider
    DERIVED_FROM = "derived_from"  # Result -> Capability
    CORROBORATES = "corroborates"  # Result <-> Result


def canonical_json(obj) -> str:
    """Deterministic JSON used for hashing/signing."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def semhash_of(definition: dict) -> str:
    """Content hash of a capability's canonical definition.

    Equal ``semhash`` => formally substitutable capabilities.
    """
    return hashlib.sha256(canonical_json(definition).encode("utf-8")).hexdigest()


@dataclass
class CapabilityNode:
    id: str
    summary: str                      # tier-1 disclosure text (one line)
    consumes: list[str] = field(default_factory=list)   # input TypeNode ids
    produces: list[str] = field(default_factory=list)   # output TypeNode ids
    preconditions: list[str] = field(default_factory=list)  # required state effects
    effects: list[str] = field(default_factory=list)        # produced state effects
    trust_level: TrustLevel = TrustLevel.SANDBOXED
    side_effects: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)   # ConceptNode ids (ontology)
    provider: Optional[str] = None
    cost_usd: float = 0.0             # flat per-call cost model
    est_latency_ms: float = 10.0
    success_rate: float = 0.9
    schema: dict = field(default_factory=dict)   # full tier-3 detail
    version: str = "1.0.0"
    semhash: str = ""
    signature: str = ""
    # Runtime-populated:
    embedding: Optional[object] = None    # numpy vector (set by CKG.index)

    # --- integrity -------------------------------------------------------
    def definition(self) -> dict:
        """The canonical, signable definition (excludes learned/runtime fields)."""
        return {
            "id": self.id,
            "summary": self.summary,
            "consumes": sorted(self.consumes),
            "produces": sorted(self.produces),
            "preconditions": sorted(self.preconditions),
            "effects": sorted(self.effects),
            "trust_level": int(self.trust_level),
            "side_effects": sorted(self.side_effects),
            "tags": sorted(self.tags),
            "provider": self.provider,
            "version": self.version,
        }

    def compute_semhash(self) -> str:
        self.semhash = semhash_of(self.definition())
        return self.semhash

    def sign(self, secret: bytes) -> str:
        if not self.semhash:
            self.compute_semhash()
        self.signature = hmac.new(secret, self.semhash.encode(), hashlib.sha256).hexdigest()
        return self.signature

    def verify(self, secret: bytes) -> bool:
        expected = semhash_of(self.definition())
        if expected != self.semhash:
            return False
        want = hmac.new(secret, self.semhash.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(want, self.signature)

    def tier1_text(self) -> str:
        """What the model sees in an activation set (progressive disclosure tier 1)."""
        return f"{self.id}: {self.summary}"

    def tier3_schema_text(self) -> str:
        """Full detail revealed only on ``focus`` (tier 3)."""
        payload = {
            "id": self.id,
            "summary": self.summary,
            "consumes": self.consumes,
            "produces": self.produces,
            "preconditions": self.preconditions,
            "effects": self.effects,
            "trust_level": self.trust_level.name,
            "side_effects": self.side_effects,
            "tags": self.tags,
            "cost_usd": self.cost_usd,
            "schema": self.schema,
        }
        return json.dumps(payload, indent=2)


@dataclass
class TypeNode:
    id: str
    schema: dict = field(default_factory=dict)
    subtype_of: list[str] = field(default_factory=list)  # type-lattice parents


@dataclass
class ProviderNode:
    id: str
    kind: str = "service"   # mcp | a2a | strap | service | model
    endpoint: str = "local://mock"
    trust_tier: str = "COMMUNITY"  # CORE | VERIFIED | COMMUNITY | PRIVATE


@dataclass
class ConceptNode:
    id: str
    ontology: str = "domain"
    label: str = ""


@dataclass
class ResultNode:
    id: str
    type: str
    value_hash: str
    value: object
    produced_at: str
    execution_id: str
    scope: str = "working"   # working | persistent
    confidence: float = 1.0


@dataclass
class IntentRecord:
    id: str
    intent_hash: str
    resolved_to: list[str]
    outcome: str = "success"   # success | partial | failure
    embedding: Optional[object] = None
