# SYNAPSE — Scale-Invariant Capability Activation for LLM Agents

[![Tests](https://img.shields.io/badge/conformance-12%2F12%20passing-brightgreen)](tests/test_conformance.py)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

A complete, deterministic, **offline** reference implementation and a
**journal-grade empirical evaluation** of **SYNAPSE**, a new agent–tool protocol
that fixes the core scaling flaw of MCP and A2A: *their per-turn context grows
linearly with the number of available tools, so more tools make the agent
slower, costlier, and less accurate.*

SYNAPSE keeps the model's per-turn context **constant** in the number of tools by
storing capabilities in a signed **Capability Knowledge Graph (CKG)**, resolving
a small **activation set** per intent, and exposing only **six fixed meta-verbs**
to the model.

## Headline result (measured, not asserted)

Across `T = 300 … 100,000` tools (6 scales × 5 seeds), vs. a faithful MCP
baseline using the **identical** scorer:

| At T = 100,000 tools | SYNAPSE | MCP flat baseline | Advantage |
|---|---:|---:|---:|
| Context tokens / turn | **971** | 7,088,086 | **7,300× smaller** |
| Cost / task | **\$0.0073** | \$53.16 | **7,300× cheaper** |
| Task success (hit@k) | **0.640** | 0.000 (window overflow) | no collapse |

- MCP **wins at T=300** (0.980 vs 0.867) — the baseline is *not* a strawman;
  crossover is by T=1000.
- SYNAPSE's mild decay is **entirely** in tasks whose ontology tag is withheld;
  with the tag, success is near-flat (0.92 → 0.86).
- Resolver confidence is calibrated (pooled **ECE = 0.138**); abstention on
  impossible ("miss") tasks is **perfect (1.000)**.

See [`paper/paper.md`](paper/paper.md) for the readable write-up and
[`paper/paper.tex`](paper/paper.tex) for the journal-ready LaTeX.

## Quick start

```powershell
# 1. Install dependencies (offline-capable scientific stack)
pip install -r requirements.txt

# 2. Reproduce EVERYTHING (tests + experiments + figures) from seed
python run_all.py

# ...or a fast smoke test on a reduced grid (~1 min)
python run_all.py --quick
```

Outputs land in `results/*.csv` and `figures/*.{png,pdf}`. Everything is
deterministic — re-running reproduces identical numbers.

### Run pieces individually

```powershell
$env:PYTHONPATH = "$PWD\src;$PWD"
python -m pytest -q tests/                       # 12 conformance tests
python -m benchmarks.run_scale_invariance        # headline experiment
python -m benchmarks.run_resolver_quality        # quality, ablations, calibration
python -m scripts.make_figures                   # 9 publication figures
```

## What's inside

```
synapse-research/
├── src/synapse/            # the protocol reference implementation
│   ├── types.py            #   signed CapabilityNode, TypeNode, ..., trust levels
│   ├── ckg.py              #   Capability Knowledge Graph (ANN + lexical + graph)
│   ├── resolver.py         #   hybrid resolver, calibrated confidence, grounded miss
│   ├── planner.py          #   type-safe regression planner -> validated DAGs
│   ├── executor.py         #   deterministic execution + chained receipts
│   ├── metaverbs.py        #   the six meta-verbs (intend/focus/plan/invoke/observe/feedback)
│   ├── receipts.py         #   signed resolution & execution receipts
│   ├── embedding.py        #   deterministic offline signed feature-hashing embedder
│   └── tokens.py           #   exact cl100k_base token counting
├── baselines/mcp_baseline.py   # faithful O(T) flat-context MCP baseline (same scorer)
├── benchmarks/             # synthetic catalog, task suite, metrics, experiments
├── scripts/make_figures.py # figure generation
├── tests/test_conformance.py   # 12 tests encoding the normative MUSTs
├── results/                # generated CSVs (source of truth for the paper)
├── figures/                # generated PNG + PDF figures
├── paper/                  # paper.md, paper.tex, references.bib
└── run_all.py              # one-command reproduction
```

## The protocol in brief

- **Knowledge plane — CKG.** Typed, HMAC-signed capability/type/provider/concept/
  result nodes with typed edges. Tampered nodes are rejected at index time
  (supply-chain integrity). Tiered disclosure (compact vs full).
- **Resolution plane — hybrid resolver.** seed (ANN + lexical + tag) → expand
  (typed edges) → filter (trust/type) → score (semantic + lexical + ontological +
  graph + type-fit) → prune to top-k. Calibrated confidence; **grounded-miss**
  abstention below a relevance floor.
- **Interaction plane — six meta-verbs.** Constant-size schemas → the model's
  tool surface (and per-turn context) does **not** grow with `T`.

## Reproducibility & honesty

- **Same scorer for both systems** — no strawman. MCP registers tools in
  shuffled order; truncation at scale is a fair emergent effect of its finite
  32k-token window.
- **Measured vs modeled** are never conflated. Context/cost are exact token
  counts; accuracy is retrieval hit-rate on a fixed N=90 task suite.
- **Stated limitations:** synthetic catalog; no live LLM in the loop; the
  reference resolver brute-forces ANN (so its *wall-clock* latency grows with
  `T`, though the *protocol* context guarantee is `O(1)` and production HNSW is
  sub-linear); and SYNAPSE's tag-dropout subset still decays. We make **no
  "zero-flaw" claim.**

## Citation

See [`CITATION.cff`](CITATION.cff). If you use this artifact, please cite the
SYNAPSE Working Group technical report (2026).

## License

MIT — see [`LICENSE`](LICENSE).
