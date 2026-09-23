# Jev as a reranker over SYNAPSE shortlists

This experiment tests whether [Jev](https://vercel.com/ai-gateway/models/jev) (TypeSafe AI's evaluation
model, called through the Vercel AI Gateway as `typesafe-ai/jev`) improves capability selection when it
picks one tool from a bounded shortlist, compared with the SYNAPSE resolver's own top-1.

It reuses the paper's catalogue generator and task suite unchanged (`benchmarks/`), so the tasks, gold
labels and shortlists match the main experiments.

## Arms

Each Jev arm is one `choice` question per task. The options are the shortlist plus a `none` option.

| arm | candidates given to Jev |
|---|---|
| `synapse8` | SYNAPSE resolver top-8 (`ResolverConfig(k=8)`) |
| `synapse32` | SYNAPSE resolver top-32 |
| `lexical32` | top-32 from the MCP baseline's scorer (a plain lexical pre-filter) |
| `synapse_only` | no Jev: the resolver's own top-1 (reference) |

When the resolver returns a grounded miss (empty shortlist), the SYNAPSE arms abstain without calling Jev.

Jev sees the same inputs as the resolver: the query, ontology tags (when present), and available input
types. Each option is `summary. tags. consumes -> produces`. Option keys are opaque (`o0`, `o1`, …)
because capability ids such as `security.probe.sql_injection.checker` would leak the answer.

A fourth arm, `full` (a Jev-only tournament over the whole catalogue in chunks of 200, because a Choice
is capped at 255 options), is implemented but **was not completed** because of upstream rate limiting.

## Results (seed 1)

Full tables, including the per-tag split, are in [`results/summary.md`](results/summary.md). hit@1 is
over 90 real tasks; all arms abstained correctly on all 5 should-miss tasks.

| arm | T = 300 | T = 1000 | T = 1000, when gold is in the shortlist |
|---|---:|---:|---:|
| `synapse_only` | **0.811** | **0.822** | **0.914** |
| `synapse8` | 0.633 | 0.411 | 0.457 |
| `synapse32` | 0.567 | 0.389 | 0.432 |
| `lexical32` | 0.578 | 0.100 | 0.429 |

## What this does and does not show

1. **Reranking with Jev lowered accuracy at both sizes.** The resolver's top-1 beats every Jev arm, and
   a longer shortlist makes Jev slightly worse (8 → 32).
2. **Most Jev errors are look-alikes.** At T = 1000, 31 of `synapse8`'s 44 errors (with the gold in the
   list) pick a capability with the same verb and object as the gold, usually with the same tag. The
   gold differs only in its output type (`type.probe_result` / `type.record`), which no query states.
   The resolver separates them through graph structure (the gold's `composes_with` edge to its stage-2
   capability and type-fit), which Jev never receives. This is partly a **property of the benchmark**:
   for many untagged queries the correct answer can't be recovered from text alone. It should be read
   as "text-only reranking can't use the structural signal", not as a general verdict on Jev.
3. **The `lexical32` drop at T = 1000 is a shortlist-recall failure.** The lexical top-32 contains the gold
   in only 23% of tasks; when it does, Jev's accuracy (0.429) matches the SYNAPSE arms.
4. **Abstention is good.** Jev chose `none` on 5/5 impossible tasks in every arm, and rarely abstained
   wrongly when the gold was present (0–3 tasks per arm).

## Reproducibility issues found along the way

- **SYNAPSE resolver output depends on `PYTHONHASHSEED`.** The resolver iterates over sets of string
  ids, so tie-breaking changes between Python processes. At T = 1000 two exports changed the k=32
  shortlist membership for 12 of 95 tasks, and `synapse_only` hit@1 was 72, 74 and 74 / 90 under hash
  seeds 0, 1 and 2. `export_catalog.py` pins `PYTHONHASHSEED=0`. The main `run_all.py` does not, so the
  paper's numbers carry roughly ±1 pp of unreported variation. (Not fixed in this PR.)
- **Jev is not bit-deterministic.** Identical requests returned slightly different probabilities
  (e.g. 0.98 vs 0.97), which flipped 6 task outcomes at T = 300 before in-flight requests were
  de-duplicated. The harness now sends each unique request once and reads every answer from cache.
- **Model version is not pinned.** The Gateway reports only `typesafe-ai/jev`, with no version, so
  results may drift if the model behind that alias changes.

## Operational notes

- Upstream capacity was the bottleneck: across the main runs, 230 new requests needed 428 retries after
  HTTP 429 ("upstream provider is currently experiencing high demand").
- Jev was free on the Gateway during these runs (promotional pricing to 2026-09-25), but the Gateway
  requires a card on file before it serves any request.

## Reproduce

```bash
cd experiments/jev
npm ci
python export_catalog.py --T 300 1000 --seeds 1      # regenerates data/ (pins PYTHONHASHSEED=0)
node jev_bench.mjs --data data/T300_s1.json --arms synapse8,synapse32,lexical32
node jev_bench.mjs --data data/T1000_s1.json --arms synapse8,synapse32,lexical32
python summarize.py results/T300_s1_synapse8-synapse32-lexical32.json results/T1000_s1_synapse8-synapse32-lexical32.json
```

`jev_cache.jsonl` holds every Jev response used. On first run it is unpacked into `cache/`, so the
commands above reproduce `results/` byte-for-byte with **no API key and no network calls**. To extend
the grid (more seeds, larger T, the `full` arm), put `AI_GATEWAY_API_KEY=...` in `.env` and run with
`node --env-file=.env jev_bench.mjs ...`; only requests not already cached are sent.

## Limitations

One seed, two catalogue sizes, a synthetic catalogue, and a single prompt wording. Jev-alone at scale
(`full`) and giving Jev resolver scores or type constraints are not yet measured.
