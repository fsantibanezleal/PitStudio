// Replay shard reader (FR-018-45, DC-018-03). A shard is read whole or not at all: a header that fails the schema, a payload
// whose byte length is not frames x items x channels x 2 (x 4 for float32), or a code outside the header's code range
// rejects it with E_SCHEMA, and the view shows the poster frame.
import { validateShardHeader } from "~/contracts/validators/replay-shard.js";

export interface ShardChannel {
  name: string;
  unit: string;
  min: number;
  max: number;
}

export type ShardResult =
  | {
      ok: true;
      kind: string;
      fps: number;
      frames: number;
      items: number;
      channels: ShardChannel[];
      values: Float64Array;
    }
  | { ok: false; code: "E_SCHEMA"; message: string };

interface Header {
  kind: string;
  encoding: "raw16" | "png16" | "float32";
  code_type?: "int16" | "uint16";
  code_range?: { min: number; max: number };
  fps: number;
  frames: { start: number; count: number };
  items: number;
  channels: ShardChannel[];
  grid?: { width: number; height: number };
  payload: { bytes: number };
}

const reject = (message: string): ShardResult => ({ ok: false, code: "E_SCHEMA", message });

/** Affine decode: min + (code - code_range.min) * (max - min) / (code_range.max - code_range.min). */
export function decodeCode(
  header: {
    code_type: "int16" | "uint16";
    code_range: { min: number; max: number };
    channels: Array<{ min: number; max: number }>;
  },
  channel: number,
  code: number,
): number {
  const ch = header.channels[channel] as { min: number; max: number };
  const { min, max } = header.code_range;
  return ch.min + ((code - min) * (ch.max - ch.min)) / (max - min);
}

function bytesOf(payload: unknown): Uint8Array | null {
  if (payload instanceof Uint8Array) return payload;
  if (payload instanceof ArrayBuffer) return new Uint8Array(payload);
  return null;
}

function checkHeader(header: unknown): { header: Header } | { error: ShardResult } {
  try {
    if (header === null || typeof header !== "object" || Array.isArray(header)) {
      return { error: reject("the shard header is not an object") };
    }
    if (!validateShardHeader(header)) {
      const first = validateShardHeader.errors?.[0];
      return {
        error: reject(
          `the shard header fails DC-018-03 (${first?.keyword ?? "schema"} at ${first?.instancePath || "/"})`,
        ),
      };
    }
    return { header: header as Header };
  } catch {
    return { error: reject("the shard header could not be read") };
  }
}

function layout(h: Header) {
  return { values: h.frames.count * h.items * h.channels.length, channels: h.channels.length };
}

function decodeRaw16(h: Header, payload: Uint8Array): ShardResult {
  const { values: count, channels } = layout(h);
  const bytesPerValue = h.encoding === "float32" ? 4 : 2;
  if (payload.byteLength !== count * bytesPerValue) {
    return reject(
      `the payload has ${payload.byteLength} bytes, frames x items x channels x ${bytesPerValue} is ${count * bytesPerValue}`,
    );
  }
  if (payload.byteLength !== h.payload.bytes) {
    return reject(`the payload has ${payload.byteLength} bytes, the header declares ${h.payload.bytes}`);
  }
  const dv = new DataView(payload.buffer, payload.byteOffset, payload.byteLength);
  const values = new Float64Array(count);
  if (h.encoding === "float32") {
    for (let i = 0; i < count; i++) {
      const v = dv.getFloat32(i * 4, true);
      if (!Number.isFinite(v)) return reject(`a Float32 value is not finite at index ${i}`);
      values[i] = v;
    }
  } else {
    const signed = h.code_type === "int16";
    const range = h.code_range as { min: number; max: number };
    const span = {
      code_type: h.code_type as "int16" | "uint16",
      code_range: range,
      channels: h.channels,
    };
    for (let i = 0; i < count; i++) {
      const code = signed ? dv.getInt16(i * 2, true) : dv.getUint16(i * 2, true);
      if (code < range.min || code > range.max)
        return reject(`a code lies outside the declared code range at index ${i}`);
      values[i] = decodeCode(span, i % channels, code);
    }
  }
  return {
    ok: true,
    kind: h.kind,
    fps: h.fps,
    frames: h.frames.count,
    items: h.items,
    channels: h.channels,
    values,
  };
}

/** Reads a raw16 or float32 shard. Never throws. A png16 tile goes through `readShardAsync`. */
export function readShard(header: unknown, payload: ArrayBuffer | Uint8Array): ShardResult {
  const checked = checkHeader(header);
  if ("error" in checked) return checked.error;
  const bytes = bytesOf(payload);
  if (!bytes) return reject("the payload is not a byte buffer");
  if (checked.header.encoding === "png16") return reject("a png16 tile is decoded by readShardAsync");
  try {
    return decodeRaw16(checked.header, bytes);
  } catch {
    return reject("the payload could not be decoded");
  }
}

// --- 16-bit greyscale PNG tiles (encoding "png16") ---------------------------------------------------------------------

const PNG_SIGNATURE = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];

async function inflate(data: Uint8Array): Promise<Uint8Array> {
  const stream = new Blob([data as BlobPart]).stream().pipeThrough(new DecompressionStream("deflate"));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

function paeth(a: number, b: number, c: number): number {
  const p = a + b - c;
  const pa = Math.abs(p - a);
  const pb = Math.abs(p - b);
  const pc = Math.abs(p - c);
  return pa <= pb && pa <= pc ? a : pb <= pc ? b : c;
}

/** Decodes a 16-bit greyscale PNG into big-endian codes (PNG byte order). */
async function decodePng16(
  bytes: Uint8Array,
): Promise<{ width: number; height: number; codes: Uint16Array } | null> {
  for (let i = 0; i < 8; i++) if (bytes[i] !== PNG_SIGNATURE[i]) return null;
  const dv = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  let pos = 8;
  let width = 0;
  let height = 0;
  const idat: Uint8Array[] = [];
  while (pos + 8 <= bytes.length) {
    const length = dv.getUint32(pos);
    const type = String.fromCharCode(...bytes.subarray(pos + 4, pos + 8));
    const body = bytes.subarray(pos + 8, pos + 8 + length);
    if (type === "IHDR") {
      width = dv.getUint32(pos + 8);
      height = dv.getUint32(pos + 12);
      const depth = bytes[pos + 16];
      const colour = bytes[pos + 17];
      const interlace = bytes[pos + 20];
      if (depth !== 16 || colour !== 0 || interlace !== 0) return null;
    } else if (type === "IDAT") {
      idat.push(body);
    } else if (type === "IEND") {
      break;
    }
    pos += 12 + length;
  }
  if (width === 0 || height === 0 || width > 4096 || height > 4096) return null;
  const joined = new Uint8Array(idat.reduce((n, c) => n + c.length, 0));
  let at = 0;
  for (const chunk of idat) {
    joined.set(chunk, at);
    at += chunk.length;
  }
  const raw = await inflate(joined);
  const stride = width * 2;
  if (raw.length !== (stride + 1) * height) return null;
  const out = new Uint8Array(stride * height);
  for (let y = 0; y < height; y++) {
    const filter = raw[y * (stride + 1)] as number;
    for (let x = 0; x < stride; x++) {
      const cur = raw[y * (stride + 1) + 1 + x] as number;
      const left = x >= 2 ? (out[y * stride + x - 2] as number) : 0;
      const up = y > 0 ? (out[(y - 1) * stride + x] as number) : 0;
      const upLeft = x >= 2 && y > 0 ? (out[(y - 1) * stride + x - 2] as number) : 0;
      let value: number;
      if (filter === 0) value = cur;
      else if (filter === 1) value = cur + left;
      else if (filter === 2) value = cur + up;
      else if (filter === 3) value = cur + ((left + up) >> 1);
      else if (filter === 4) value = cur + paeth(left, up, upLeft);
      else return null;
      out[y * stride + x] = value & 0xff;
    }
  }
  const view = new DataView(out.buffer);
  const codes = new Uint16Array(width * height);
  for (let i = 0; i < codes.length; i++) codes[i] = view.getUint16(i * 2);
  return { width, height, codes };
}

/** Reads any shard, a png16 field tile included. Never rejects. */
export async function readShardAsync(
  header: unknown,
  payload: ArrayBuffer | Uint8Array,
): Promise<ShardResult> {
  const checked = checkHeader(header);
  if ("error" in checked) return checked.error;
  if (checked.header.encoding !== "png16") return readShard(header, payload);
  const bytes = bytesOf(payload);
  if (!bytes) return reject("the payload is not a byte buffer");
  const h = checked.header;
  try {
    if (bytes.byteLength !== h.payload.bytes) return reject("the payload length differs from the header");
    const png = await decodePng16(bytes);
    const grid = h.grid;
    if (!png || !grid) return reject("the payload is not a 16-bit greyscale PNG");
    const { values: count } = layout(h);
    if (png.width !== grid.width || png.height !== grid.height || png.codes.length !== count) {
      return reject("the PNG size differs from frames x items x channels");
    }
    const range = h.code_range as { min: number; max: number };
    const span = { code_type: "uint16" as const, code_range: range, channels: h.channels };
    const values = new Float64Array(count);
    for (let i = 0; i < count; i++) {
      const code = png.codes[i] as number;
      if (code < range.min || code > range.max)
        return reject(`a code lies outside the declared code range at index ${i}`);
      values[i] = decodeCode(span, i % h.channels.length, code);
    }
    return {
      ok: true,
      kind: h.kind,
      fps: h.fps,
      frames: h.frames.count,
      items: h.items,
      channels: h.channels,
      values,
    };
  } catch {
    return reject("the payload could not be decoded");
  }
}
