// Radius graph of the GNS (FR-011-02, FR-011-13, P-011-04): the TypeScript twin of src/pitstudio/granular/graph.py.
//
// Neighbour of i iff j != i and |x_i - x_j|^2 < R^2 (strict), the squared distance in binary64 from the binary32 positions
// (reading a Float32Array yields exact binary32 values as numbers, and JS arithmetic is binary64). Lists are ordered by
// (squared distance, index), the first kMax kept, overflowing particles counted. Output arrays are identical to the Python builder.
import { InvalidGraphError } from "./errors";

export const K_MAX = 32;

export interface RadiusGraph {
  n: number;
  /** n * kMax neighbour indices, row i at i * kMax; masked-off entries hold the particle's own index. */
  index: Int32Array;
  /** n * kMax, 1 for a listed neighbour. */
  mask: Uint8Array;
  overflowCount: number;
}

const BRUTE_FORCE_BELOW = 64; // particles
const MAX_GRID_CELLS = 4_000_000;

/** Throws InvalidGraphError unless `positions` is a flat [x0, y0, x1, y1, ...] array of n >= 1 finite pairs. */
export function validatePositions(positions: Float32Array | Float64Array): number {
  if (positions.length === 0) throw new InvalidGraphError("N = 0: no particles");
  if (positions.length % 2 !== 0) throw new InvalidGraphError("positions must hold x, y pairs: odd length");
  for (let i = 0; i < positions.length; i++) {
    if (!Number.isFinite(positions[i] as number))
      throw new InvalidGraphError("positions contain a non-finite value");
  }
  return positions.length / 2;
}

export function buildRadiusGraph(
  positions: Float32Array | Float64Array,
  radius: number,
  kMax = K_MAX,
): RadiusGraph {
  const n = validatePositions(positions);
  if (!Number.isFinite(radius) || radius <= 0) {
    throw new InvalidGraphError(`the connectivity radius must be a positive finite number, got ${radius}`);
  }
  if (!Number.isInteger(kMax) || kMax < 1)
    throw new InvalidGraphError(`kMax must be a positive integer, got ${kMax}`);
  const r2 = radius * radius;
  const index = new Int32Array(n * kMax);
  const mask = new Uint8Array(n * kMax);
  for (let i = 0; i < n; i++) index.fill(i, i * kMax, (i + 1) * kMax);

  // candidate scratch, grown on demand: squared distance and index of the neighbours of the current particle
  let candD2 = new Float64Array(64);
  let candJ = new Int32Array(64);
  let count = 0;
  const push = (d2: number, j: number) => {
    if (count === candD2.length) {
      const nd = new Float64Array(count * 2);
      nd.set(candD2);
      candD2 = nd;
      const nj = new Int32Array(count * 2);
      nj.set(candJ);
      candJ = nj;
    }
    candD2[count] = d2;
    candJ[count] = j;
    count++;
  };

  const cellSize = radius * (1 + 1e-6); // a hair above R so that rounding of the cell division can never split a pair closer than R
  const grid = n >= BRUTE_FORCE_BELOW ? buildGrid(positions, n, cellSize) : null;
  let overflow = 0;
  for (let i = 0; i < n; i++) {
    count = 0;
    const xi = positions[2 * i] as number;
    const yi = positions[2 * i + 1] as number;
    if (grid === null) {
      for (let j = 0; j < n; j++) {
        if (j === i) continue;
        const dx = xi - (positions[2 * j] as number);
        const dy = yi - (positions[2 * j + 1] as number);
        const d2 = dx * dx + dy * dy;
        if (d2 < r2) push(d2, j);
      }
    } else {
      const cx = Math.floor((xi - grid.minX) / cellSize);
      const cy = Math.floor((yi - grid.minY) / cellSize);
      for (let gy = Math.max(cy - 1, 0); gy <= Math.min(cy + 1, grid.ny - 1); gy++) {
        for (let gx = Math.max(cx - 1, 0); gx <= Math.min(cx + 1, grid.nx - 1); gx++) {
          const cell = gy * grid.nx + gx;
          for (let s = grid.start[cell] as number; s < (grid.start[cell + 1] as number); s++) {
            const j = grid.order[s] as number;
            if (j === i) continue;
            const dx = xi - (positions[2 * j] as number);
            const dy = yi - (positions[2 * j + 1] as number);
            const d2 = dx * dx + dy * dy;
            if (d2 < r2) push(d2, j);
          }
        }
      }
    }
    // insertion sort by (d2, j): the lists are short (about 23 in a dense 2-D packing)
    for (let a = 1; a < count; a++) {
      const d = candD2[a] as number;
      const j = candJ[a] as number;
      let b = a - 1;
      while (
        b >= 0 &&
        ((candD2[b] as number) > d || ((candD2[b] as number) === d && (candJ[b] as number) > j))
      ) {
        candD2[b + 1] = candD2[b] as number;
        candJ[b + 1] = candJ[b] as number;
        b--;
      }
      candD2[b + 1] = d;
      candJ[b + 1] = j;
    }
    if (count > kMax) overflow++;
    const keep = Math.min(count, kMax);
    for (let k = 0; k < keep; k++) {
      index[i * kMax + k] = candJ[k] as number;
      mask[i * kMax + k] = 1;
    }
  }
  return { n, index, mask, overflowCount: overflow };
}

interface Grid {
  minX: number;
  minY: number;
  nx: number;
  ny: number;
  start: Int32Array; // nx * ny + 1 offsets into `order`
  order: Int32Array; // particle indices grouped by cell, ascending inside a cell
}

/** Uniform grid of cell size R, or null when the extent is too large for a dense grid (the caller then uses brute force). */
function buildGrid(positions: Float32Array | Float64Array, n: number, radius: number): Grid | null {
  let minX = Number.POSITIVE_INFINITY;
  let minY = Number.POSITIVE_INFINITY;
  let maxX = Number.NEGATIVE_INFINITY;
  let maxY = Number.NEGATIVE_INFINITY;
  for (let i = 0; i < n; i++) {
    const x = positions[2 * i] as number;
    const y = positions[2 * i + 1] as number;
    if (x < minX) minX = x;
    if (x > maxX) maxX = x;
    if (y < minY) minY = y;
    if (y > maxY) maxY = y;
  }
  const nxF = Math.floor((maxX - minX) / radius) + 1;
  const nyF = Math.floor((maxY - minY) / radius) + 1;
  if (!Number.isFinite(nxF) || !Number.isFinite(nyF) || nxF * nyF > MAX_GRID_CELLS) return null;
  const nx = nxF;
  const ny = nyF;
  const start = new Int32Array(nx * ny + 1);
  const cellOf = new Int32Array(n);
  for (let i = 0; i < n; i++) {
    const cx = Math.floor(((positions[2 * i] as number) - minX) / radius);
    const cy = Math.floor(((positions[2 * i + 1] as number) - minY) / radius);
    const cell = cy * nx + cx;
    cellOf[i] = cell;
    start[cell + 1] = (start[cell + 1] as number) + 1;
  }
  for (let c = 0; c < nx * ny; c++) start[c + 1] = (start[c + 1] as number) + (start[c] as number);
  const fill = start.slice(0, nx * ny);
  const order = new Int32Array(n);
  for (let i = 0; i < n; i++) {
    const cell = cellOf[i] as number;
    order[fill[cell] as number] = i;
    fill[cell] = (fill[cell] as number) + 1;
  }
  return { minX, minY, nx, ny, start, order };
}
