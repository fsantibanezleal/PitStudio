# Spec 000 — Foundation: PitStudio
Status: Draft · Tier: L · Approved: —

The product-level specification, written from the approved solution plan. Every feature spec (`specs/NNN-*/`) is a
child of this one.

## 1. Intent
<!-- The question the product answers, for whom, and what is out of scope. -->

## 2. Users and user stories
| ID | Story | Priority |
|---|---|---|
| US-000-1 | As a <reader/engineer>, I want <capability> so that <outcome>. | P1 |

## 3. Product-level requirements (EARS)
| ID | Pattern | Requirement | Verification |
|---|---|---|---|
| FR-000-01 | Ubiquitous | The web app shall present every result with its data source, licence and lane (live / precomputed / replay). | E2E |
| FR-000-02 | Unwanted | If a compute tier cannot initialise, then the web app shall fall back to the next tier and show the active tier. | E2E (hostile) |
| FR-000-03 | Ubiquitous | The web app shall offer English (default) and Spanish, and light and dark themes, on every view. | E2E + axe |
| FR-000-04 | Event | When a visitor opens the site, the web app shall require the access gate before showing the workbench. | E2E |

## 4. Correctness properties
| ID | Property (for all …) | Input domain / generator | Tolerance |
|---|---|---|---|

## 5. Non-functional requirements and success criteria
| ID | Statement | Threshold | Measured by |
|---|---|---|---|
| NFR-000-01 | Initial JavaScript (gzip) | ≤ 200 KB | build report |
| NFR-000-02 | Accessibility | axe 0 serious/critical; Lighthouse a11y ≥ 0.95 | Playwright + LHCI |
| SC-000-01 | <the headline quality metric on held-out real data> | <threshold vs classical baseline> | metrics baseline |

## 6. Data contracts
| ID | Artifact | Schema | Producer → Consumer |
|---|---|---|---|
| DC-000-01 | `web/public/assets/manifest.json` | `contracts/manifest.schema.json` | export stage → web app |

## 7. Data sources (summary — full registry in `data/sources.yaml`)
| Source id | Real / synthetic | Licence (SPDX) | Redistribution |
|---|---|---|---|

## 8. Risks and assumptions

## 9. Clarifications log
- [NEEDS CLARIFICATION: …]  ← must be empty before Approved
