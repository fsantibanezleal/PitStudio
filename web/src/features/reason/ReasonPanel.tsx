// The Cosmos Reason 2 panel of the cases B1 and B2 and the tool card of the Studio page (spec 015, FR-015-41, -07, -43).
//
// The baked records `<base>reason/<case>/records.json` and the SHA-256 in `records.sha256` are read at run time and
// verified in the browser (`./records`). Three outcomes, each in `data-reason-state`: `not-run` (nothing published, the
// honest default), `records` (verified: notices, every record with its question, full output, parsed answer, truth and a
// correct or incorrect badge) and `unavailable` (digest or schema failure: "answers unavailable", none of the file's text).
// Every string comes from the verified file or is fixed here and is rendered as a text node, never as markup.
import { useEffect, useState } from "react";
import styles from "~/cases/cases.module.css";
import { panelText, type RecordsResult, UNAVAILABLE_TEXT, verifyRecordFile } from "./records";

export const COSMOS_NOTICE = "Built on NVIDIA Cosmos";
export const HONESTY_NOTICE = "Zero-shot 2B VLM; not a safety system.";
export const NOT_RUN_TEXT = "not run";
// Fixed English strings: the notices are mandated verbatim by FR-015-41 and the rest names the tool and its state.
const HEADING = "Cosmos Reason 2 · zero-shot 2B vision-language model";
const TOOL_NAME = "Cosmos Reason 2";
const CORRECT = "correct";
const INCORRECT = "incorrect";

type State =
  | { kind: "loading" }
  | { kind: "not-run" }
  | { kind: "unavailable" }
  | { kind: "records"; result: RecordsResult };

async function fetchText(url: string, signal: AbortSignal): Promise<string | null> {
  const response = await fetch(url, { signal });
  const type = response.headers.get("content-type") ?? "";
  if (!response.ok || type.includes("text/html")) return null; // a missing file (or an SPA fallback page) is "not published"
  return response.text();
}

export function ReasonPanel({ caseId }: { caseId: string }) {
  const [state, setState] = useState<State>({ kind: "loading" });
  useEffect(() => {
    const controller = new AbortController();
    const base = `${import.meta.env.BASE_URL}reason/${caseId}/`;
    (async () => {
      try {
        const records = await fetchText(`${base}records.json`, controller.signal);
        if (records === null) return setState({ kind: "not-run" });
        const digest = await fetchText(`${base}records.sha256`, controller.signal);
        const result = await verifyRecordFile(records, (digest ?? "").trim());
        setState(result.ok ? { kind: "records", result } : { kind: "unavailable" });
      } catch {
        if (!controller.signal.aborted) setState({ kind: "not-run" });
      }
    })();
    return () => controller.abort();
  }, [caseId]);

  const doc = state.kind === "records" ? (state.result.ok ? state.result.doc : null) : null;
  const records = (doc as { records?: Record<string, unknown>[] } | null)?.records ?? [];
  return (
    <section
      className={styles.panel}
      data-testid="reason-panel"
      data-reason-state={state.kind}
      aria-label="Cosmos Reason 2"
    >
      <h3>{HEADING}</h3>
      {state.kind === "not-run" && (
        <p>{`Cosmos Reason 2: ${NOT_RUN_TEXT}. No answers are published for this case.`}</p>
      )}
      {state.kind === "unavailable" && <p>{UNAVAILABLE_TEXT}</p>}
      {state.kind === "records" && state.result.ok && (
        <>
          <p>{panelText(state.result)[0]}</p>
          <p>{panelText(state.result)[1]}</p>
          {records.map((r, i) => (
            <div key={String(r.record_id ?? i)} data-reason-record>
              <p>{String(r.question ?? "")}</p>
              <p>{String(r.output ?? "")}</p>
              {typeof r.parsed === "string" && <p>{r.parsed}</p>}
              {typeof r.truth === "string" && <p>{r.truth}</p>}
              <span data-correct={r.correct === true ? "true" : "false"}>
                {r.correct === true ? CORRECT : INCORRECT}
              </span>
            </div>
          ))}
        </>
      )}
    </section>
  );
}

/** The Cosmos tool on the Studio page: "not run" while no Cosmos run is published (the gated terms are not accepted). */
export function CosmosToolCard() {
  return (
    <section data-tool="cosmos-reason-2" aria-label="Cosmos Reason 2">
      <h2>{TOOL_NAME}</h2>
      <p>{`Zero-shot 2B vision-language reasoning scored against exact scene truth: ${NOT_RUN_TEXT} (no Cosmos run is published).`}</p>
      <p>{COSMOS_NOTICE}</p>
      <p>{HONESTY_NOTICE}</p>
    </section>
  );
}
