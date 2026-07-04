"""MCP-style flat-context baseline.

This is a faithful, *non-strawman* model of how MCP / A2A / STRAP expose tools:
every tool's schema is placed into the model's context, and the model selects a
tool by matching its intent against that flat list. We reproduce this honestly:

* **Context cost is O(T).** We serialise each tool to the same JSON schema shape
  an MCP server advertises and count its exact tokens with cl100k_base. Real
  models have a finite context window ``W`` (tokens). Tools whose schemas do not
  fit within ``W`` are **truncated** (never seen) — a real, documented failure
  mode of large tool catalogs.

* **Same selection function.** To avoid strawmanning, the baseline "model" scores
  visible tools with the *identical* embedder/cosine used by the SYNAPSE
  resolver. The only differences are structural: (a) the baseline sees a flat
  list with no graph/type/composition signal, (b) tools beyond ``W`` are
  invisible, and (c) as ``T`` grows the number of hard-negative distractors in
  view grows, raising the chance a distractor outranks the gold tool.

Thus any measured accuracy gap is attributable to SYNAPSE's curation and bounded
context, not to giving the baseline a worse retriever.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import numpy as np

from synapse.ckg import CKG
from synapse.tokens import count_tokens
from synapse.types import CapabilityNode


def tool_schema_text(cap: CapabilityNode) -> str:
    """The JSON an MCP server would advertise for one tool (what the model reads)."""
    return json.dumps(
        {
            "name": cap.id,
            "description": cap.summary,
            "inputSchema": {
                "type": "object",
                "properties": {
                    "input": {
                        "type": "object",
                        "description": f"Accepts {', '.join(cap.consumes) or 'any'}",
                    }
                },
            },
            "outputSchema": {"produces": cap.produces},
            "annotations": {"tags": cap.tags, "trust": cap.trust_level.name},
        },
        separators=(",", ":"),
    )


@dataclass
class MCPResult:
    selected: str | None
    ranked: list[str]
    context_tokens: int
    visible_tools: int
    total_tools: int
    truncated: bool


class MCPBaseline:
    """Flat-context selector with a finite window and identical scorer.

    Parameters
    ----------
    window_tokens:
        The model context window ``W`` in tokens. Tool schemas are packed in a
        fixed order until the window is full; the remainder are invisible.
    preamble_tokens:
        Fixed system-prompt overhead (kept constant across conditions).
    """

    def __init__(self, ckg: CKG, window_tokens: int = 128_000, preamble_tokens: int = 400, order_seed: int = 0):
        self.ckg = ckg
        self.window_tokens = window_tokens
        self.preamble_tokens = preamble_tokens
        # Registration order is arbitrary in practice: a server lists tools in
        # the order they were added, not by relevance to any future query. We
        # model this with a deterministic shuffle so that, once the catalog
        # exceeds the context window, whether a given tool is visible does not
        # depend on it happening to be planted first.
        import random as _random
        self._order: list[str] = list(ckg.capabilities.keys())
        _random.Random(order_seed).shuffle(self._order)
        self._schema_tokens: dict[str, int] = {}
        for cid in self._order:
            self._schema_tokens[cid] = count_tokens(tool_schema_text(ckg.capabilities[cid]))
        # precompute prefix sums for window packing
        self._prefix: list[int] = []
        run = self.preamble_tokens
        for cid in self._order:
            run += self._schema_tokens[cid]
            self._prefix.append(run)

    def visible_set(self) -> tuple[list[str], int, bool]:
        """Tools that fit in the window, the token total, and whether truncation occurred."""
        visible = []
        for cid, cum in zip(self._order, self._prefix):
            if cum <= self.window_tokens:
                visible.append(cid)
            else:
                break
        total_tokens = self._prefix[len(visible) - 1] if visible else self.preamble_tokens
        truncated = len(visible) < len(self._order)
        return visible, total_tokens, truncated

    def context_tokens_full(self) -> int:
        """Exact tokens to advertise the *entire* catalog (the honest O(T) cost)."""
        return self.preamble_tokens + sum(self._schema_tokens.values())

    def select(self, goal: str, tags: list[str] | None = None, top: int = 8) -> MCPResult:
        tags = tags or []
        visible, ctx_tokens, truncated = self.visible_set()
        qv = self.ckg.embedder.embed(goal + " " + " ".join(tags))

        # Same cosine scorer as the resolver — flat, no graph/type signal.
        scored: list[tuple[str, float]] = []
        for cid in visible:
            scored.append((cid, self.ckg.similarity(cid, qv)))
        scored.sort(key=lambda x: -x[1])
        ranked = [cid for cid, _ in scored[:top]]
        selected = ranked[0] if ranked else None
        return MCPResult(
            selected=selected,
            ranked=ranked,
            context_tokens=ctx_tokens,
            visible_tools=len(visible),
            total_tools=len(self._order),
            truncated=truncated,
        )
