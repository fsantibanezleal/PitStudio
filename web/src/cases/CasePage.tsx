import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router";
import { ArtefactCard } from "~/cards/ArtefactCard";
import { NotFound } from "~/shell/NotFound";
import { Tabs } from "~/shell/Tabs";
import { parseTabParam } from "~/shell/tabParam";
import { useHydrated } from "~/shell/useHydrated";
import { TierBadge } from "~/tier/TierBadge";
import { ContextTab } from "./ContextTab";
import styles from "./cases.module.css";
import { Stage } from "./ExploreView";
import { artefactsOfCase, latestRunId, useWebManifest } from "./manifest";
import { ReproduceBlock } from "./ReproduceBlock";
import { recipeOf } from "./recipes";
import { caseRegistry } from "./registry";
import { type CaseEntry, type CaseId, caseEntry, isCaseId, type Lang, pick } from "./types";

export const CASE_TAB_IDS = ["scene", "simulate", "replay", "charts", "context"] as const;

function Pending({ children }: { children: string }) {
  const { t } = useTranslation("cases");
  return (
    <p className={styles.panel}>
      <span className={styles.pending}>{t("notYetRun")}</span> · {children}
    </p>
  );
}

function Workbench({ caseId, entry }: { caseId: CaseId; entry: CaseEntry }) {
  const { t, i18n } = useTranslation("cases");
  const lang: Lang = i18n.resolvedLanguage === "es" ? "es" : "en";
  const [params, setParams] = useSearchParams();
  const hydrated = useHydrated();
  const manifest = useWebManifest();
  const selected = hydrated ? parseTabParam(params.toString(), CASE_TAB_IDS) : CASE_TAB_IDS[0];
  const own = artefactsOfCase(manifest.artefacts, caseId);
  const replay = own.filter((a) => a.lane === "replay");

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
      <Tabs
        idBase="case"
        label={t("case.tabs")}
        tabs={CASE_TAB_IDS.map((id) => ({ id, label: t(`case.tab.${id}`) }))}
        selected={selected}
        onSelect={select}
      >
        {selected === "scene" && <Stage caseId={caseId} entry={entry} />}
        {selected === "simulate" && (
          <Pending>{t("case.simulatePending", { engines: entry.engines.join(", ") })}</Pending>
        )}
        {selected === "replay" &&
          (replay.length > 0 ? (
            <ul className={styles.cardList}>
              {replay.map((artefact) => (
                <li key={artefact.id}>
                  <ArtefactCard artefact={artefact} run={null} />
                </li>
              ))}
            </ul>
          ) : (
            <Pending>{t("case.replayPending")}</Pending>
          ))}
        {selected === "charts" && <Pending>{t("case.chartsPending")}</Pending>}
        {selected === "context" && <ContextTab caseId={caseId} registry={caseRegistry} sources={[]} />}
      </Tabs>
      <ReproduceBlock caseId={caseId} recipe={recipeOf(caseId)} runId={latestRunId(own)} />
    </article>
  );
}

/** A case page for a canonical id; any other id is the app's not-found page and loads nothing (FR-018-13). */
export function CasePage({ id }: { id: string | undefined }) {
  const entry = isCaseId(id) ? caseEntry(caseRegistry, id) : undefined;
  if (!isCaseId(id) || !entry) return <NotFound />;
  return <Workbench caseId={id} entry={entry} />;
}
