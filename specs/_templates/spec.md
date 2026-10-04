# Spec NNN — <Feature name>
Status: Draft | Clarified | Approved | Implementing | Converged | Superseded
Tier: S | M | L · Parent: 000-foundation · Approved: YYYY-MM-DD
Supersedes/Modifies: (none | FR-00X-yy)

## 1. Intent
One paragraph: problem, who benefits, what is out of scope.

## 2. User stories
### US-NNN-1 (P1) <title>
As a <reader/user>, I want <capability> so that <outcome>. Independent test: <how this story alone is demonstrable>.

## 3. Functional requirements (EARS)
| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-NNN-01 | Ubiquitous | The <system> shall <response>. | unit |
| FR-NNN-02 | Event | When <trigger>, the <system> shall <response within X units>. | integration |
| FR-NNN-03 | State | While <state>, the <system> shall <response>. | unit |
| FR-NNN-04 | Optional | Where <feature/hardware>, the <system> shall <response>. | integration (gpu) |
| FR-NNN-05 | Unwanted | If <bad input/condition>, then the <system> shall <error signal>. | adversarial |

## 4. Correctness properties
| ID | Property (for all …) | Input domain / generator | Tolerance |
|---|---|---|---|
| P-NNN-01 | For any finite real signal x, ifft(fft(x)) ≈ x | float64, len 1..4096, abs(x) < 1e6 | rtol 1e-9 |

## 5. Non-functional requirements and success criteria
| ID | Statement | Threshold | Measured by |
|---|---|---|---|

## 6. Data contracts
| ID | Artifact | Schema | Producer → Consumer |
|---|---|---|---|

## 7. Edge cases and assumptions

## 8. Clarifications log
- [NEEDS CLARIFICATION: …]  ← must be empty before Approved

## 9. Changes (only for features that modify earlier behaviour)
### ADDED Requirements
### MODIFIED Requirements
### REMOVED Requirements
