"""The Execution Plane — run activated capabilities, fold results back.

Executions are sandboxed/budgeted in a real deployment; here we simulate them
deterministically. Each invocation yields a signed ExecutionReceipt chained to
its parent (resolution or upstream execution), and a ResultNode that can be
folded into the CKG as working/persistent memory.
"""

from __future__ import annotations

import hashlib
import time
from typing import Optional

from .ckg import CKG
from .receipts import ExecutionReceipt, hash_value, new_id
from .types import ResultNode


class Executor:
    def __init__(self, ckg: CKG, secret: bytes = b"synapse-demo-key"):
        self.ckg = ckg
        self.secret = secret
        self.memory: dict[str, ResultNode] = {}

    def invoke(
        self,
        capability_id: str,
        inputs: Optional[dict] = None,
        parent_id: str = "root",
        seed: int = 0,
    ) -> tuple[ResultNode, ExecutionReceipt]:
        cap = self.ckg.capabilities[capability_id]
        inputs = inputs or {}

        # deterministic success draw from success_rate
        draw = _unit_hash(f"{capability_id}|{seed}|{hash_value(inputs)}")
        success = draw <= cap.success_rate

        out_type = cap.produces[0] if cap.produces else "type.void"
        value = {
            "capability": capability_id,
            "produced_type": out_type,
            "ok": success,
            "effects": cap.effects,
        }
        exec_id = new_id("exec")
        result = ResultNode(
            id=new_id("result"),
            type=out_type,
            value_hash=hash_value(value),
            value=value,
            produced_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(0)),
            execution_id=exec_id,
            scope="working",
            confidence=cap.success_rate if success else 0.0,
        )
        receipt = ExecutionReceipt(
            receipt_id=exec_id,
            capability_id=capability_id,
            parent_id=parent_id,
            input_hash=hash_value(inputs),
            output_hash=result.value_hash,
            success=success,
            cost_usd=cap.cost_usd,
            latency_ms=cap.est_latency_ms,
        ).sign(self.secret)

        self.memory[result.id] = result
        return result, receipt

    def run_plan(self, plan, seed: int = 0, parent_id: str = "root"):
        """Execute a plan DAG in topological (list) order, threading receipts."""
        results = []
        receipts = []
        available_types: dict[str, str] = {}   # type_id -> result_id
        parent = parent_id
        for step in plan.steps:
            inputs = {
                t: available_types.get(t)
                for t in step.consumes
                if t in available_types
            }
            result, receipt = self.invoke(step.capability_id, inputs, parent_id=parent, seed=seed)
            parent = receipt.receipt_id
            for t in step.produces:
                available_types[t] = result.id
            results.append(result)
            receipts.append(receipt)
        return results, receipts


def _unit_hash(text: str) -> float:
    """Deterministic float in [0,1) from text."""
    h = hashlib.blake2b(text.encode(), digest_size=8).digest()
    return int.from_bytes(h, "little") / 2 ** 64
