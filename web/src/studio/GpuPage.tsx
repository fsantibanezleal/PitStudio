import { useTranslation } from "react-i18next";
import shell from "~/shell/shell.module.css";
import { publishedRunIds, useRunBundles, useStudioManifest } from "./data";
import { clip } from "./format";
import styles from "./studio.module.css";
import { GpuTimelines } from "./telemetry/GpuTimelines";
import { LocalOnlyCards } from "./telemetry/LocalOnly";

/** `/studio/gpu`: the open-runtime timelines of every published run, and the licence note for the local-only stages (FR-019-27, FR-019-30). */
export function GpuPage() {
  const { t } = useTranslation("studio");
  const manifest = useStudioManifest();
  const bundles = useRunBundles([...publishedRunIds, ...manifest.value.runs], true);
  const runs = [...bundles.value].sort((a, b) => (a.card.created < b.card.created ? 1 : -1));

  return (
    <article className={shell.page}>
      <h1>{t("gpuPage.title")}</h1>
      <p className={shell.lead}>{t("gpuPage.lead")}</p>
      {bundles.status === "ready" && runs.length === 0 && <p data-testid="no-runs">{t("runs.none")}</p>}
      {runs.map(({ card, telemetry }) => (
        <section key={card.run_id} className={styles.block} data-run-block={card.run_id}>
          <h2>{clip(card.run_id)}</h2>
          {telemetry && <GpuTimelines run={card} telemetry={telemetry} />}
          <LocalOnlyCards run={card} />
        </section>
      ))}
    </article>
  );
}
