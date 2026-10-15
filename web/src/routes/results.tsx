import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router";
import { caseRegistry } from "~/cases/registry";
import { useParityReport } from "~/cases/SimulateTab";
import { pick } from "~/cases/types";
import { AccelRows } from "~/results/AccelRows";
import { publishedBundles } from "~/results/bundles";
import { ComparisonRows } from "~/results/ComparisonRows";
import { CriteriaTable } from "~/results/CriteriaTable";
import { NotYetRun } from "~/results/NotYetRun";
import { PENDING_BY_TAB } from "~/results/pending";
import { parseResultsTab, RESULTS_TAB_IDS } from "~/results/tabs";
import { AccelerationTab } from "~/results/tabs/AccelerationTab";
import { CosmosTab } from "~/results/tabs/CosmosTab";
import { type ParityReport, ParityTab } from "~/results/tabs/ParityTab";
import { SimToRealTab } from "~/results/tabs/SimToRealTab";
import { Tabs } from "~/shell/Tabs";
import { useHydrated } from "~/shell/useHydrated";
import type { Route } from "./+types/results";

export const meta: Route.MetaFunction = () => [{ title: "Results · PitStudio" }];

const isParityReport = (r: unknown): r is ParityReport =>
  typeof r === "object" && r !== null && Array.isArray((r as ParityReport).engines);

export default function ResultsPage() {
  const { t, i18n } = useTranslation("results");
  const { t: tApp } = useTranslation("app");
  const lang = i18n.resolvedLanguage === "es" ? "es" : "en";
  const [params, setParams] = useSearchParams();
  const hydrated = useHydrated();
  const parity = useParityReport();
  const selected = hydrated ? parseResultsTab(params.toString()) : RESULTS_TAB_IDS[0];

  const select = (id: string) => {
    const next = new URLSearchParams(params);
    next.set("tab", id);
    setParams(next, { preventScrollReset: true });
  };

  const bundles = publishedBundles.filter((b) => b.tab === selected);
  const published = new Set(bundles.map((b) => b.id));
  const pending = PENDING_BY_TAB[selected]
    .filter((id) => !published.has(id))
    .map((id) => ({
      id,
      title: t(`pending.${id}.title`),
      reports: t(`pending.${id}.reports`),
      criterion: t(`pending.${id}.criterion`),
    }));
  const rows = bundles.flatMap((b) => b.comparison);

  return (
    <article>
      <h1>{tApp("pages.results.title")}</h1>
      <p>{tApp("pages.results.lead")}</p>
      <Tabs
        idBase="results"
        label={t("tabs.label")}
        tabs={RESULTS_TAB_IDS.map((id) => ({ id, label: t(`tabs.${id}`) }))}
        selected={selected}
        onSelect={select}
      >
        {selected === "sim-to-real" && <SimToRealTab rows={rows} registry={caseRegistry} />}
        {selected === "cosmos" && <CosmosTab rows={rows} />}
        {selected === "parity" && isParityReport(parity) && parity.engines.length > 0 && (
          <ParityTab report={parity} />
        )}
        {selected === "acceleration" && bundles.length > 0 && (
          <AccelerationTab
            bundles={bundles.map((b) => ({
              id: b.id,
              rows: b.acceleration as never,
              conditions: b.conditions as never,
            }))}
          />
        )}
        {bundles.map((bundle) => (
          <section key={bundle.id} aria-label={pick(bundle.title, lang)}>
            <h3>{pick(bundle.title, lang)}</h3>
            {selected !== "sim-to-real" && selected !== "cosmos" && bundle.comparison.length > 0 && (
              <ComparisonRows rows={bundle.comparison} />
            )}
            {selected === "sim-to-real" && bundle.comparison.some((r) => r.kind !== "estimate") && (
              <ComparisonRows rows={bundle.comparison.filter((r) => r.kind !== "estimate")} />
            )}
            {selected !== "acceleration" && bundle.acceleration.length > 0 && (
              <AccelRows rows={bundle.acceleration} />
            )}
          </section>
        ))}
        {pending.length > 0 && <NotYetRun items={pending} />}
      </Tabs>
      <CriteriaTable bundles={publishedBundles} />
    </article>
  );
}
