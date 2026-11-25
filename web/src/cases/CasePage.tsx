import { lazy, Suspense } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router";
import { publishedBundles } from "~/results/bundles";
import { NotFound } from "~/shell/NotFound";
import { Tabs } from "~/shell/Tabs";
import { parseTabParam } from "~/shell/tabParam";
import { useHydrated } from "~/shell/useHydrated";
import { ClockControls } from "~/sim/ClockControls";
import { DEFAULT_DURATION_S, useSimClock } from "~/sim/useSimClock";
import { TierBadge } from "~/tier/TierBadge";
import { CaseStory } from "./BuiltWithView";
import { Stage } from "./ExploreView";
import { artefactsOfCase, latestRunId, useWebManifest } from "./manifest";
import { caseRegistry } from "./registry";
import { replayDuration, replayVideosOf } from "./replayVideos";
import { type CaseEntry, type CaseId, caseEntry, isCaseId, type Lang, pick } from "./types";

// Each tab other than the Scene is its own chunk, requested when the visitor opens it (NFR-018-02): the initial JavaScript of a case
// page holds the shell, the case story and the Scene tab only.
// The Reproduce block carries the recipe files of the cases: it is its own chunk, drawn once the page is hydrated.
const ReproduceWithRuns = lazy(() =>
  import("./ReproduceWithRuns").then((m) => ({ default: m.ReproduceWithRuns })),
);
const TAB_CHUNKS = {
  simulate: () => import("./SimulateTab").then((m) => ({ default: m.SimulateTab })),
  replay: () => import("./ReplayTab").then((m) => ({ default: m.ReplayTab })),
  charts: () => import("./ChartsTab").then((m) => ({ default: m.ChartsTab })),
  context: () => import("./ContextTab").then((m) => ({ default: m.ContextTab })),
};
const SimulateTab = lazy(TAB_CHUNKS.simulate);
const ReplayTab = lazy(TAB_CHUNKS.replay);
const ChartsTab = lazy(TAB_CHUNKS.charts);
const ContextTab = lazy(TAB_CHUNKS.context);

// A link that names a tab (`?tab=charts`) starts that tab's chunk while the page hydrates, so the tab is drawn as soon as it is selected.
if (typeof window !== "undefined") {
  const named = /[?&]tab=([a-z]+)/.exec(window.location.search)?.[1];
  if (named && Object.hasOwn(TAB_CHUNKS, named)) void TAB_CHUNKS[named as keyof typeof TAB_CHUNKS]();
}

export const CASE_TAB_IDS = ["scene", "simulate", "replay", "charts", "context"] as const;

function Workbench({ caseId, entry }: { caseId: CaseId; entry: CaseEntry }) {
  const { t, i18n } = useTranslation("cases");
  const lang: Lang = i18n.resolvedLanguage === "es" ? "es" : "en";
  const [params, setParams] = useSearchParams();
  const hydrated = useHydrated();
  const manifest = useWebManifest();
  const selected = hydrated ? parseTabParam(params.toString(), CASE_TAB_IDS) : CASE_TAB_IDS[0];
  const own = artefactsOfCase(manifest.artefacts, caseId);
  const videos = replayVideosOf(manifest.artefacts, caseId);
  const clock = useSimClock({
    duration: replayDuration(videos) ?? DEFAULT_DURATION_S,
    fps: entry.clock_fps ?? 10,
    seed: hydrated ? params.get("t") : null,
  });
  // With replay videos the clock's controls sit inside the first video card, so there is one set of them on the page.
  const transportInReplay = selected === "replay" && videos.length > 0;

  const select = (id: string) => {
    const next = new URLSearchParams(params);
    next.set("tab", id);
    setParams(next, { preventScrollReset: true });
  };

  return (
    <article>
      <h1>
        {caseId} · {pick(entry.title, lang)}
      </h1>
      <TierBadge />
      <p>
        <Link to="/cases/">{t("case.back")}</Link>
      </p>
      <CaseStory
        caseId={caseId}
        entry={entry}
        artefacts={manifest.artefacts}
        ready={manifest.status === "ready"}
      >
        {/* the clock is shown once the manifest is known: its duration is the longest replay video */}
        {manifest.status === "ready" && !transportInReplay && <ClockControls clock={clock} />}
        <Tabs
          idBase="case"
          label={t("case.tabs")}
          tabs={CASE_TAB_IDS.map((id) => ({ id, label: t(`case.tab.${id}`) }))}
          selected={selected}
          onSelect={select}
        >
          {selected === "scene" && <Stage caseId={caseId} entry={entry} />}
          <Suspense fallback={<p>{t("case.tabLoading")}</p>}>
            {selected === "simulate" && <SimulateTab caseId={caseId} registry={caseRegistry} />}
            {selected === "replay" && (
              <ReplayTab caseId={caseId} artefacts={manifest.artefacts} clock={clock} />
            )}
            {selected === "charts" && (
              <ChartsTab
                caseId={caseId}
                registry={caseRegistry}
                rows={publishedBundles.flatMap((bundle) => bundle.comparison)}
              />
            )}
            {selected === "context" && <ContextTab caseId={caseId} registry={caseRegistry} sources={[]} />}
          </Suspense>
        </Tabs>
        {hydrated && (
          <Suspense fallback={null}>
            <ReproduceWithRuns caseId={caseId} runId={latestRunId(own)} />
          </Suspense>
        )}
      </CaseStory>
    </article>
  );
}

/** A case page for a canonical id; any other id is the app's not-found page and loads nothing (FR-018-13). */
export function CasePage({ id }: { id: string | undefined }) {
  const entry = isCaseId(id) ? caseEntry(caseRegistry, id) : undefined;
  if (!isCaseId(id) || !entry) return <NotFound />;
  return <Workbench caseId={id} entry={entry} />;
}
