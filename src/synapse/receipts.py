"""Signed, chainable receipts.

Resolution receipts prove *why* capabilities were offered; execution receipts
prove *what* ran. Both are HMAC-signed and pinned to a CKG version, and each
execution receipt references its parent, forming a verifiable DAG. This is a
faithful-but-minimal stand-in for the JWS/transparency-log machinery in the
security specification (docs 08 and 18).
"""

from __future__ import annotations

import hashlib
import hmac
import time
import uuid
from dataclasses import dataclass, field

from .types import canonical_json


def _sign(secret: bytes, payload: dict) -> str:
    return hmac.new(secret, canonical_json(payload).encode(), hashlib.sha256).hexdigest()


@dataclass
class ResolutionReceipt:
    receipt_id: str
    ckg_version: str
    intent_hash: str
    principal: str
    activated: list[str]
    scores: list[float]
    signature: str = ""
    ts: float = field(default_factory=time.time)

    def payload(self) -> dict:
        return {
            "receipt_id": self.receipt_id,
            "ckg_version": self.ckg_version,
            "intent_hash": self.intent_hash,
            "principal": self.principal,
            "activated": self.activated,
            "kind": "resolution",
        }

    def sign(self, secret: bytes) -> "ResolutionReceipt":
        self.signature = _sign(secret, self.payload())
        return self

    def verify(self, secret: bytes) -> bool:
        return hmac.compare_digest(self.signature, _sign(secret, self.payload()))


@dataclass
class ExecutionReceipt:
    receipt_id: str
    capability_id: str
    parent_id: str          # resolution receipt or upstream execution receipt
    input_hash: str
    output_hash: str
    success: bool
    cost_usd: float
    latency_ms: float
    signature: str = ""
    ts: float = field(default_factory=time.time)

    def payload(self) -> dict:
        return {
            "receipt_id": self.receipt_id,
            "capability_id": self.capability_id,
            "parent_id": self.parent_id,
            "input_hash": self.input_hash,
            "output_hash": self.output_hash,
            "success": self.success,
            "kind": "execution",
        }

    def sign(self, secret: bytes) -> "ExecutionReceipt":
        self.signature = _sign(secret, self.payload())
        return self

    def verify(self, secret: bytes) -> bool:
        return hmac.compare_digest(self.signature, _sign(secret, self.payload()))


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def hash_value(value) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()
