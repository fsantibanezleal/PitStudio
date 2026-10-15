import { ExecutiveView, Tabs, useLangStore } from "@fasl-work/caos-app-shell";
import { type KeyboardEvent, type MouseEvent, useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router";
import styles from "~/shell/shell.module.css";
import { isExecutiveSection } from "./content";
import "./executive.css";
import local from "./introduction.module.css";

/** The pages the technical view points to, in the order of the navigation (the App has its own button). */
const TECHNICAL_PAGES = ["cases", "studio", "theory", "methods", "results", "knowledge"] as const;

const TAB = '[role="tab"][data-tab]';

/** The shell's view reads its language from its own store; keep it on the product's language (no storage write). */
function useShellLanguage(): void {
  const { i18n } = useTranslation();
  const lang = i18n.language === "es" ? "es" : "en";
  useEffect(() => {
    if (useLangStore.getState().lang !== lang) useLangStore.setState({ lang });
  }, [lang]);
}

/** The executive view, with its open sub-tab held in `?section=` so each of the five opens by link. */
function ExecutiveTab({ data, onOpenTechnical }: { data: unknown; onOpenTechnical: () => void }) {
  const [params, setParams] = useSearchParams();
  const host = useRef<HTMLDivElement>(null);
  const applied = useRef(false);
  const wanted = params.get("section");

  useEffect(() => {
    if (applied.current) return;
    applied.current = true;
    if (!isExecutiveSection(wanted) || wanted === "pain") return;
    host.current?.querySelector<HTMLElement>(`[role="tab"][data-tab="${wanted}"]`)?.click();
  }, [wanted]);

  const remember = (id: string | undefined) => {
    if (!isExecutiveSection(id ?? null)) return;
    setParams(
      (previous) => {
        const next = new URLSearchParams(previous);
        if (id === "pain") next.delete("section");
        else next.set("section", id ?? "pain");
        return next;
      },
      { replace: true, preventScrollReset: true },
    );
  };

  return (
    // biome-ignore lint/a11y/noStaticElementInteractions: delegating the shell's own tab clicks and keys, no role of its own
    <div
      ref={host}
      onClick={(e: MouseEvent<HTMLDivElement>) =>
        remember((e.target as HTMLElement).closest<HTMLElement>(TAB)?.dataset.tab)
      }
      onKeyUp={(e: KeyboardEvent<HTMLDivElement>) => {
        if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) {
          remember((e.target as HTMLElement).closest<HTMLElement>(TAB)?.dataset.tab);
        }
      }}
    >
      <ExecutiveView data={data} base={import.meta.env.BASE_URL} onOpenTechnical={onOpenTechnical} />
    </div>
  );
}

function TechnicalTab() {
  const { t } = useTranslation("app");
  return (
    <section className={local.technical}>
      <h2>{t("introduction.technical.heading")}</h2>
      <p className={styles.lead}>{t("introduction.technical.lead")}</p>
      <h3>{t("introduction.technical.pages")}</h3>
      <ul className={local.pages}>
        {TECHNICAL_PAGES.map((page) => (
          <li key={page}>
            <Link to={`/${page}`}>{t(`pages.${page}.title`)}</Link>
            <p>{t(`pages.${page}.lead`)}</p>
          </li>
        ))}
      </ul>
      <Link to="/app" className={local.open}>
        {t("introduction.technical.app")}
      </Link>
    </section>
  );
}

/**
 * The tabs of the Introduction: the executive view first (framing the industry problem), then the technical view and the App.
 * Everything that needs the shared shell (and its KaTeX dependency) lives in this module, which IntroductionView loads lazily.
 */
export default function IntroductionBody({ data }: { data: unknown }) {
  const { t } = useTranslation("app");
  const [params, setParams] = useSearchParams();
  useShellLanguage();
  const view = params.get("view") === "technical" ? "technical" : "executive";

  const select = (id: string) => {
    setParams(
      (previous) => {
        const next = new URLSearchParams(previous);
        if (id === "technical") next.set("view", "technical");
        else next.delete("view");
        return next;
      },
      { replace: true, preventScrollReset: true },
    );
  };

  return (
    <Tabs
      ariaLabel={t("introduction.tabs.label")}
      value={view}
      onChange={select}
      tabs={[
        {
          id: "executive",
          label: t("introduction.tabs.executive"),
          content: <ExecutiveTab data={data} onOpenTechnical={() => select("technical")} />,
        },
        { id: "technical", label: t("introduction.tabs.technical"), content: <TechnicalTab /> },
      ]}
    />
  );
}
