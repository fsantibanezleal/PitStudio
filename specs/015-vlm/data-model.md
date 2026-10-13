# Data model 015: conventions of the frame state and its companion files

Authority: spec 015 (`spec.md`, section 6) and the contracts in `contracts/`. This file fixes the conventions the contracts
leave open (reported as ambiguities in the red phase); the ground truth (`src/pitstudio/reason/truth.py`), the query
builder and the detector rule read exactly these. Spec 009 writes the frame states and must follow them.

## Frame state (`contracts/frame-state.schema.json`, DC-015-01)

- Units: every transform and footprint is already in metres. `metersPerUnit` and `upAxis` are required and kept for
  provenance; they are never applied a second time (P-015-08 MR2).
- Horizontal plane: the two axes that are not `upAxis` (x, y for `Z`; x, z for `Y`). `footprint.centre_m` is the object's
  position in that plane, in the order of the axes.
- Heading: `footprint.heading_deg` is counter-clockwise from the first horizontal axis towards the second, in
  [-180, 180]. `half_extents_m` is (half length along the heading, half width across it). The body frame of an object has
  x forward along the heading and y to the left.
- Pose: `translation_m` plus a unit quaternion `rotation_xyzw` (norm within 1e-6 of 1; the loader checks it, FR-015-49).
- `visible_px` never exceeds `width_px x height_px` of the frame (FR-015-48). A "visible" haul truck has at least 400
  pixels, a visible person at least 100, a bench edge "in view" at least 2,000 (spec 015 FR-015-17 to FR-015-19).
- Camera: OpenGL / USD convention. The camera looks along its -Z axis, +Y is up, +X is right; the world direction of pixel
  (u, v) is R [(u - cx)/fx, -(v - cy)/fy, -1]. `pose` is the world-from-camera pose (spec 013 FR-013-19).

## Companion files (referenced by path and SHA-256 in the frame state)

| Reference | Format | Content |
|---|---|---|
| `depth` | `.npy`, float32, shape (height_px, width_px) | distance in metres along each pixel's ray from the camera to the surface (spec 013 `DistanceToCameraSD`); `inf` for sky. A z-depth map (spec 009 FR-009-02) must be converted by the producer: range = z * sqrt(1 + ((u-cx)/fx)^2 + ((v-cy)/fy)^2) |
| `dust_field` | `.npz` (no pickle) with `origin_m` (3), `spacing_m` (scalar), `sigma_per_m` (nx, ny, nz) | extinction coefficient in 1/m per cubic cell, lower corner at `origin_m`, axis order x, y, z; `null` when the scene has no dust field |
| `terrain` | `.npz` with `x0_m`, `y0_m`, `spacing_m`, `z_m` (ny, nx) | ground height in metres on a regular grid, bilinear between nodes (a GeoTIFF is converted by the pipeline) |

A frame whose dust field is `null` has zero extinction unless its condition is `dust`, in which case the type-4 question
is not asked. Blind-zone polygons are not in the frame state: they belong to the truck asset (body frame, metres) and are
supplied by the caller as a map from `asset_id` to polygon; a truck without one makes types 5 not asked.

## Query set and statistics

- `frame_state_sha256` is the SHA-256 of the canonical JSON of the frame state (sorted keys, no spaces, UTF-8, no ASCII
  escapes); the query-set digest is the SHA-256 of the file bytes, supplied by the caller (FR-015-47).
- A query id is `<frame_id>-t<type>`; the label "3+" stands for "3 or more".
- Dataset-level CHAIR_i, CHAIR_s and recall are micro averages; the bootstrap draws, within each true class, the
  multinomial counts of predicted labels (exactly equivalent to resampling queries for count-based metrics).
