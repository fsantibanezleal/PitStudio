import { useTranslation } from "react-i18next";
import { clip, gib, num, utcDate } from "../format";
import styles from "../studio.module.css";
import type { ArtefactLike, RunCard } from "../types";

/** Block 5: live in the browser, or precomputed on which GPU and when (FR-019-16). */
export function WhereRanBlock({ artefacts, runs }: { artefacts: ArtefactLike[]; runs: RunCard[] }) {
  const { t } = useTranslation("studio");
  const byId = new Map(runs.map((r) => [r.run_id, r]));
  return (
    <section data-block="where-ran" className={styles.block} aria-labelledby="b-where-ran">
      <h2 id="b-where-ran">{t("blocks.whereRan.title")}</h2>
      <ul className={styles.plain}>
        {artefacts.map((a) => {
          const run = byId.get(a.run_id);
          const date = utcDate(run?.created);
          const limit = num(run?.gpu?.power_limit_enforced_w);
          let line: string;
          if (a.lane === "live") line = t("blocks.whereRan.live");
          else if (!run?.gpu || !date) line = t("blocks.whereRan.unknown");
          else if (limit === null)
            line = t("blocks.whereRan.noLimit", {
              gpu: clip(run.gpu.name),
              gb: gib(run.gpu.vram_total_bytes),
              date,
            });
          else
            line = t("blocks.whereRan.precomputed", {
              gpu: clip(run.gpu.name),
              gb: gib(run.gpu.vram_total_bytes),
              w: limit,
              date,
            });
          return (
            <li key={`${a.run_id}/${a.id}`} data-artefact={a.id}>
              <strong>{clip(a.id)}</strong>: {line}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
