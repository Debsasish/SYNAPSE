"""SYNAPSE reference implementation.

A scale-invariant capability-activation protocol built around a Capability
Knowledge Graph (CKG), a hybrid resolver, a type-safe planner, and a fixed
six-verb meta-interface. See the paper in ``paper/`` for the design rationale
and the empirical evaluation.
"""

from .types import (
    TrustLevel,
    EdgeType,
    CapabilityNode,
    TypeNode,
    ProviderNode,
    ConceptNode,
    ResultNode,
    IntentRecord,
)
from .ckg import CKG
from .embedding import HashingEmbedder
from .resolver import Resolver, ResolverConfig, ActivationSet
from .planner import Planner, Plan
from .metaverbs import SynapseSession

__all__ = [
    "TrustLevel",
    "EdgeType",
    "CapabilityNode",
    "TypeNode",
    "ProviderNode",
    "ConceptNode",
    "ResultNode",
    "IntentRecord",
    "CKG",
    "HashingEmbedder",
    "Resolver",
    "ResolverConfig",
    "ActivationSet",
    "Planner",
    "Plan",
    "SynapseSession",
]

__version__ = "1.0.0"
