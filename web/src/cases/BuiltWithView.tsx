import { createContext, lazy, type ReactNode, Suspense, useContext, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { RunChartList } from "~/charts/RunChartList";
import { methodRegistry, methodSlug } from "~/methods/registry";
import { studioIndex, studioTools } from "~/studio/data";
import {
  attributionText,
  type BuiltGroupId,
  type BuiltGroups,
  type BuiltItem,
  deriveBuiltWith,
  type MethodInfo,
  type ToolInfo,
  vendorName,
  visualAttributionText,
} from "./builtWith";
import styles from "./cases.module.css";
import {
  type PublishedCase,
  PublishedCaseContext,
  type PublishedResult,
  usePublishedResults,
} from "./publishedResults";
import { useRenderSummary } from "./renderSummary";
import type { ArtefactRecord, CaseEntry, Lang } from "./types";
import { pick } from "./types";
import { usedForVisual } from "./visualUsed";

// The rendered scene (poster, stills, clip loader) is drawn after the summary is read in the browser, so its code is a chunk of its own.
const SceneRender = lazy(() => import("./SceneRender").then((m) => ({ default: m.SceneRender })));

const GROUP_IDS: BuiltGroupId[] = ["omniverse", "frameworks", "methods", "data"];

export const toolInfos: ToolInfo[] = studioTools.map((t) => {
  const v = studioIndex.tools.find((i) => i.id === t.id)?.version.value;
  return {
    id: t.id,
    name: t.name,
    version: v && v !== "unresolved" ? v : null,
    licence: t.spdx.length > 0 ? t.spdx.join(" or ") : null,
    cases: t.cases,
    status: t.status,
  };
});
export const methodInfos: MethodInfo[] = methodRegistry.map((m) => ({
  id: m.id,
  name: m.name,
  slug: methodSlug(m.id),
}));

interface Attribution {
  groups: BuiltGroups;
  text: (kind: string, ran?: boolean) => string;
}
const AttributionContext = createContext<Attribution | null>(null);

/** The readable producer line of one visual frame (FR-018-72); nothing outside a case page. */
export function Attribution({ kind, ran }: { kind: string; ran?: boolean }) {
  const a = useContext(AttributionContext);
  const text = a?.text(kind, ran) ?? "";
  // a visual with no registry entry has no line rather than an invented one
  if (text === "") return null;
  return (
    <p className={styles.producer} data-producer={kind}>
      {text}
    </p>
  );
}

function Chip({ item }: { item: BuiltItem }) {
  const { t } = useTranslation("cases");
  return (
    <li
      className={styles.chip}
      data-chip={item.id}
      data-status={item.status}
      data-nvidia={String(item.nvidia)}
    >
      <Link to={item.href}>
        {item.name}
        {item.version ? ` ${item.version}` : ""}
      </Link>
      {item.licence && <span className={styles.chipMeta}>{item.licence}</span>}
      {item.nvidia && <span className={styles.nvidiaMark}>{t("builtWith.nvidia")}</span>}
      <span className={styles.chipStatus} data-used={String(item.status === "used")}>
        {t(`builtWith.${item.status}`)}
      </span>
    </li>
  );
}

/** The Built with section: a native disclosure, collapsed on every load; its summary row counts the used and the planned parts (FR-018-80). */
export function BuiltWithSection({ groups }: { groups: BuiltGroups }) {
  const { t } = useTranslation("cases");
  const all = GROUP_IDS.flatMap((g) => groups[g]);
  const used = all.filter((i) => i.status === "used").length;
  return (
    <section className={styles.builtWith} data-testid="built-with" aria-labelledby="built-with-title">
      <details className={styles.builtDetails}>
        <summary className={styles.builtSummary}>
          <h2 id="built-with-title">{t("builtWith.title")}</h2>
          <span className={styles.unit} data-testid="built-with-counts">
            {t("builtWith.counts", { used, planned: all.length - used })}
          </span>
          <span className={styles.builtChevron} aria-hidden="true" />
        </summary>
        <div className={styles.builtGroups}>
          {GROUP_IDS.map((g) => (
            <div key={g} data-group={g}>
              <h3>{t(`builtWith.group.${g}`)}</h3>
              <ul className={styles.chips}>
                {groups[g].length > 0 ? (
                  groups[g].map((item) => <Chip key={`${g}-${item.id}`} item={item} />)
                ) : (
                  <li className={styles.unit}>{t("builtWith.none")}</li>
                )}
              </ul>
            </div>
          ))}
        </div>
      </details>
    </section>
  );
}

function ResultCard({
  result,
  groups,
  caseId,
}: {
  result: PublishedResult;
  groups: BuiltGroups;
  caseId: string;
}) {
  const { t } = useTranslation("cases");
  const own: BuiltItem[] = result.tools.flatMap((id) => {
    const info = toolInfos.find((x) => x.id === id);
    return info
      ? [
          {
            ...info,
            href: `/studio/tools/${id}/`,
            nvidia: groups.omniverse.some((i) => i.id === id),
            status: "used" as const,
          },
        ]
      : [];
  });
  const methods = groups.methods
    .filter((m) => result.methods.includes(m.id))
    .map((m) => ({ ...m, status: "used" as const }));
  const words = {
    used: t("builtWith.usedSentence"),
    planned: t("builtWith.plannedSentence"),
    plannedList: (parts: string) =>
      t("builtWith.plannedListSentence", { parts, interpolation: { escapeValue: false } }),
  };
  return (
    <section
      className={styles.panel}
      data-visual="result"
      data-result={result.runId}
      data-verdict={result.verdict}
    >
      <h3>{result.title}</h3>
      {result.verdict === "failed" && <p className={styles.failed}>{t("results.failed")}</p>}
      <p className={styles.unit}>{result.label}</p>
      <ul className={styles.headlines}>
        {result.headline.map((h) => (
          <li key={h.name}>
            <strong>{h.value}</strong> {h.unit} · {h.name}
            {h.note ? <span className={styles.unit}> ({h.note})</span> : null}
          </li>
        ))}
      </ul>
      {result.partial && <p className={styles.unit}>{t("results.partial")}</p>}
      <RunChartList caseId={caseId} runId={result.runId} />
      <p className={styles.producer} data-producer="result">
        {attributionText(t("attribution.result"), own.slice(0, 3), methods, words)}
      </p>
      <p className={styles.unit}>
        <Link to={`/studio/runs/${result.runId}/`}>{t("results.run")}</Link>
      </p>
    </section>
  );
}

/**
 * The case story at the top of a case page (FR-018-72): the question, the Built with section, the published results; its context
 * gives every visual below it a readable producer attribution.
 */
export function CaseStory({
  caseId,
  entry,
  artefacts,
  ready,
  children,
}: {
  caseId: string;
  entry: CaseEntry;
  artefacts: readonly ArtefactRecord[];
  ready: boolean;
  children: ReactNode;
}) {
  const { t, i18n } = useTranslation("cases");
  const lang: Lang = i18n.resolvedLanguage === "es" ? "es" : "en";
  const published: PublishedCase = usePublishedResults(caseId, artefacts, ready);
  const render = useRenderSummary(caseId, artefacts, ready);
  const renderTools = render.model?.builtWith;
  const groups = useMemo(
    () =>
      deriveBuiltWith({
        entry,
        tools: toolInfos,
        methods: methodInfos,
        usedTools: published.usedTools,
        usedMethods: published.usedMethods,
        renderTools,
        lang,
        caseId,
      }),
    [entry, published, renderTools, lang, caseId],
  );
  const value = useMemo<Attribution>(() => {
    const words = {
      used: t("builtWith.usedSentence"),
      planned: t("builtWith.plannedSentence"),
      plannedList: (parts: string) =>
        t("builtWith.plannedListSentence", { parts, interpolation: { escapeValue: false } }),
    };
    return {
      groups,
      text: (kind, ran) =>
        visualAttributionText(
          kind,
          t(`attribution.${kind}`, { defaultValue: t("attribution.result") }),
          groups,
          usedForVisual(kind, published.results, entry, ran),
          words,
        ),
    };
  }, [groups, t, published.results, entry]);
  return (
    <PublishedCaseContext.Provider value={published}>
      <AttributionContext.Provider value={value}>
        <p className={styles.question} data-testid="case-question">
          {pick(entry.question, lang)}
        </p>
        <BuiltWithSection groups={groups} />
        {published.results.length > 0 && (
          <section aria-labelledby="results-title" data-testid="published-results">
            <h2 id="results-title">{t("results.title")}</h2>
            {published.results.map((r) => (
              <ResultCard key={r.runId} result={r} groups={groups} caseId={caseId} />
            ))}
          </section>
        )}
        {/* drawn once the results above it are in place, so its stills are not taken for visible while the page above is still short */}
        {published.status === "ready" && (
          <Suspense fallback={null}>
            <SceneRender state={render} tools={toolInfos} />
          </Suspense>
        )}
        {children}
      </AttributionContext.Provider>
    </PublishedCaseContext.Provider>
  );
}

/** The same section in compact form for one catalogue row (FR-018-72): NVIDIA tools, frameworks and methods as one short line. */
export function BuiltWithCompact({ entry, caseId, lang }: { entry: CaseEntry; caseId: string; lang: Lang }) {
  const { t } = useTranslation("cases");
  const groups = deriveBuiltWith({
    entry,
    tools: toolInfos,
    methods: methodInfos,
    usedTools: new Set(),
    usedMethods: new Set(),
    lang,
    caseId,
  });
  return (
    <div data-testid="built-with-compact" className={styles.compact}>
      {GROUP_IDS.filter((g) => g !== "data").map((g) => (
        <p key={g} data-group={g}>
          <span className={styles.unit}>{t(`builtWith.group.${g}`)}: </span>
          {groups[g].map((i) => (i.nvidia ? vendorName(i.name, t("builtWith.nvidia")) : i.name)).join(", ") ||
            t("builtWith.none")}
        </p>
      ))}
    </div>
  );
}
