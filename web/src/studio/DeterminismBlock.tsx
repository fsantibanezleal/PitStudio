import { useTranslation } from "react-i18next";
import { clip } from "./format";
import styles from "./studio.module.css";
import type { RunCard, StageRecord } from "./types";

interface Observable {
  name: string;
  rtol: number;
  atol: number;
  first: number;
  second: number;
}

const finite = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

function digestsOf(rerun: unknown): [string, string] | null {
  const d = (rerun as { digests?: unknown } | undefined)?.digests;
  return Array.isArray(d) && d.length === 2 && d.every((x) => typeof x === "string")
    ? [String(d[0]), String(d[1])]
    : null;
}

function observablesOf(rerun: unknown): Observable[] {
  const list = (rerun as { observables?: unknown } | undefined)?.observables;
  if (!Array.isArray(list)) return [];
  return list.filter(
    (o): o is Observable =>
      typeof o === "object" &&
      o !== null &&
      typeof (o as Observable).name === "string" &&
      finite((o as Observable).rtol) &&
      finite((o as Observable).atol) &&
      finite((o as Observable).first) &&
      finite((o as Observable).second),
  );
}

function Check({ stage }: { stage: StageRecord }) {
  const { t } = useTranslation("studio");
  const det = stage.determinism;
  if (det?.rerun_check === "not-applicable") return <span>{t("det.notApplicable")}</span>;
  if (det === undefined || det.rerun_check === "pending") return <span>{t("det.pending")}</span>;
  if (det.class === "bitwise") {
    const digests = digestsOf(det.rerun);
    if (digests === null) return <span>{t("det.pending")}</span>;
    return (
      <span>
        <code className={styles.mono}>{clip(digests[0])}</code>{" "}
        <code className={styles.mono}>{clip(digests[1])}</code>{" "}
        <strong>{digests[0] === digests[1] ? t("det.equal") : t("det.different")}</strong>
      </span>
    );
  }
  if (det.class === "statistical") {
    const observables = observablesOf(det.rerun);
    if (observables.length === 0) return <span>{t("det.pending")}</span>;
    return (
      <ul className={styles.plain}>
        {observables.map((o) => (
          <li key={o.name} data-testid="observable">
            {clip(o.name)}: {t("det.tolerance", { rtol: o.rtol, atol: o.atol })} · {o.first} / {o.second}
          </li>
        ))}
      </ul>
    );
  }
  return <span>{t("det.pending")}</span>;
}

/** The determinism class of every stage and the result of its re-run check (FR-019-25). */
export function DeterminismBlock({ run }: { run: RunCard }) {
  return (
    <div data-testid="determinism" className={styles.det}>
      <ul className={styles.plain}>
        {run.stages.map((stage, i) => (
          // biome-ignore lint/suspicious/noArrayIndexKey: a stage is identified by its place on the card
          <li key={i} data-testid="determinism-stage" data-stage={stage.key.id}>
            <strong>{clip(stage.key.id)}</strong> · <span>{clip(stage.determinism?.class ?? "")}</span> ·{" "}
            <Check stage={stage} />
          </li>
        ))}
      </ul>
    </div>
  );
}
