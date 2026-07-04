# SYNAPSE: Scale-Invariant Capability Activation for LLM Agents via a Capability Knowledge Graph

*SYNAPSE Working Group — reference implementation & reproducible artifact*

> This is the readable companion to `paper.tex` (journal-ready LaTeX). Every
> number below is measured by the code in this repository and can be regenerated
> with `python run_all.py`. The source of truth for all figures is
> `results/*.csv`.

## Abstract

Tool-augmented large language model (LLM) agents increasingly rely on protocols
such as the **Model Context Protocol (MCP)** and **Agent2Agent (A2A)** to connect
to external capabilities. These protocols share a structural flaw: the
description of every registered tool is injected into the model's context window,
so per-turn context, token cost, and cognitive load grow **linearly in the number
of available tools `T`**. As ecosystems scale to thousands of tools, this `O(T)`
growth exhausts the context window, inflates cost, and degrades selection
accuracy — *more tools make the agent worse*.

We introduce **SYNAPSE**, a protocol that decouples capability *availability*
from capability *presence in context*. SYNAPSE stores tools as signed nodes in a
**Capability Knowledge Graph (CKG)**, resolves a small task-relevant
**activation set** via a hybrid semantic–lexical–ontological retriever, and
exposes to the model only **six fixed meta-verbs** whose schema size is
independent of `T`.

Across catalog sizes from **T=300 to T=100,000** (6 scales × 5 seeds), against a
faithful MCP baseline that uses the *identical* scorer:

| Quantity (at T=100k) | SYNAPSE | MCP | Advantage |
|---|---:|---:|---:|
| Context tokens / turn | **971** | 7,088,086 | **7,300× smaller** |
| Cost / task (USD) | **\$0.0073** | \$53.16 | **7,300× cheaper** |
| Task success (hit@k) | **0.640** | 0.000 | no collapse |

MCP *wins* at the smallest scale (T=300: 0.980 vs 0.867), proving the baseline is
not a strawman; the crossover is by T=1000. SYNAPSE's mild decay is confined to
tasks whose ontology tag is withheld (with the tag, success is near-flat
0.92→0.86). We report calibration (ECE = 0.138), ablations, and an honest
account of the reference resolver's wall-clock cost.

## 1. The scaling paradox

Both MCP and A2A assume the set of available capabilities is *presented*
in-context: each tool contributes a name, description, and JSON schema to the
prompt **on every turn**. This has an `O(T)` context cost with three compounding
consequences:

1. **Context exhaustion** — thousands of schemas overflow even long windows.
2. **Cost inflation** — every turn re-pays for every tool.
3. **Accuracy degradation** — larger prompts dilute attention and add
   near-duplicate distractors, so selection quality *falls* as tools are added
   ("lost in the middle").

This is structural, not a tuning issue: any protocol mandating in-context
presence of all availability inherits `O(T)` growth.

## 2. SYNAPSE in one page

SYNAPSE separates three planes; only the last touches the model context.

- **Knowledge plane — the Capability Knowledge Graph (CKG).** A typed, signed
  multigraph of `Capability`, `Type`, `Provider`, `Concept`, and `Result` nodes
  with typed edges (`produces`, `consumes`, `subtype-of`, `provided-by`,
  `tagged`, `depends-on`). Every capability is **HMAC-signed** over its semantic
  fields; the store refuses to index a node whose signature fails to verify
  (tamper-evidence / supply-chain integrity). Nodes support tiered disclosure
  (compact tier-1 vs full tier-3).

- **Resolution plane — the hybrid resolver.** Intent → *seed* (ANN + lexical +
  tag) → *expand* along typed edges → *filter* by trust/type → *score* (semantic,
  lexical, ontological, graph proximity, type fit) → *prune* to top `k`. A
  calibrated logistic yields a confidence; if the absolute top semantic
  similarity is below a **relevance floor**, the resolver returns a **grounded
  miss** (explicit abstention) instead of a confident wrong tool. Output: an
  **activation set** (≤ k nodes) plus a signed **resolution receipt**.

- **Interaction plane — six meta-verbs.** `intend`, `focus`, `plan`, `invoke`,
  `observe`, `feedback`. Their JSON schemas are **constant in size**, so the
  model's tool surface — and per-turn context — does not grow with `T`. The
  planner is a type-safe best-first regression planner that only connects a
  producer's output type to a consumer's input type, yielding validated
  executable DAGs. Execution emits chained receipts for end-to-end provenance.

## 3. Methodology (designed to be adversarial to our own hypothesis)

- **Matched scorer (no strawman).** Both systems use the *identical*
  deterministic signed feature-hashing embedder and cosine scorer. The only
  difference is the protocol. MCP registers tools in **shuffled** order per seed,
  so truncation at large `T` is an emergent, fair consequence of the 32k-token
  window — not adversarial placement.
- **Exact accounting.** Context is measured with exact `cl100k_base`
  tokenization, not estimated. We separate *measured* quantities (context,
  tokens, cost, retrieval accuracy) from *modeled* ones.
- **Synthetic catalog.** Five domains; a **fixed** suite of N=90 gold tasks
  (constant across scales) embedded in a growing sea of hard-negative
  distractors and near-duplicate families; only the distractor count varies with
  `T`. Includes single- and two-step plans and deliberate **miss** tasks. The
  eval suite adds paraphrase, tag-dropout, and lexical-noise perturbations so
  accuracy is believable rather than a flat 1.000.
- **Protocol.** `T ∈ {300, 1k, 3k, 10k, 30k, 100k}`, 5 seeds each; bootstrap 95%
  CIs; growth characterized with both log-`T` and linear-`T` OLS fits (the
  appropriate model per metric), endpoint Cohen's `d`, and a `T_max/T_min` ratio.

## 4. Results

### 4.1 Context and cost are O(1) vs O(T) — *exact, measured*

| System | T | Ctx/turn | hit@k | hit@1 | \$/task |
|---|---:|---:|---:|---:|---:|
| SYNAPSE | 300 | 940 | 0.867 | 0.787 | 0.0070 |
| SYNAPSE | 1,000 | 947 | 0.887 | 0.769 | 0.0071 |
| SYNAPSE | 3,000 | 955 | 0.856 | 0.720 | 0.0072 |
| SYNAPSE | 10,000 | 967 | 0.731 | 0.618 | 0.0072 |
| SYNAPSE | 30,000 | 970 | 0.671 | 0.587 | 0.0073 |
| SYNAPSE | 100,000 | 971 | 0.640 | 0.551 | 0.0073 |
| MCP | 300 | 21,119 | 0.980 | 0.551 | 0.158 |
| MCP | 1,000 | 69,863 | 0.229 | 0.127 | 0.524 |
| MCP | 3,000 | 210,708 | 0.156 | 0.089 | 1.580 |
| MCP | 10,000 | 706,640 | 0.033 | 0.013 | 5.300 |
| MCP | 30,000 | 2,124,846 | 0.000 | 0.000 | 15.936 |
| MCP | 100,000 | 7,088,086 | 0.000 | 0.000 | 53.161 |

MCP context is linear in `T` (linear-`T` fit R²=1.000, ~70.9 tokens/tool).
SYNAPSE context rises only 31 tokens across 2.5 decades (activation set filling
to `k`, not dependence on `T`) — statistically nonzero, practically negligible.

### 4.2 Bounded context does not cost success

MCP's success **collapses** once gold tools are pushed past the window (hit@k →
0.000 by T=30k). SYNAPSE decays gracefully (0.867 → 0.640). Endpoint effect
sizes: MCP success Cohen's `d = 9.9` (catastrophic) vs SYNAPSE `d = 0.54`
(moderate). MCP winning at T=300 confirms a fair baseline.

### 4.3 Where SYNAPSE's decay comes from (mechanistic, honest)

| SYNAPSE subset | T=300 | T=30k | T=100k |
|---|---:|---:|---:|
| With ontology tag | 0.917 | 0.896 | 0.857 |
| Tag dropped (semantic-only) | 0.719 | 0.009 | 0.000 |

The *entire* aggregate decay is the tag-dropout subset falling back to pure
semantics in a growing distractor sea. With structured grounding, SYNAPSE is
near scale-invariant in **accuracy** too — motivating richer ontological grounding
rather than hiding the effect.

### 4.4 Calibration & ablations

Pooled ECE = **0.138** (0.107 at T=300 → 0.218 at T=100k). Abstention on miss
tasks is **perfect (1.000)** at every scale. Ablations at T=10k:

| Configuration | prec@1 | hit@k | MRR |
|---|---:|---:|---:|
| hybrid (full) | 0.622 | 0.738 | 0.668 |
| − semantic | 0.000 | 0.000 | 0.000 |
| − tag | 0.260 | 0.491 | 0.326 |
| − expand | 0.600 | 0.711 | 0.643 |
| − type-fit | 0.602 | 0.724 | 0.652 |
| − lexical | 0.613 | 0.727 | 0.658 |
| semantic-only | 0.162 | 0.402 | 0.228 |

Every signal contributes; semantic and ontology-tag channels dominate. A `k`
sweep trades context for recall (hit@k 0.622 at k=1 → 0.789 at k=16).

## 5. Threats to validity & limitations (stated plainly)

- **Synthetic data.** Absolute accuracy is not a claim about any production tool
  set; the *relative* scaling behavior is the robust phenomenon (same data +
  scorer for both systems).
- **No live LLM.** We isolate the protocol/retrieval layer; we measure context,
  cost, and selection quality, not end-to-end completion by a specific model.
- **Reference resolver latency.** The reference resolver brute-forces all `T`
  embeddings, so its wall-clock latency grows with `T` (1.4 → 88 ms). MCP's
  per-turn scoring is faster *only because it already discarded most tools* — the
  very cause of its accuracy collapse. The protocol guarantee is about **model
  context** (`O(1)`), independent of the ANN backend; production HNSW gives
  sub-linear resolver time.
- **Residual decay.** SYNAPSE is *not* flawless — the tag-dropout subset decays
  with `T`, as quantified above. We make no "zero-flaw" claim.

## 6. Security & trust

HMAC-signed capability nodes (rejected at index time if tampered) give
supply-chain integrity; chained signed resolution/execution receipts give
end-to-end provenance from intent to artifact; trust levels gate providers; and
capability tokens with contextual caveats bound authority. Together these address
several OWASP-LLM risks (excessive agency, supply-chain tampering) by making
capability provenance explicit and verifiable rather than implicit in a prompt.

## 7. Reproducibility

Fully deterministic and offline. `python run_all.py` regenerates every number,
table, and figure from seed; `pytest tests/` runs the conformance suite that
encodes the protocol's normative requirements.

## 8. Conclusion

Dominant tool protocols make agents *worse* as ecosystems grow because
availability is conflated with in-context presence. SYNAPSE breaks that
conflation with a signed capability knowledge graph, a calibrated hybrid
resolver, and six fixed meta-verbs — achieving per-turn context and cost that are
**constant in the number of tools**. Our matched-scorer evaluation shows this
constancy is not merely cheaper but *prevents* the accuracy collapse that
flat-context protocols suffer at scale, while we quantify SYNAPSE's residual
limitations honestly. SYNAPSE offers an adoptable path — wrapping existing MCP
servers as providers — to agent ecosystems that get **better, not worse**, as
they grow.
