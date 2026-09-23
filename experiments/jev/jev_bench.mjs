// Jev vs SYNAPSE benchmark harness.
// Usage: node --env-file=.env jev_bench.mjs --data data/T300_s1.json --arms synapse8,synapse32,lexical32,full [--limit N] [--chunk 200] [--conc 4]
// Every Jev response is cached in cache/ (keyed by request hash) so reruns are free and reproducible.
import { experimental_evaluate as evaluate } from 'ai';
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';

const MODEL = 'typesafe-ai/jev';
const NONE = 'none';
const INSTRUCTIONS =
  'Select the single capability that best accomplishes the request, using the ontology tags and ' +
  'available input types when given. Choose "none" if no listed capability can accomplish it.';

const args = Object.fromEntries(
  process.argv.slice(2).reduce((acc, a, i, arr) => (a.startsWith('--') ? [...acc, [a.slice(2), arr[i + 1]]] : acc), []),
);
const dataPath = args.data ?? 'data/T300_s1.json';
const arms = (args.arms ?? 'synapse8,synapse32,lexical32').split(',');
const limit = args.limit ? Number(args.limit) : Infinity;
const CHUNK = Number(args.chunk ?? 200); // Choice hard limit is 255 options incl. "none"
const CONC = Number(args.conc ?? 4);

const data = JSON.parse(fs.readFileSync(dataPath, 'utf8'));
const caps = new Map(data.capabilities.map(c => [c.id, c]));
const tasks = data.tasks.slice(0, limit);
// Seed cache/ from the committed jev_cache.jsonl so published numbers reproduce without API calls.
if (!fs.existsSync('cache') && fs.existsSync('jev_cache.jsonl')) {
  fs.mkdirSync('cache');
  for (const line of fs.readFileSync('jev_cache.jsonl', 'utf8').split('\n').filter(Boolean)) {
    const { key, response } = JSON.parse(line);
    fs.writeFileSync(path.join('cache', `${key}.json`), JSON.stringify(response));
  }
}
fs.mkdirSync('cache', { recursive: true });
fs.mkdirSync('results', { recursive: true });

const describe = c =>
  `${c.summary}. tags: ${c.tags.join(', ') || '-'}. consumes: ${c.consumes.join(', ')} -> produces: ${c.produces.join(', ')}`;

const stateFor = t => ({
  request: t.query,
  ontology_tags: t.tags,
  available_input_types: t.initial_types,
});

let nReq = 0, nCached = 0, inTok = 0, outTok = 0, n429 = 0, nFailed = 0;

// Throttle concurrent network calls.
let active = 0;
const queue = [];
const acquire = () => new Promise(r => (active < CONC ? (active++, r()) : queue.push(r)));
const release = () => (queue.length ? queue.shift()() : active--);

// Identical requests in flight share one call: Jev is not bit-deterministic, so each unique
// request must be answered exactly once for results to be a pure function of the cache.
const inflight = new Map();

// One Choice over candidate ids. Options are opaque keys (o0, o1, ...) so ids can't leak the answer.
async function choose(task, ids) {
  const keys = ids.map((_, i) => `o${i}`);
  const criteria = Object.fromEntries(ids.map((id, i) => [keys[i], describe(caps.get(id))]));
  criteria[NONE] = 'None of the listed capabilities can accomplish the request.';
  const req = { model: MODEL, state: stateFor(task), questions: { pick: { type: 'choice', instructions: INSTRUCTIONS, criteria } } };
  const hash = createHash('sha256').update(JSON.stringify(req)).digest('hex').slice(0, 24);
  const file = path.join('cache', `${hash}.json`);

  let ans;
  if (fs.existsSync(file)) {
    ans = JSON.parse(fs.readFileSync(file, 'utf8'));
    nCached++;
  } else if (inflight.has(hash)) {
    ans = await inflight.get(hash);
    if (!ans) throw new Error('shared request failed');
  } else {
    let settle;
    inflight.set(hash, new Promise((res, rej) => (settle = { res, rej })).catch(() => null));
    await acquire();
    let t0;
    try {
      let r;
      for (let attempt = 0; ; attempt++) {
        t0 = performance.now();
        try {
          r = await evaluate({ ...req, maxRetries: 0 });
          break;
        } catch (e) {
          if (e.statusCode !== 429 && e.statusCode < 500 || attempt >= 10) throw e;
          n429++;
          const wait = Math.min(60000, 2000 * 2 ** attempt) * (0.5 + Math.random());
          console.error(`[${new Date().toISOString().slice(11, 19)}] ${task.task_id} ${ids.length} opts: ${e.statusCode}, retry ${attempt + 1} in ${Math.round(wait / 1000)}s`);
          await new Promise(res => setTimeout(res, wait));
        }
      }
      ans = {
        choice: r.answers.pick.choice,
        probabilities: r.answers.pick.probabilities ?? null,
        usage: r.usage,
        modelId: r.response.modelId,
        latency_ms: performance.now() - t0,
      };
      fs.writeFileSync(file, JSON.stringify(ans));
      nReq++;
      settle.res(ans);
    } catch (e) {
      settle.rej(e);
      console.error(`\n[${task.task_id}] ${ids.length} options -> ${e.name}: ${e.message}`);
      if (e.responseBody) console.error('  body:', String(e.responseBody).slice(0, 500));
      throw e;
    } finally {
      release();
    }
  }
  inTok += ans.usage?.inputTokens ?? 0;
  outTok += ans.usage?.outputTokens ?? 0;
  const id = ans.choice === NONE ? null : ids[keys.indexOf(ans.choice)];
  const conf = ans.probabilities ? ans.probabilities[ans.choice] : null;
  const pNone = ans.probabilities ? ans.probabilities[NONE] ?? 0 : null;
  return { id, conf, pNone, latency: ans.latency_ms ?? 0, calls: 1 };
}

// Tournament over the whole catalogue: chunk, keep each chunk's winner, repeat until one Choice fits.
async function tournament(task, ids) {
  let calls = 0, latency = 0;
  let pool = ids;
  while (pool.length > CHUNK) {
    const chunks = [];
    for (let i = 0; i < pool.length; i += CHUNK) chunks.push(pool.slice(i, i + CHUNK));
    const winners = await Promise.all(chunks.map(c => choose(task, c)));
    calls += winners.length;
    latency += Math.max(...winners.map(w => w.latency)); // chunks run in parallel
    pool = winners.map(w => w.id).filter(Boolean);
  }
  if (!pool.length) return { id: null, conf: null, pNone: 1, calls, latency };
  const fin = await choose(task, pool);
  return { ...fin, calls: calls + 1, latency: latency + fin.latency };
}

// Shuffle the full catalogue once per file (fixed seed) so chunk boundaries don't follow generation order.
function seededShuffle(arr, seed) {
  const a = [...arr];
  let s = seed >>> 0;
  for (let i = a.length - 1; i > 0; i--) {
    s = (s * 1664525 + 1013904223) >>> 0;
    const j = s % (i + 1);
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}
const allIds = seededShuffle([...caps.keys()], 7);

const ARMS = {
  synapse8: t => choose(t, t.shortlists.synapse_k8.ids),
  synapse32: t => choose(t, t.shortlists.synapse_k32.ids),
  lexical32: t => choose(t, t.shortlists.lexical_k32.ids),
  full: t => tournament(t, allIds),
};

const rows = [];
for (const arm of arms) {
  if (!ARMS[arm]) throw new Error(`unknown arm ${arm}`);
  let done = 0;
  await Promise.all(
    tasks.map(async t => {
      const shortlistEmpty = arm !== 'full' && !t.shortlists[{ synapse8: 'synapse_k8', synapse32: 'synapse_k32', lexical32: 'lexical_k32' }[arm]].ids.length;
      let r;
      try {
        r = shortlistEmpty ? { id: null, conf: null, pNone: null, calls: 0, latency: 0 } : await ARMS[arm](t);
      } catch {
        nFailed++; // excluded from metrics; rerun later picks it up (successful calls are cached)
        return;
      }
      rows.push({
        T: data.T, seed: data.seed, arm, task: t.task_id, variant: t.variant, has_tag: t.tags.length ? 1 : 0,
        should_miss: t.should_miss ? 1 : 0, gold: t.gold, pred: r.id,
        correct: t.should_miss ? (r.id === null ? 1 : 0) : (r.id === t.gold ? 1 : 0),
        conf: r.conf, p_none: r.pNone, calls: r.calls, latency_ms: Math.round(r.latency),
      });
      if (++done % 10 === 0 || done === tasks.length)
        console.log(`[${new Date().toISOString().slice(11, 19)}] ${arm}: ${done}/${tasks.length}`);
    }),
  );
}

// SYNAPSE resolver alone (no Jev), from the exported shortlist, for side-by-side comparison.
for (const t of tasks) {
  const s = t.shortlists.synapse_k8;
  const pred = s.grounded_miss || !s.ids.length ? null : s.ids[0];
  rows.push({
    T: data.T, seed: data.seed, arm: 'synapse_only', task: t.task_id, variant: t.variant, has_tag: t.tags.length ? 1 : 0,
    should_miss: t.should_miss ? 1 : 0, gold: t.gold, pred,
    correct: t.should_miss ? (pred === null ? 1 : 0) : (pred === t.gold ? 1 : 0),
    conf: s.conf[0] ?? null, p_none: null, calls: 0, latency_ms: 0,
  });
}

rows.sort((a, b) => a.arm.localeCompare(b.arm) || a.task.localeCompare(b.task));
const out = `results/${path.basename(dataPath, '.json')}_${arms.join('-')}.json`;
fs.writeFileSync(out, JSON.stringify(rows, null, 1));

// Summary
const mean = xs => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : NaN);
function ece(rs) {
  const r = rs.filter(x => x.conf != null);
  if (!r.length) return NaN;
  let e = 0;
  for (let b = 0; b < 10; b++) {
    const bin = r.filter(x => x.conf > b / 10 && x.conf <= (b + 1) / 10 || (b === 0 && x.conf === 0));
    if (bin.length) e += (bin.length / r.length) * Math.abs(mean(bin.map(x => x.correct)) - mean(bin.map(x => x.conf)));
  }
  return e;
}
console.log(`\nT=${data.T} seed=${data.seed}  tasks=${tasks.length}  new requests=${nReq} cached=${nCached} 429-retries=${n429} failed-tasks=${nFailed}  tokens in/out=${inTok}/${outTok}`);
console.table(
  [...arms, 'synapse_only'].map(arm => {
    const r = rows.filter(x => x.arm === arm);
    const real = r.filter(x => !x.should_miss);
    return {
      arm,
      'hit@1': mean(real.map(x => x.correct)).toFixed(3),
      'hit@1 tag': mean(real.filter(x => x.has_tag).map(x => x.correct)).toFixed(3),
      'hit@1 no-tag': mean(real.filter(x => !x.has_tag).map(x => x.correct)).toFixed(3),
      'false abstain': mean(real.map(x => (x.pred === null ? 1 : 0))).toFixed(3),
      'miss abstain': mean(r.filter(x => x.should_miss).map(x => x.correct)).toFixed(3),
      ECE: ece(real).toFixed(3),
      'calls/task': mean(r.map(x => x.calls)).toFixed(1),
      'lat ms': Math.round(mean(r.map(x => x.latency_ms))),
    };
  }),
);
console.log(`rows -> ${out}`);
