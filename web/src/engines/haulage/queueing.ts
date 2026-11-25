// M1 analytical fleet sizing in the browser (spec 007, FR-007-15, FR-007-16): the match factor, the finite-source queue
// M/M/1//N, the open M/M/c queue and exact mean-value analysis. The port equals `minephys.haulage` on the committed golden
// vectors (tests/fixtures/haulage/m1_goldens.json) within rtol 1e-12, atol 1e-15. Every function returns a typed `Result`,
// never throws, and never returns NaN or Infinity: a hostile input names its first failing field (in the order of the
// argument list), and `Unstable` is returned for an open queue with rho >= 1 once the arguments are valid.
// No call to `Math.pow`: the finite-source normalising sum is evaluated by Horner's rule, a running product.

export type Result<T> =
  | { ok: true; value: T }
  | { ok: false; kind: "InvalidInput"; field: string }
  | { ok: false; kind: "Unstable" };

const MAX_TRUCKS = 400;

const bad = (field: string): { ok: false; kind: "InvalidInput"; field: string } => ({
  ok: false,
  kind: "InvalidInput",
  field,
});

const isPositive = (x: unknown): x is number => typeof x === "number" && Number.isFinite(x) && x > 0;
const isCount = (x: unknown, cap?: number): x is number =>
  typeof x === "number" &&
  Number.isFinite(x) &&
  Number.isInteger(x) &&
  x >= 1 &&
  (cap === undefined || x <= cap);
const allPositive = (xs: unknown): xs is number[] =>
  Array.isArray(xs) && xs.length > 0 && xs.every(isPositive);

function finiteOrNull(...xs: number[]): boolean {
  return xs.every((x) => Number.isFinite(x));
}

export function matchFactor(i: {
  n_trucks: number;
  n_loaders: number;
  load_time: number;
  cycle_time: number;
}): Result<number> {
  if (!isCount(i.n_trucks, MAX_TRUCKS)) return bad("n_trucks");
  if (!isCount(i.n_loaders)) return bad("n_loaders");
  if (!isPositive(i.load_time)) return bad("load_time");
  if (!isPositive(i.cycle_time)) return bad("cycle_time");
  const mf = (i.n_trucks * i.load_time) / (i.n_loaders * i.cycle_time);
  return finiteOrNull(mf) ? { ok: true, value: mf } : bad("cycle_time");
}

export type FiniteSource = {
  idle_probability: number;
  utilisation: number;
  throughput: number;
  mean_at_loader: number;
  mean_time_at_loader: number;
};

export function finiteSourceQueue(i: {
  n_trucks: number;
  travel_rate: number;
  service_rate: number;
}): Result<FiniteSource> {
  if (!isCount(i.n_trucks, MAX_TRUCKS)) return bad("n_trucks");
  if (!isPositive(i.travel_rate)) return bad("travel_rate");
  if (!isPositive(i.service_rate)) return bad("service_rate");
  const n = i.n_trucks;
  const a = i.travel_rate / i.service_rate;
  // sum_{k=0..N} N!/(N-k)! a^k = 1 + N a (1 + (N-1) a (1 + ... (1 + a)))
  let sum = 1;
  for (let j = 1; j <= n; j++) sum = 1 + j * a * sum;
  const idle = Number.isFinite(sum) ? 1 / sum : 0;
  const util = 1 - idle;
  const x = i.service_rate * util;
  const atLoader = n - x / i.travel_rate;
  const value = {
    idle_probability: idle,
    utilisation: util,
    throughput: x,
    mean_at_loader: atLoader,
    mean_time_at_loader: atLoader / x,
  };
  return finiteOrNull(...Object.values(value)) ? { ok: true, value } : bad("service_rate");
}

export type Mmc = {
  utilisation: number;
  erlang_c: number;
  mean_wait: number;
  mean_queue_length: number;
  mean_time_in_system: number;
  mean_in_system: number;
};

export function mmcQueue(i: { arrival_rate: number; service_rate: number; servers: number }): Result<Mmc> {
  if (!isPositive(i.arrival_rate)) return bad("arrival_rate");
  if (!isPositive(i.service_rate)) return bad("service_rate");
  if (!isCount(i.servers)) return bad("servers");
  const c = i.servers;
  if (i.arrival_rate >= c * i.service_rate) return { ok: false, kind: "Unstable" };
  const a = i.arrival_rate / i.service_rate;
  let b = 1; // Erlang B recursion B_k = a B_{k-1} / (k + a B_{k-1})
  for (let k = 1; k <= c; k++) b = (a * b) / (k + a * b);
  const rho = a / c;
  const erlangC = b / (1 - rho * (1 - b));
  const wq = erlangC / (c * i.service_rate - i.arrival_rate);
  const w = wq + 1 / i.service_rate;
  const value = {
    utilisation: rho,
    erlang_c: erlangC,
    mean_wait: wq,
    mean_queue_length: i.arrival_rate * wq,
    mean_time_in_system: w,
    mean_in_system: i.arrival_rate * w,
  };
  return finiteOrNull(...Object.values(value)) ? { ok: true, value } : bad("arrival_rate");
}

export type Mva = {
  throughput: number[];
  residence_time: number[];
  queue_length: number[];
  utilisation: number[];
};

export function meanValueAnalysis(i: {
  population: number;
  service_time: number[];
  visit_ratio: number[];
  station_type: ("queue" | "delay")[];
}): Result<Mva> {
  if (!isCount(i.population, MAX_TRUCKS)) return bad("population");
  if (!allPositive(i.service_time)) return bad("service_time");
  if (!allPositive(i.visit_ratio) || i.visit_ratio.length !== i.service_time.length)
    return bad("visit_ratio");
  if (
    !Array.isArray(i.station_type) ||
    i.station_type.length !== i.service_time.length ||
    !i.station_type.every((t) => t === "queue" || t === "delay")
  )
    return bad("station_type");
  const s = i.service_time;
  const v = i.visit_ratio;
  const m = s.length;
  let q: number[] = new Array(m).fill(0);
  const throughput: number[] = [];
  let r: number[] = new Array(m).fill(0);
  for (let k = 1; k <= i.population; k++) {
    r = s.map((st, j) => (i.station_type[j] === "queue" ? st * (1 + (q[j] as number)) : st));
    let total = 0;
    for (let j = 0; j < m; j++) total += (v[j] as number) * (r[j] as number);
    const x = k / total;
    throughput.push(x);
    q = r.map((rj, j) => (v[j] as number) * x * rj);
  }
  const x = throughput[throughput.length - 1] as number;
  const value = {
    throughput,
    residence_time: r,
    queue_length: q,
    utilisation: s.map((st, j) => (v[j] as number) * x * st),
  };
  const all = [...throughput, ...r, ...q, ...value.utilisation];
  return finiteOrNull(...all) ? { ok: true, value } : bad("service_time");
}
