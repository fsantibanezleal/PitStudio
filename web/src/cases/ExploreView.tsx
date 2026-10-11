import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router";
import { useHydrated } from "~/shell/useHydrated";
import { useThreeD } from "~/tier/probe";
import { TierBadge } from "~/tier/TierBadge";
import { CaseRail } from "./CaseRail";
import styles from "./cases.module.css";
import { KpiTable } from "./KpiTable";
import { LayerToggles } from "./LayerToggles";
import { publishedLayers, useWebManifest } from "./manifest";
import { caseRegistry } from "./registry";
import {
  type CaseEntry,
  type CaseId,
  caseEntry,
  headlineKpis,
  isCaseId,
  LAYER_IDS,
  type LayerId,
} from "./types";

/** Layers, scene state and headline KPIs of one case; shared by the Explore route and the Scene tab. */
export function Stage({ caseId, entry }: { caseId: CaseId; entry: CaseEntry }) {
  const { t } = useTranslation("cases");
  const manifest = useWebManifest();
  const threeD = useThreeD();
  const [hidden, setHidden] = useState<ReadonlySet<LayerId>>(new Set());
  const published = publishedLayers(manifest.artefacts, caseId);
  const visible = new Set(
    LAYER_IDS.filter((l) => published.has(l) && !hidden.has(l) && entry.layers.includes(l)),
  );

  const toggle = (layer: LayerId) => {
    const next = new Set(hidden);
    if (visible.has(layer)) next.add(layer);
    else next.delete(layer);
    setHidden(next);
  };

  return (
    <>
      <section className={styles.panel} aria-labelledby="layers-title">
        <h2 id="layers-title">{t("layers.title")}</h2>
        <LayerToggles layers={entry.layers} published={published} visible={visible} onToggle={toggle} />
      </section>
      <section
        className={styles.scene}
        data-testid="scene-state"
        data-visible-layers={[...visible].join(",")}
        aria-labelledby="scene-title"
      >
        <div>
          <h2 id="scene-title">{t("scene.title")}</h2>
          <p>
            {t("scene.terrain")}: <span className={styles.pending}>{t("notYetRun")}</span>
          </p>
          {threeD === false && <p>{t("scene.noThreeD")}</p>}
          <p className={styles.unit}>
            {t("scene.summary", {
              layers: [...visible].map((l) => t(`layers.${l}`)).join(", ") || t("scene.noLayers"),
            })}
          </p>
        </div>
      </section>
      <section
        className={styles.panel}
        data-testid="kpi-panel"
        data-case={caseId}
        aria-labelledby="kpi-title"
      >
        <h2 id="kpi-title">{t("kpi.panelTitle")}</h2>
        <KpiTable items={headlineKpis(entry).map((kpi) => ({ kpi, value: null, artefact: null }))} />
        <p>
          <Link to={`/cases/${caseId}/`}>{t("kpi.openCase")}</Link>
        </p>
      </section>
    </>
  );
}

/** The Explore route: case rail, layers, scene state, KPI panel and tier badge (FR-018-02 to FR-018-08). */
export function ExploreView() {
  const { t } = useTranslation(["cases", "app"]);
  const [params, setParams] = useSearchParams();
  const hydrated = useHydrated();
  const requested = hydrated ? params.get("case") : null;
  const selected = isCaseId(requested) ? requested : null;
  const entry = selected ? caseEntry(caseRegistry, selected) : undefined;

  const select = (id: CaseId) => {
    const next = new URLSearchParams(params);
    next.set("case", id);
    setParams(next, { replace: true, preventScrollReset: true });
  };

  return (
    <article>
      <h1>{t("app:pages.explore.title")}</h1>
      <p className={styles.unit}>{t("app:pages.explore.lead")}</p>
      <TierBadge />
      <div className={styles.explore}>
        <nav data-testid="case-rail" aria-label={t("cases:rail.title")}>
          <CaseRail registry={caseRegistry} selected={selected} onSelect={select} />
        </nav>
        <div className={styles.stage}>
          {selected && entry ? (
            <Stage key={selected} caseId={selected} entry={entry} />
          ) : (
            <p className={styles.panel}>{t("cases:explore.pick")}</p>
          )}
        </div>
      </div>
    </article>
  );
}
