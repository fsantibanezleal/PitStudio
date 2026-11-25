import { lazy, Suspense, useCallback, useId, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import casesStyles from "~/cases/cases.module.css";
import type { ArtefactRecord } from "~/cases/types";
import { useHydrated } from "~/shell/useHydrated";
import { useMotion } from "~/shell/useReducedMotion";
import { megabytes, terrainModel } from "./model";
import styles from "./terrain.module.css";

// The 3D chunk (three.js, R3F, the 3D Tiles renderer) is a dynamic import: it is requested only after hydration, on a page that
// has a published tileset and a browser with WebGL 2 or WebGPU, and never becomes part of the initial JavaScript (NFR-018-02).
const TerrainCanvas = lazy(() => import("./TerrainCanvas"));

type DetailState = "idle" | "loading" | "shown" | "stopped";

/**
 * The terrain line of the Scene tab and of the Explore route (FR-018-01): "Not yet run" until a tileset is published, then the
 * orbitable 3D pit read from the published LOD-0 tileset, with its provenance chip, a button that loads the higher levels after
 * a user action (progress, abort) and keyboard, pointer and reduced-motion operation.
 */
export function TerrainView({
  caseId,
  artefacts,
  ready,
  threeD,
}: {
  caseId: string | null;
  artefacts: readonly ArtefactRecord[];
  ready: boolean;
  /** `null` until the capability probe ran; `false` when neither WebGL 2 nor WebGPU exists. */
  threeD: boolean | null;
}) {
  const { t } = useTranslation(["terrain3d", "cases"]);
  const hydrated = useHydrated();
  const motion = useMotion();
  const summaryId = useId();
  const model = useMemo(
    () => (ready ? terrainModel(artefacts, caseId, import.meta.env.BASE_URL) : null),
    [ready, artefacts, caseId],
  );
  const [renderer, setRenderer] = useState<"webgpu" | "webgl2" | null>(null);
  const [detail, setDetail] = useState<DetailState>("idle");
  const [wantDetail, setWantDetail] = useState(false);
  const [active, setActive] = useState(0);
  const [resetKey, setResetKey] = useState(0);
  const [failed, setFailed] = useState(false);

  const onProgress = useCallback((which: "lod0" | "detail", p: { active: number; loaded: number }) => {
    if (which !== "detail") return;
    setActive(p.active);
    setDetail((d) => (d === "loading" && p.loaded > 0 && p.active === 0 ? "shown" : d));
  }, []);
  const onError = useCallback(() => setFailed(true), []);

  const caption = t("cases:scene.terrain");
  if (!ready) {
    return (
      <p>
        {caption}: <span className={styles.status}>{t("terrain3d:status.checking")}</span>
      </p>
    );
  }
  if (!model) {
    return (
      <p>
        {caption}: <span className={casesStyles.pending}>{t("cases:notYetRun")}</span>
      </p>
    );
  }

  const showCanvas = hydrated && threeD === true;
  return (
    <div className={styles.view} data-testid="terrain-view" data-state={failed ? "failed" : "used"}>
      <p>
        {caption}: <span>{t("terrain3d:status.used", { run: model.runId })}</span>
      </p>
      {showCanvas && (
        <>
          <div className={styles.canvasBox}>
            <Suspense fallback={<p className={styles.status}>{t("terrain3d:loading")}</p>}>
              <TerrainCanvas
                lod0Url={model.lod0.url}
                detailUrl={wantDetail && model.detail ? model.detail.url : null}
                summaryId={summaryId}
                label={t("terrain3d:canvasLabel")}
                motion={motion}
                resetKey={resetKey}
                onRenderer={setRenderer}
                onProgress={onProgress}
                onError={onError}
              />
            </Suspense>
          </div>
          <p id={summaryId} data-testid="scene-summary" className={styles.hint}>
            {t("terrain3d:summary", {
              renderer: renderer ? t(`terrain3d:renderer.${renderer}`) : t("terrain3d:renderer.pending"),
            })}
          </p>
          <div className={styles.bar}>
            <button type="button" onClick={() => setResetKey((k) => k + 1)}>
              {t("terrain3d:controls.reset")}
            </button>
            {model.detail && !wantDetail && (
              <button
                type="button"
                onClick={() => {
                  setWantDetail(true);
                  setDetail("loading");
                }}
              >
                {t("terrain3d:controls.loadDetail", { size: megabytes(model.detail.bytes) })}
              </button>
            )}
            {wantDetail && (
              <button
                type="button"
                onClick={() => {
                  setWantDetail(false);
                  setDetail("stopped");
                }}
              >
                {t("terrain3d:controls.stopDetail")}
              </button>
            )}
            <span className={styles.hint}>{t("terrain3d:controls.hint")}</span>
          </div>
          <p className={styles.status} role="status" aria-live="polite">
            {detail === "loading" && t("terrain3d:detail.loading", { active })}
            {detail === "shown" && t("terrain3d:detail.shown")}
            {detail === "stopped" && t("terrain3d:detail.stopped")}
            {failed && t("terrain3d:error")}
          </p>
        </>
      )}
      <p>
        <span className={styles.chip} data-testid="provenance-chip" title={t("terrain3d:chip.title")}>
          {model.sources.map((s) => `${s.id} (${s.licence})`).join(" · ")}
          {" · "}
          <span className={styles.badge}>{model.lane.toUpperCase()}</span>
        </span>
      </p>
    </div>
  );
}
