import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router";
import { pick } from "~/cases/types";
import { AccelRows } from "~/results/AccelRows";
import { publishedBundles } from "~/results/bundles";
import { ComparisonRows } from "~/results/ComparisonRows";
import { NotYetRun } from "~/results/NotYetRun";
import { PENDING_BY_TAB } from "~/results/pending";
import { parseResultsTab, RESULTS_TAB_IDS } from "~/results/tabs";
import { Tabs } from "~/shell/Tabs";
import { useHydrated } from "~/shell/useHydrated";
import type { Route } from "./+types/results";

export const meta: Route.MetaFunction = () => [{ title: "Results · PitStudio" }];

export default function ResultsPage() {
  const { t, i18n } = useTranslation("results");
  const { t: tApp } = useTranslation("app");
  const lang = i18n.resolvedLanguage === "es" ? "es" : "en";
  const [params, setParams] = useSearchParams();
  const hydrated = useHydrated();
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
        {bundles.map((bundle) => (
          <section key={bundle.id} aria-label={pick(bundle.title, lang)}>
            <h3>{pick(bundle.title, lang)}</h3>
            {bundle.comparison.length > 0 && <ComparisonRows rows={bundle.comparison} />}
            {bundle.acceleration.length > 0 && <AccelRows rows={bundle.acceleration} />}
          </section>
        ))}
        {pending.length > 0 && <NotYetRun items={pending} />}
      </Tabs>
    </article>
  );
}
