// Engine `mincut` (spec 018 section 7.1): the minephys.planning ultimate pit and nested pits for the browser, case C3. The pit is the
// smallest maximum-weight closure of the block precedence graph, solved as a minimum s-t cut by Dinic's algorithm (iterative, typed
// arrays). Block numbering is C order over (levels, rows, cols), level 0 at the top (T-018-071, flagged in the report).
import { rangeError, schemaError, sizeError } from "../analytical/errors";
import { asArray, asEnum, asInteger, asNumber, asObject } from "../analytical/validate";

const MAX_BLOCKS = 100000;
const MAX_CENTS = 2 ** 30;
const PATTERNS = ["1-5", "1-9"] as const;
type Pattern = (typeof PATTERNS)[number];

interface Shape {
  levels: number;
  rows: number;
  cols: number;
}

export interface Pit {
  pit_value_cents: number;
  block_count: number;
  blocks: number[];
}

function parseShape(raw: unknown, blockCountRaw: unknown): { shape: Shape; n: number } {
  const o = asObject(raw, "shape");
  const levels = asInteger(o.levels, "shape.levels", { lo: 1 });
  const rows = asInteger(o.rows, "shape.rows", { lo: 1 });
  const cols = asInteger(o.cols, "shape.cols", { lo: 1 });
  const n = levels * rows * cols;
  if (n > MAX_BLOCKS) throw sizeError(`a model of ${n} blocks is above the ${MAX_BLOCKS} cap`);
  const declared = asInteger(blockCountRaw, "block_count", { lo: 1 });
  if (declared !== n) throw schemaError(`block_count ${declared} does not match the shape (${n} blocks)`);
  return { shape: { levels, rows, cols }, n };
}

/** The offsets (dr, dc) of the blocks one level up that a block requires. */
function offsets(pattern: Pattern): Array<[number, number]> {
  if (pattern === "1-5")
    return [
      [0, 0],
      [1, 0],
      [-1, 0],
      [0, 1],
      [0, -1],
    ];
  const out: Array<[number, number]> = [];
  for (let dr = -1; dr <= 1; dr++) for (let dc = -1; dc <= 1; dc++) out.push([dr, dc]);
  return out;
}

/** Precedence arcs (block i requires block j) as parallel arrays. */
function precedence(shape: Shape, pattern: Pattern): { from: Int32Array; to: Int32Array } {
  const { levels, rows, cols } = shape;
  const offs = offsets(pattern);
  const from: number[] = [];
  const to: number[] = [];
  for (let l = 1; l < levels; l++)
    for (let r = 0; r < rows; r++)
      for (let c = 0; c < cols; c++)
        for (const [dr, dc] of offs) {
          const rr = r + dr;
          const cc = c + dc;
          if (rr < 0 || rr >= rows || cc < 0 || cc >= cols) continue;
          from.push((l * rows + r) * cols + c);
          to.push(((l - 1) * rows + rr) * cols + cc);
        }
  return { from: Int32Array.from(from), to: Int32Array.from(to) };
}

/** Smallest maximum-weight closed set: the source side of the final residual network of a Dinic maximum flow. */
function closure(values: ArrayLike<number>, arcs: { from: Int32Array; to: Int32Array }): Uint8Array {
  const n = values.length;
  const s = n;
  const t = n + 1;
  const nodes = n + 2;
  let positive = 0;
  let negative = 0;
  for (let i = 0; i < n; i++) {
    const v = values[i] as number;
    if (v > 0) positive++;
    else if (v < 0) negative++;
  }
  const inPit = new Uint8Array(n);
  if (positive === 0) return inPit;
  const e = arcs.from.length + positive + negative;
  const tails = new Int32Array(e);
  const heads = new Int32Array(e);
  const caps = new Float64Array(2 * e);
  let k = 0;
  for (let a = 0; a < arcs.from.length; a++, k++) {
    tails[k] = arcs.from[a] as number;
    heads[k] = arcs.to[a] as number;
    caps[k] = Number.POSITIVE_INFINITY;
  }
  for (let i = 0; i < n; i++) {
    const v = values[i] as number;
    if (v > 0) {
      tails[k] = s;
      heads[k] = i;
      caps[k++] = v;
    } else if (v < 0) {
      tails[k] = i;
      heads[k] = t;
      caps[k++] = -v;
    }
  }
  // half-edges 0..e-1 forward, e..2e-1 reverse, laid out by tail node (CSR)
  const start = new Int32Array(nodes + 1);
  for (let h = 0; h < e; h++) {
    const a = (tails[h] as number) + 1;
    const b = (heads[h] as number) + 1;
    start[a] = (start[a] as number) + 1;
    start[b] = (start[b] as number) + 1;
  }
  for (let u = 0; u < nodes; u++) start[u + 1] = (start[u + 1] as number) + (start[u] as number);
  const fill = start.slice(0, nodes);
  const slot = new Int32Array(2 * e);
  const head = new Int32Array(2 * e);
  const cap = new Float64Array(2 * e);
  for (let h = 0; h < e; h++) {
    const tail = tails[h] as number;
    const f = fill[tail] as number;
    fill[tail] = f + 1;
    slot[h] = f;
    head[f] = heads[h] as number;
    cap[f] = caps[h] as number;
  }
  for (let h = 0; h < e; h++) {
    const hd = heads[h] as number;
    const f = fill[hd] as number;
    fill[hd] = f + 1;
    slot[e + h] = f;
    head[f] = tails[h] as number;
    cap[f] = 0;
  }
  const rev = new Int32Array(2 * e);
  for (let h = 0; h < e; h++) {
    rev[slot[h] as number] = slot[e + h] as number;
    rev[slot[e + h] as number] = slot[h] as number;
  }
  const level = new Int32Array(nodes);
  const queue = new Int32Array(nodes);
  const it = new Int32Array(nodes);
  const path = new Int32Array(nodes);
  const stack = new Int32Array(nodes + 1);
  for (;;) {
    level.fill(-1);
    level[s] = 0;
    let qh = 0;
    let qt = 0;
    queue[qt++] = s;
    let found = false;
    while (qh < qt && !found) {
      const u = queue[qh++] as number;
      const lu = (level[u] as number) + 1;
      for (let a = start[u] as number; a < (start[u + 1] as number); a++) {
        if ((cap[a] as number) > 0) {
          const v = head[a] as number;
          if ((level[v] as number) < 0) {
            level[v] = lu;
            queue[qt++] = v;
            if (v === t) found = true;
          }
        }
      }
    }
    if (!found) break;
    // blocking flow: iterative depth-first search with current-arc pointers
    for (let u = 0; u < nodes; u++) it[u] = start[u] as number;
    let depth = 0;
    let u = s;
    stack[0] = s;
    for (;;) {
      if (u === t) {
        let flow = Number.POSITIVE_INFINITY;
        for (let d = 0; d < depth; d++) flow = Math.min(flow, cap[path[d] as number] as number);
        let cut = -1;
        for (let d = 0; d < depth; d++) {
          const a = path[d] as number;
          cap[a] = (cap[a] as number) - flow;
          cap[rev[a] as number] = (cap[rev[a] as number] as number) + flow;
          if (cut < 0 && (cap[a] as number) <= 0) cut = d;
        }
        depth = cut;
        u = stack[depth] as number;
        continue;
      }
      let a = it[u] as number;
      const end = start[u + 1] as number;
      const lu = (level[u] as number) + 1;
      while (a < end && !((cap[a] as number) > 0 && level[head[a] as number] === lu)) a++;
      it[u] = a;
      if (a < end) {
        path[depth] = a;
        depth++;
        u = head[a] as number;
        stack[depth] = u;
      } else {
        if (u === s) break;
        level[u] = -1;
        depth--;
        u = stack[depth] as number;
        it[u] = (it[u] as number) + 1;
      }
    }
  }
  for (let i = 0; i < n; i++) inPit[i] = (level[i] as number) >= 0 ? 1 : 0;
  return inPit;
}

function toPit(inPit: Uint8Array, values: ArrayLike<number>): Pit {
  const blocks: number[] = [];
  let sum = 0;
  for (let i = 0; i < inPit.length; i++)
    if (inPit[i]) {
      blocks.push(i);
      sum += values[i] as number;
    }
  return { pit_value_cents: sum, block_count: blocks.length, blocks };
}

export function ultimate_pit(args: Record<string, unknown>): Pit {
  const a = asObject(args, "args");
  const { shape, n } = parseShape(a.shape, a.block_count);
  const pattern = asEnum(a.pattern, "pattern", PATTERNS);
  const list = asArray(a.values_cents, "values_cents");
  if (list.length !== n) throw schemaError(`values_cents holds ${list.length} values for ${n} blocks`);
  const values = new Float64Array(n);
  list.forEach((v, i) => {
    values[i] = asInteger(v, `values_cents[${i}]`, { lo: -MAX_CENTS, hi: MAX_CENTS });
  });
  return toPit(closure(values, precedence(shape, pattern)), values);
}

export interface Shell extends Pit {
  revenue_factor: number;
}

export function nested_shells(args: Record<string, unknown>): { shells: Shell[] } {
  const a = asObject(args, "args");
  const { shape, n } = parseShape(a.shape, a.block_count);
  const pattern = asEnum(a.pattern, "pattern", PATTERNS);
  const tonnage = asArray(a.tonnage_kg, "tonnage_kg");
  const grade = asArray(a.grade, "grade");
  if (tonnage.length !== n || grade.length !== n)
    throw schemaError(`tonnage_kg and grade need ${n} entries (got ${tonnage.length} and ${grade.length})`);
  const t = tonnage.map((v, i) => asNumber(v, `tonnage_kg[${i}]`, { lo: 0 }));
  const g = grade.map((v, i) => asNumber(v, `grade[${i}]`, { lo: 0, hi: 1 }));
  const price = asNumber(a.price_cents_per_kg, "price_cents_per_kg", { lo: 0 });
  const selling = asNumber(a.selling_cost_cents_per_kg, "selling_cost_cents_per_kg", { lo: 0 });
  if (!(price > selling)) throw rangeError("price_cents_per_kg must exceed selling_cost_cents_per_kg");
  const recovery = asNumber(a.recovery, "recovery", { lo: 0, loOpen: true, hi: 1 });
  const processing = asNumber(a.processing_cost_cents_per_kg, "processing_cost_cents_per_kg", { lo: 0 });
  const mining = asNumber(a.mining_cost_cents_per_kg, "mining_cost_cents_per_kg", { lo: 0 });
  const rf = asArray(a.revenue_factors, "revenue_factors", 1).map((v, i) =>
    asNumber(v, `revenue_factors[${i}]`, { lo: 0, loOpen: true, hi: 2 }),
  );
  for (let i = 1; i < rf.length; i++)
    if (!((rf[i] as number) > (rf[i - 1] as number)))
      throw rangeError("revenue_factors must be strictly increasing");
  const arcs = precedence(shape, pattern);
  const unit = g.map((gi) => gi * recovery * (price - selling));
  const shells: Shell[] = rf.map((factor) => {
    const values = new Float64Array(n);
    for (let i = 0; i < n; i++) {
      const ti = t[i] as number;
      // v_i(lambda) = max(T [lambda g r (p - s) - c_p], 0) - T c_m, to integer cents (the pit value is an integer)
      values[i] = Math.round(Math.max(ti * (factor * (unit[i] as number) - processing), 0) - ti * mining);
    }
    return { revenue_factor: factor, ...toPit(closure(values, arcs), values) };
  });
  return { shells };
}
