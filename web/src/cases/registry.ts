// The case registry the pages read (DC-018-01). Until `studio/cases.yaml` (T-018-001) is generated into the web build,
// the contract's valid example is the source: the same 12 cases with the same titles, KPIs, sources and methods.
// The registry is descriptive configuration of the product, not a measured result, so showing it is not showing a
// fixture as a result (ADR-0040): every number a visitor sees as a result still comes from a published artefact.
import registryJson from "../../../specs/018-web-cases/contracts/examples/cases.valid.json";
import type { CaseRegistry } from "./types";

export const caseRegistry = registryJson as unknown as CaseRegistry;
