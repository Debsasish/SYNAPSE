"""Exact token accounting.

The scale-invariance claim is fundamentally about *how many tokens the model
must hold in context per turn*. We measure this precisely with the
``cl100k_base`` BPE tokenizer (the encoding used by GPT-3.5/4 class models),
so the reported context sizes are not estimates but exact token counts for a
concrete, widely deployed tokenizer.
"""

from __future__ import annotations

import functools

import tiktoken


@functools.lru_cache(maxsize=1)
def _encoder():
    return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """Exact token count under cl100k_base."""
    if not text:
        return 0
    return len(_encoder().encode(text))


def count_tokens_many(texts) -> int:
    enc = _encoder()
    return sum(len(t) for t in enc.encode_ordinary_batch(list(texts)))
