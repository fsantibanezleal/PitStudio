# Plan NNN — <Feature name>
Spec: ./spec.md

## Summary
Approach in five lines; which requirements each component satisfies.

## Technical context
Runtime: Python 3.14 (core `.venv`, pipeline venv) · Node 24 · key dependencies (locked) · target: local CPU/GPU,
GitHub Pages (static).

## Constitution check
| Principle | Pass? | Note / justification |
|---|---|---|
| Acceptance-test-first | | |
| Independent oracles | | oracle for FR-NNN-01 = … |
| Neutral contracts | | DC-NNN-01 |
| Static delivery | | baked fallback for … |

## Design
Components / modules → requirement IDs; data-flow diagram (link to an SVG in docs/assets/diagrams/).

## Test strategy
| Requirement | Level | Oracle | Tool |
|---|---|---|---|
| FR-NNN-01 | unit | analytical | pytest |
| P-NNN-01 | property | invariant | Hypothesis |

## Risks and complexity tracking
| Deviation | Why needed | Simpler alternative rejected because |
|---|---|---|
