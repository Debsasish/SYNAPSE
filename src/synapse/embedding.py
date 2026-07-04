"""Deterministic, offline text embedder.

We deliberately avoid downloading a neural embedding model so the entire
benchmark is reproducible on any machine with no network access and no
per-run variance. The embedder is a hashed bag-of-features model over word
unigrams/bigrams and character 3-grams, projected into a fixed-dimensional
space with signed random hashing (the "hashing trick") and L2-normalised.

Two texts that share vocabulary land close in cosine space, which is exactly
the property the resolver and the baseline both rely on. Because *both*
systems use this identical embedder, the scale-invariance comparison is
apples-to-apples: any accuracy difference comes from graph curation and
bounded context, not from a better retriever on one side.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Iterable

import numpy as np

_WORD_RE = re.compile(r"[a-z0-9]+")


def _stable_hash(token: str) -> int:
    """Platform-stable 64-bit hash (Python's builtin hash is salted)."""
    h = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(h, "little")


class HashingEmbedder:
    """Signed feature-hashing embedder.

    Parameters
    ----------
    dim:
        Output dimensionality.
    use_bigrams, use_char_ngrams:
        Feature families to include. Character n-grams add robustness to
        morphological variants; bigrams capture short phrases.
    idf:
        Optional inverse-document-frequency weights keyed by token, learned via
        :meth:`fit`. When absent, all tokens weigh 1.0.
    """

    def __init__(
        self,
        dim: int = 256,
        use_bigrams: bool = True,
        use_char_ngrams: bool = True,
        char_n: int = 3,
    ) -> None:
        self.dim = int(dim)
        self.use_bigrams = use_bigrams
        self.use_char_ngrams = use_char_ngrams
        self.char_n = char_n
        self.idf: dict[str, float] = {}
        self._fitted = False

    # --- featurisation ---------------------------------------------------
    def _tokens(self, text: str) -> list[str]:
        words = _WORD_RE.findall(text.lower())
        feats: list[str] = list(words)
        if self.use_bigrams:
            feats.extend(f"{a}_{b}" for a, b in zip(words, words[1:]))
        if self.use_char_ngrams:
            joined = " ".join(words)
            n = self.char_n
            feats.extend(
                "#" + joined[i : i + n] for i in range(max(0, len(joined) - n + 1))
            )
        return feats

    # --- optional IDF fitting -------------------------------------------
    def fit(self, corpus: Iterable[str]) -> "HashingEmbedder":
        """Learn IDF weights so rare, discriminative terms count more."""
        docs = [set(self._tokens(t)) for t in corpus]
        n_docs = max(1, len(docs))
        df: dict[str, int] = {}
        for tokset in docs:
            for tok in tokset:
                df[tok] = df.get(tok, 0) + 1
        self.idf = {
            tok: math.log((1.0 + n_docs) / (1.0 + c)) + 1.0 for tok, c in df.items()
        }
        self._fitted = True
        return self

    # --- embedding -------------------------------------------------------
    def embed(self, text: str) -> np.ndarray:
        vec = np.zeros(self.dim, dtype=np.float64)
        for tok in self._tokens(text):
            h = _stable_hash(tok)
            idx = h % self.dim
            sign = 1.0 if (h >> 63) & 1 else -1.0
            weight = self.idf.get(tok, 1.0) if self._fitted else 1.0
            vec[idx] += sign * weight
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        return vec

    def embed_many(self, texts: Iterable[str]) -> np.ndarray:
        return np.vstack([self.embed(t) for t in texts])


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity of two (already L2-normalised) vectors."""
    return float(np.dot(a, b))
