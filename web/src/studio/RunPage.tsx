import { useTranslation } from "react-i18next";
import { ArtefactCard } from "~/cards/ArtefactCard";
import { NotFound } from "~/shell/NotFound";
import shell from "~/shell/shell.module.css";
import { ConnectSection } from "./ConnectSection";
import { DeterminismBlock } from "./DeterminismBlock";
import { isPublishedRun, RUN_ID, useRunBundles, useStudioManifest } from "./data";
import { clip, gib, num, utcDate } from "./format";
import { ManifestTree } from "./ManifestTree";
import { StageDag } from "./StageDag";
import styles from "./studio.module.css";
import { GpuTimelines } from "./telemetry/GpuTimelines";
import { LocalOnlyCards } from "./telemetry/LocalOnly";
import type { ArtefactLike } from "./types";

/**
 * `/studio/runs/<run id>`: manifest viewer, telemetry charts, stage DAG, determinism block and artefacts of a published run
 * (FR-019-22). A run id that is not a published run (unknown, local, malformed or traversing) is the not-found page and
 * requests no run asset (FR-019-26): the id is checked against the runs of this build, then against the runs of the web manifest.
 */
export function RunPage({ id }: { id: string | undefined }) {
  const built = isPublishedRun(id);
  const manifest = useStudioManifest();
  if (id === undefined || !RUN_ID.test(id)) return <NotFound />;
  if (!built) {
    if (manifest.status === "loading") return <Loading />;
    if (!manifest.value.runs.includes(id)) return <NotFound />;
  }
  return <PublishedRun runId={id} />;
}

function Loading() {
  const { t } = useTranslation("studio");
  return (
    <article className={shell.page}>
      <h1>{t("runPage.loading")}</h1>
    </article>
  );
}

function PublishedRun({ runId }: { runId: string }) {
  const { t } = useTranslation("studio");
  const bundles = useRunBundles([runId], true);
  const bundle = bundles.value[0];
  if (bundles.status === "loading") return <Loading />;
  if (!bundle) return <NotFound />;
  const { card, telemetry } = bundle;
  const date = utcDate(card.created);

  return (
    <article className={shell.page}>
      <h1>
        {t("runPage.title")} {clip(card.run_id)}
      </h1>
      <p className={shell.lead}>
        {date ?? ""}
        {card.gpu
          ? ` · ${clip(card.gpu.name)} (${gib(card.gpu.vram_total_bytes)} GB${card.gpu.power_limit_enforced_w === null ? "" : `, ${num(card.gpu.power_limit_enforced_w)} W`})`
          : ""}
        {card.stale ? ` · ${t("stale")}` : ""}
        {card.fixture ? ` · ${t("fixture")}` : ""}
      </p>

      <ConnectSection />

      <section className={styles.block} aria-labelledby="r-manifest">
        <h2 id="r-manifest">{t("runPage.manifest")}</h2>
        <ManifestTree value={card} />
      </section>

      <section className={styles.block} aria-labelledby="r-telemetry">
        <h2 id="r-telemetry">{t("runPage.telemetry")}</h2>
        {telemetry ? (
          <GpuTimelines run={card} telemetry={telemetry} />
        ) : (
          <div data-testid="telemetry-charts">
            <p>{t("runPage.noTelemetry")}</p>
          </div>
        )}
        <LocalOnlyCards run={card} />
      </section>

      <section className={styles.block} aria-labelledby="r-dag">
        <h2 id="r-dag">{t("dag.title")}</h2>
        <StageDag run={card} />
      </section>

      <section className={styles.block} aria-labelledby="r-det">
        <h2 id="r-det">{t("det.title")}</h2>
        <DeterminismBlock run={card} />
      </section>

      <section className={styles.block} aria-labelledby="r-artefacts">
        <h2 id="r-artefacts">{t("runPage.artefacts")}</h2>
        <div data-testid="run-artefacts" className={styles.grid}>
          {card.artefacts.length === 0 && <p>{t("runPage.noArtefacts")}</p>}
          {(card.artefacts as ArtefactLike[]).map((a) => (
            <div key={a.id} id={a.id}>
              <ArtefactCard artefact={a} run={card} />
            </div>
          ))}
        </div>
      </section>
    </article>
  );
}
