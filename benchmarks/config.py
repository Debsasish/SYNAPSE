"""Shared experiment configuration and cost model."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


# Catalog sizes. The gold task suite is FIXED (constant N); only the number of
# distractor capabilities varies, so accuracy differences are attributable to
# scale, not to a changing task set. The smallest size must exceed the planted
# footprint (n_gold_families * (2 + distractors_per_family)).
T_GRID = [300, 1000, 3000, 10000, 30000, 100000]

# A reduced grid for a fast smoke test (enabled via SYNAPSE_QUICK=1).
T_GRID_QUICK = [300, 1000, 3000]

SEEDS = [1, 2, 3, 4, 5]
SEEDS_QUICK = [1, 2]

_QUICK = os.environ.get("SYNAPSE_QUICK", "0") == "1"

N_GOLD_FAMILIES = 30
DISTRACTORS_PER_FAMILY = 6
VARIANTS_PER_TASK = 3          # -> N = 90 evaluation tasks (+ miss tasks)
EMBED_DIM = 256
K = 8                          # activation-set cap / baseline top-k
MCP_WINDOW_TOKENS = 32_000     # model context window for the flat baseline
MCP_ORDER_SEED = 7

# Turns per task (both systems): SYNAPSE spends 1 intend + ~1 focus + 1 plan +
# invoke; MCP re-sends the full tool catalog every reasoning turn. We model a
# modest, EQUAL number of turns so the per-turn context difference is what
# drives cost. Using an equal turn count is conservative (favours neither).
TURNS_PER_TASK = 3

# LLM input-token price (USD per token). Representative of a mid-tier model
# (e.g. ~$2.50 / 1M input tokens). Only the ratio matters for the comparison.
PRICE_PER_INPUT_TOKEN = 2.50e-6


@dataclass
class ExperimentConfig:
    t_grid: list = field(default_factory=lambda: list(T_GRID_QUICK if _QUICK else T_GRID))
    seeds: list = field(default_factory=lambda: list(SEEDS_QUICK if _QUICK else SEEDS))
    n_gold_families: int = N_GOLD_FAMILIES
    distractors_per_family: int = DISTRACTORS_PER_FAMILY
    variants_per_task: int = VARIANTS_PER_TASK
    embed_dim: int = EMBED_DIM
    k: int = K
    mcp_window_tokens: int = MCP_WINDOW_TOKENS
    mcp_order_seed: int = MCP_ORDER_SEED
    turns_per_task: int = TURNS_PER_TASK
    price_per_input_token: float = PRICE_PER_INPUT_TOKEN
