import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { engineMode, NEEDS_WEBGPU, PARITY_NOT_CONFIRMED } from "~/engines/registry";
import { useChain } from "~/tier/probe";
import styles from "./cases.module.css";
import { EnginePanel, type EngineState, type PanelTier } from "./EnginePanel";
import { KpiTable } from "./KpiTable";
import { type CaseRegistry, headlineKpis } from "./types";

/** The parity report of the deployed build, read once (`assets/parity-report.json`); missing or unusable confirms nothing. */
export function useParityReport(): unknown {
  const [report, setReport] = useState<unknown>(undefined);
  useEffect(() => {
    const controller = new AbortController();
    fetch(`${import.meta.env.BASE_URL}assets/parity-report.json`, { signal: controller.signal })
      .then((res) => (res.ok ? res.json() : undefined))
      .then(setReport)
      .catch(() => {
        if (!controller.signal.aborted) setReport(undefined);
      });
    return () => controller.abort();
  }, []);
  return report;
}

/**
 * The Simulate (live) tab (FR-018-14): one engine panel per engine of the case, in registry order, each on the tier the page
 * probed (T0 until the probe has finished: nothing is computed before it), LIVE only for a result computed in this browser and
 * REPLAY otherwise, with the notice that says why; the headline KPIs of the case follow the engines.
 */
export function SimulateTab({ caseId, registry }: { caseId: string; registry: CaseRegistry }) {
  const { t } = useTranslation("cases");
  const chain = useChain();
  const report = useParityReport();
  const entry = Object.hasOwn(registry.cases, caseId) ? registry.cases[caseId] : undefined;
  if (!entry) return null;

  const notice = (text: string | null): string | null => {
    if (text === PARITY_NOT_CONFIRMED) return t("engine.notice.parity");
    if (text === NEEDS_WEBGPU) return t("engine.notice.needsWebGpu");
    return text;
  };

  return (
    <>
      {entry.engines.map((engine) => {
        const tier: PanelTier = chain ? chain.tierOf(engine) : "t0";
        const decision = engineMode(engine, tier, report);
        // No engine of this build computes in the browser yet: every panel shows its precomputed lane.
        const state: EngineState = "replay";
        return (
          <EnginePanel
            key={engine}
            engine={engine}
            mode={decision.mode === "live" ? "replay" : decision.mode}
            state={state}
            requests={0}
            tier={tier}
            notice={notice(decision.notice) ?? t("engine.notice.noBackend")}
          />
        );
      })}
      <section
        className={styles.panel}
        data-testid="kpi-panel"
        data-case={caseId}
        aria-labelledby="sim-kpi-title"
      >
        <h2 id="sim-kpi-title">{t("kpi.panelTitle")}</h2>
        <KpiTable items={headlineKpis(entry).map((kpi) => ({ kpi, value: null, artefact: null }))} />
      </section>
    </>
  );
}
