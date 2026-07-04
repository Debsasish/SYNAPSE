"""The Capability Knowledge Graph (CKG).

A typed, directed, weighted, signed property graph that holds *all*
capabilities and their relationships. The resolver queries it to turn an
intent into a small activation set; the planner treats capability nodes as
typed operators. Crucially, the graph lives **outside** the model context —
the model never holds T capabilities in its head.

For clarity the reference implementation uses brute-force cosine over a dense
matrix for approximate-nearest-neighbour (ANN) search. A production deployment
would swap in an HNSW/IVF index for O(log T) recall; the asymptotics we claim
for *model context* are unaffected by that choice.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Iterable, Optional

import numpy as np

from .embedding import HashingEmbedder
from .types import (
    CapabilityNode,
    ConceptNode,
    EdgeType,
    ProviderNode,
    TrustLevel,
    TypeNode,
)

_WORD_RE = re.compile(r"[a-z0-9]+")


class CKG:
    def __init__(self, embedder: Optional[HashingEmbedder] = None, secret: bytes = b"synapse-demo-key"):
        self.embedder = embedder or HashingEmbedder()
        self.secret = secret

        self.capabilities: dict[str, CapabilityNode] = {}
        self.types: dict[str, TypeNode] = {}
        self.concepts: dict[str, ConceptNode] = {}
        self.providers: dict[str, ProviderNode] = {}

        # relationship indexes (built at index() time)
        self.type_consumers: dict[str, list[str]] = defaultdict(list)  # type -> caps consuming
        self.type_producers: dict[str, list[str]] = defaultdict(list)  # type -> caps producing
        self.concept_caps: dict[str, list[str]] = defaultdict(list)    # concept -> caps
        self.composes: dict[str, list[tuple[str, float]]] = defaultdict(list)
        self.requires: dict[str, list[str]] = defaultdict(list)
        self.semhash_class: dict[str, list[str]] = defaultdict(list)   # semhash -> caps
        self.lexical_index: dict[str, set[str]] = defaultdict(set)     # token -> caps

        # dense ANN store
        self._cap_ids: list[str] = []
        self._cap_matrix: Optional[np.ndarray] = None
        self._id_pos: dict[str, int] = {}
        self._indexed = False

    # --- construction ----------------------------------------------------
    def add_capability(self, cap: CapabilityNode) -> None:
        cap.compute_semhash()
        cap.sign(self.secret)
        self.capabilities[cap.id] = cap
        self._indexed = False

    def add_type(self, t: TypeNode) -> None:
        self.types[t.id] = t

    def add_concept(self, c: ConceptNode) -> None:
        self.concepts[c.id] = c

    def add_provider(self, p: ProviderNode) -> None:
        self.providers[p.id] = p

    def add_composes_with(self, a: str, b: str, weight: float) -> None:
        self.composes[a].append((b, weight))
        self.composes[b].append((a, weight))

    def add_requires(self, cap: str, dependency: str) -> None:
        self.requires[cap].append(dependency)

    # --- indexing --------------------------------------------------------
    def index(self) -> "CKG":
        """Compute embeddings and build the relationship/lexical/ANN indexes.

        Signature verification is enforced here: a node that fails integrity
        checks is never indexed and therefore never resolvable.
        """
        self.type_consumers.clear()
        self.type_producers.clear()
        self.concept_caps.clear()
        self.semhash_class.clear()
        self.lexical_index.clear()

        ids: list[str] = []
        vectors: list[np.ndarray] = []
        for cap in self.capabilities.values():
            if not cap.verify(self.secret):
                # Tampered/unsigned nodes are structurally excluded.
                continue
            text = self._cap_text(cap)
            cap.embedding = self.embedder.embed(text)
            ids.append(cap.id)
            vectors.append(cap.embedding)

            for t in cap.consumes:
                self.type_consumers[t].append(cap.id)
            for t in cap.produces:
                self.type_producers[t].append(cap.id)
            for concept in cap.tags:
                self.concept_caps[concept].append(cap.id)
            self.semhash_class[cap.semhash].append(cap.id)
            for tok in set(_WORD_RE.findall(text.lower())):
                self.lexical_index[tok].add(cap.id)

        self._cap_ids = ids
        self._id_pos = {cid: i for i, cid in enumerate(ids)}
        self._cap_matrix = np.vstack(vectors) if vectors else np.zeros((0, self.embedder.dim))
        self._indexed = True
        return self

    @staticmethod
    def _cap_text(cap: CapabilityNode) -> str:
        return " ".join([cap.summary, " ".join(cap.tags), " ".join(cap.produces), cap.id.replace(".", " ")])

    # --- retrieval primitives -------------------------------------------
    def ann(self, query_vec: np.ndarray, top: int) -> list[tuple[str, float]]:
        """Approximate nearest neighbours by cosine similarity."""
        if not self._indexed:
            self.index()
        if self._cap_matrix.shape[0] == 0:
            return []
        sims = self._cap_matrix @ query_vec
        top = min(top, sims.shape[0])
        idx = np.argpartition(-sims, top - 1)[:top]
        idx = idx[np.argsort(-sims[idx])]
        return [(self._cap_ids[i], float(sims[i])) for i in idx]

    def similarity(self, cap_id: str, query_vec: np.ndarray) -> float:
        pos = self._id_pos.get(cap_id)
        if pos is None:
            return 0.0
        return float(self._cap_matrix[pos] @ query_vec)

    def lexical_match(self, text: str, limit: int = 50) -> set[str]:
        toks = set(_WORD_RE.findall(text.lower()))
        hits: dict[str, int] = defaultdict(int)
        for tok in toks:
            for cid in self.lexical_index.get(tok, ()):  # exact-term recall
                hits[cid] += 1
        ranked = sorted(hits.items(), key=lambda kv: -kv[1])
        return {cid for cid, _ in ranked[:limit]}

    def tag_match(self, tags: Iterable[str]) -> set[str]:
        out: set[str] = set()
        for tag in tags:
            out.update(self.concept_caps.get(tag, ()))
        return out

    def expand(self, seeds: Iterable[str], depth: int = 2, per_node_fanout: int = 8) -> set[str]:
        """Compositional recall: reachable capabilities within ``depth`` hops.

        Follows composes_with, produces->consumes, and requires edges — the
        structural signal that pure vector similarity cannot express.
        """
        frontier = set(seeds)
        seen = set(frontier)
        for _ in range(depth):
            nxt: set[str] = set()
            for cid in frontier:
                cap = self.capabilities.get(cid)
                if cap is None:
                    continue
                # produces -> consumes (next-step capabilities)
                for t in cap.produces:
                    for consumer in self.type_consumers.get(t, ())[:per_node_fanout]:
                        nxt.add(consumer)
                # composes_with (top by weight)
                for other, _w in sorted(self.composes.get(cid, ()), key=lambda x: -x[1])[:per_node_fanout]:
                    nxt.add(other)
                # requires (prerequisites)
                for dep in self.requires.get(cid, ())[:per_node_fanout]:
                    nxt.add(dep)
            nxt -= seen
            seen |= nxt
            frontier = nxt
            if not frontier:
                break
        return seen

    # --- type lattice ----------------------------------------------------
    def is_subtype(self, a: str, b: str) -> bool:
        """True if type ``a`` is a subtype of (assignable to) type ``b``."""
        if a == b:
            return True
        seen = set()
        stack = [a]
        while stack:
            cur = stack.pop()
            if cur == b:
                return True
            if cur in seen:
                continue
            seen.add(cur)
            node = self.types.get(cur)
            if node:
                stack.extend(node.subtype_of)
        return False

    # --- stats -----------------------------------------------------------
    @property
    def n_capabilities(self) -> int:
        return len(self.capabilities)
