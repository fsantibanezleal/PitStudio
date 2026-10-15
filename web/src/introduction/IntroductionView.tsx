import { lazy, Suspense } from "react";
import { useTranslation } from "react-i18next";
import styles from "~/shell/shell.module.css";

// The shared shell (the executive view, its tabs and its KaTeX dependency) is split out of the start page: the page
// heading and lede are in the first scripts, the view arrives as its own chunk (NFR-018-02).
const IntroductionBody = lazy(() => import("./IntroductionBody"));

/** The Introduction: the executive view first (framing the industry problem), then the technical view and the App. */
export function IntroductionView({ data }: { data: unknown }) {
  const { t } = useTranslation("app");
  return (
    <article className={styles.page}>
      <h1>{t("introduction.title")}</h1>
      <p className={styles.lead}>{t("introduction.lead")}</p>
      <Suspense fallback={<p role="status">{t("introduction.loading")}</p>}>
        <IntroductionBody data={data} />
      </Suspense>
    </article>
  );
}
