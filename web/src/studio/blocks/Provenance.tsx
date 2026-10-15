import { useTranslation } from "react-i18next";
import { clip, gib, num, percent, stageOf, THROTTLE_REASONS } from "../format";
import styles from "../studio.module.css";
import { type ArtefactLike, NOT_PUBLISHED, type RunCard, type TelemetrySummary } from "../types";

function Chip({ id, label, value, shown }: { id: string; label: string; value?: string; shown: string }) {
  return (
    <span data-chip={id} data-value={value ?? shown} className={styles.chip}>
      <span className={styles.chipLabel}>{label}</span> {shown}
    </span>
  );
}

/** Provenance chips of an artefact: run, recipe, commit, GPU and, for a public stage, its timings and throttle shares (FR-019-15). */
export function ProvenanceChips({ artefact, run }: { artefact: ArtefactLike; run: RunCard | null }) {
  const { t } = useTranslation("studio");
  const stage = stageOf(run, artefact.producer.stage);
  const localOnly = stage?.performance === "local-only";
  const tele: TelemetrySummary | null = stage && typeof stage.telemetry === "object" ? stage.telemetry : null;
  const wall = num(stage?.wall_s);
  const vramBytes = tele?.mem_used_peak_bytes;
  const energy = num(tele?.energy_j);
  const fractions = tele?.clocks_event_frac;

  return (
    <div data-testid="provenance" className={styles.chips}>
      <Chip id="run" label={t("prov.run")} shown={clip(artefact.run_id)} />
      {run?.recipe?.sha256 && (
        <Chip id="recipe" label={t("prov.recipe")} shown={clip(run.recipe.sha256.slice(0, 12))} />
      )}
      <Chip id="git" label={t("prov.git")} shown={clip(artefact.git_sha.slice(0, 7))} />
      {run?.gpu && <Chip id="gpu" label={t("prov.gpu")} shown={clip(run.gpu.name)} />}
      {run?.gpu && <Chip id="driver" label={t("prov.driver")} shown={clip(run.gpu.driver)} />}
      {localOnly && <Chip id="local-only" label={t("prov.localOnly")} shown={NOT_PUBLISHED} />}
      {!localOnly && wall !== null && (
        <Chip id="wall" label={t("prov.wall")} value={wall} shown={`${wall} s`} />
      )}
      {!localOnly && typeof vramBytes === "number" && Number.isFinite(vramBytes) && (
        <Chip id="vram" label={t("prov.vram")} value={gib(vramBytes)} shown={`${gib(vramBytes)} GiB`} />
      )}
      {!localOnly && energy !== null && (
        <Chip id="energy" label={t("prov.energy")} value={energy} shown={`${energy} J`} />
      )}
      {!localOnly &&
        fractions &&
        typeof fractions === "object" &&
        THROTTLE_REASONS.map((reason) => {
          const p = percent(fractions[reason]);
          return p === null ? null : (
            <Chip
              key={reason}
              id={`throttle-${reason}`}
              label={t(`throttle.${reason}`)}
              value={p}
              shown={`${p} %`}
            />
          );
        })}
    </div>
  );
}
