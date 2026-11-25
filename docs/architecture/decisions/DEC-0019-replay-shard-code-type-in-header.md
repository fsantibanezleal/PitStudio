# DEC-0019: Replay shards use 16-bit integer codes, the type is declared in the header

> The accepted record DEC-0006 fixed `int16` for quantized replay shards. The reviewed specifications let a shard
> declare `int16` or `uint16`, and fix `uint16` for point-cloud shards. This record amends DEC-0006 decision 2 rather
> than rewriting it. · Part of: [decisions](README.md) · Related:
> [DEC-0006](DEC-0006-3d-and-simulation-on-static-web.md) · [DEC-0018](DEC-0018-corrections-to-dec-0004-0006-0010.md)

**Status:** Accepted, 2026-10-11. Amends DEC-0006 (decision 2, the replay code type).

## Context

DEC-0006, decision 2, lists the format of fleet and particle replays as "int16-quantized poses and positions in a
bounding box". While the specifications were written, four requirements stated a different detail:
- FR-005-45 (physics replay shards) lets the header declare the code type;
- DC-018-03 (the replay-shard schema of the web app) declares `code_type` as `int16` or `uint16`;
- P-018-68 (the replay round-trip property) holds for either type;
- FR-013-35 (sensor point-cloud shards) fixes `uint16`.

A position quantized inside its bounding box fits either a signed or an unsigned 16-bit code with the same resolution,
so the type is a property of the producer, not of the product. Accepted records are not rewritten, so the change is
recorded here, and the status line of DEC-0006 points to this record.

## Decision

1. **DEC-0006, decision 2 — replay code type.** Replays use 16-bit integer codes. The shard header declares `int16` or
   `uint16`, and readers take the type from the header. A reader never assumes one type, and a header that declares
   any other type is rejected.

The rest of DEC-0006 decision 2 stands: quantization inside a bounding box, time-window shards of at most 10 MB, and a
JSON manifest with schema, units, fps and SHA-256.

## Alternatives considered

| Alternative | Why it was not taken |
|---|---|
| Rewrite DEC-0006 in place | The decision-record rules forbid rewriting accepted records except for typos and broken links |
| Revert the specifications to `int16` only | Point-cloud shards are naturally unsigned (FR-013-35), and a header-declared type costs one branch in the reader |

## Consequences

- Readers of DEC-0006 are pointed here by its status line.
- The specifications keep their wording: 005-physics (FR-005-45), 013-sensors (FR-013-35) and 018-web-cases
  (DC-018-03, P-018-68). The replay reader and the shard writers are tested with both types.
