import { CircleCheck, CircleDashed } from "lucide-react";
import { useTranslation } from "react-i18next";
import { clip, num } from "./format";
import styles from "./studio.module.css";
import type { RunCard, StageRecord } from "./types";

/** One edge per pair: from the stage that produced an artefact of the card to each stage listing it as an artefact input. */
export function stageEdges(run: RunCard): Array<{ from: string; to: string }> {
  const stageIds = new Set(run.stages.map((s) => s.key.id));
  const producer = new Map<string, string>();
  for (const a of run.artefacts) {
    const id = a.producer?.stage?.id;
    if (typeof id === "string" && stageIds.has(id)) producer.set(a.id, id);
  }
  const seen = new Set<string>();
  const out: Array<{ from: string; to: string }> = [];
  for (const stage of run.stages) {
    for (const input of stage.inputs ?? []) {
      if (input.kind !== "artefact") continue;
      const from = producer.get(input.id);
      if (from === undefined || from === stage.key.id) continue;
      const key = `${from}>${stage.key.id}`;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push({ from, to: stage.key.id });
    }
  }
  return out;
}

function statusText(stage: StageRecord): string {
  return (stage.status ?? "").replaceAll("_", " ");
}

/** The stage DAG of a run card as text and icons: cache result, exit status, retries and wall time per stage (FR-019-24). */
export function StageDag({ run }: { run: RunCard }) {
  const { t } = useTranslation("studio");
  const edges = stageEdges(run);
  return (
    <div data-testid="stage-dag" className={styles.dag}>
      <ul className={styles.plain}>
        {run.stages.map((stage, i) => {
          const hit = stage.cache === "hit";
          const Icon = hit ? CircleCheck : CircleDashed;
          const wall = stage.performance === "local-only" ? null : num(stage.wall_s);
          const wallText = wall === null ? "" : `${wall} s`; // seconds: a unit symbol, the same in every language
          const retries = Math.max((stage.attempts?.length ?? 1) - 1, 0);
          return (
            <li
              // biome-ignore lint/suspicious/noArrayIndexKey: a stage is identified by its place on the card
              key={i}
              data-testid="stage-node"
              data-stage={stage.key.id}
              {...(stage.key.variant === undefined ? {} : { "data-variant": stage.key.variant })}
              data-cache={hit ? "hit" : "miss"}
              data-status={stage.status}
              className={styles.dagNode}
            >
              <Icon size={16} aria-hidden="true" />{" "}
              <strong>
                {clip(stage.key.id)}
                {stage.key.variant ? ` (${clip(stage.key.variant)})` : ""}
              </strong>
              <span> · {hit ? t("dag.hit") : t("dag.miss")}</span>
              <span> · {statusText(stage)}</span>
              {typeof stage.exit_code === "number" && (
                <span> · {t("dag.exit", { code: stage.exit_code })}</span>
              )}
              <span data-field="retries"> · {t("dag.retries", { n: retries })}</span>
              {wall !== null && <span data-field="wall"> · {wallText}</span>}
            </li>
          );
        })}
      </ul>
      <ul className={styles.plain} aria-label={t("dag.edges")}>
        {edges.map((e) => (
          <li key={`${e.from}>${e.to}`} data-testid="dag-edge" data-from={e.from} data-to={e.to}>
            {clip(e.from)} {t("dag.feeds")} {clip(e.to)}
          </li>
        ))}
      </ul>
    </div>
  );
}
