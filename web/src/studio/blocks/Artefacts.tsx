import { useTranslation } from "react-i18next";
import { ArtefactCard } from "~/cards/ArtefactCard";
import { CASE_IDS, type RunSummary } from "~/cases/types";
import { docsHref } from "../links";
import { SafeText } from "../SafeText";
import styles from "../studio.module.css";
import type { ArtefactLike, RunCard, StudioTool } from "../types";
import { ProvenanceChips } from "./Provenance";

const NONE = "none";

/** Case groups in canonical order, then any other case id in text order, then the artefacts without a case. */
function groupKeys(groups: Map<string, ArtefactLike[]>): string[] {
  const canonical = CASE_IDS.filter((id) => groups.has(id));
  const other = [...groups.keys()]
    .filter((k) => k !== NONE && !(CASE_IDS as readonly string[]).includes(k))
    .sort();
  return [...canonical, ...other, ...(groups.has(NONE) ? [NONE] : [])];
}

/** Block 3: the artefacts of the tool, by case; "Not yet run" or "Evaluated, not adopted" when there are none to show (FR-019-12 to FR-019-14). */
export function ArtefactsBlock({
  tool,
  artefacts,
  runs,
  cards,
}: {
  tool: StudioTool;
  artefacts: ArtefactLike[];
  runs?: Array<RunSummary & { stale?: boolean }>;
  /** The full run cards: with them each artefact carries its provenance chips (FR-019-15). */
  cards?: RunCard[];
}) {
  const { t } = useTranslation("studio");
  const mine = artefacts.filter((a) => a.producer.tool === tool.id);
  const groups = new Map<string, ArtefactLike[]>();
  for (const a of mine) {
    const cases = a.cases && a.cases.length > 0 ? a.cases : [NONE];
    for (const c of cases) groups.set(c, [...(groups.get(c) ?? []), a]);
  }
  const runOf = (a: ArtefactLike) => runs?.find((r) => r.run_id === a.run_id) ?? null;

  return (
    <section data-block="artefacts" className={styles.block} aria-labelledby="b-artefacts">
      <h2 id="b-artefacts">{t("blocks.artefacts.title")}</h2>
      {tool.status === "evaluated-not-adopted" ? (
        <div data-testid="not-adopted" className={styles.notice}>
          <p>
            <strong>{t("blocks.artefacts.notAdopted")}</strong>
          </p>
          {tool.reason && (
            <p>
              <SafeText value={tool.reason} />
            </p>
          )}
          {tool.docs_page && (
            <p>
              <a href={docsHref(tool.docs_page)}>{t("blocks.artefacts.evidence")}</a>
            </p>
          )}
        </div>
      ) : mine.length === 0 ? (
        <p data-testid="not-yet-run">{t("notYetRun")}</p>
      ) : (
        groupKeys(groups).map((key) => (
          <div key={key} data-case-group={key}>
            <h3>{key === NONE ? t("blocks.artefacts.noCase") : key}</h3>
            <div className={styles.grid}>
              {(groups.get(key) ?? []).map((a) => {
                const run = runOf(a);
                return (
                  <div key={`${key}/${a.run_id}/${a.id}`}>
                    {run?.stale && (
                      <span className={styles.badge} data-testid="stale-badge">
                        {t("stale")}
                      </span>
                    )}
                    <ArtefactCard artefact={a} run={run} />
                    {cards && (
                      <ProvenanceChips artefact={a} run={cards.find((c) => c.run_id === a.run_id) ?? null} />
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ))
      )}
    </section>
  );
}
