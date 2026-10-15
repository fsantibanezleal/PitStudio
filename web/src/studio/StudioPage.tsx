import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import shell from "~/shell/shell.module.css";
import { ConnectSection } from "./ConnectSection";
import { studioIndex, studioTools, useRunSummaries } from "./data";
import { Loop } from "./Loop";
import { StudioMap } from "./StudioMap";
import styles from "./studio.module.css";

/** `/studio`: the tool map with its static fallback, the physical-AI loop below it, and the opt-in local-studio control. */
export function StudioPage() {
  const { t } = useTranslation("app");
  const { t: ts } = useTranslation("studio");
  const runs = useRunSummaries();
  return (
    <article className={shell.page}>
      <h1>{t("pages.studio.title")}</h1>
      <p className={shell.lead}>{t("pages.studio.lead")}</p>
      <nav aria-label={ts("nav.label")} className={styles.chips}>
        <Link to="/studio/runs/" className={styles.chip}>
          {ts("nav.runs")}
        </Link>
        <Link to="/studio/gpu/" className={styles.chip}>
          {ts("nav.gpu")}
        </Link>
      </nav>
      <ConnectSection id="s-connect" />
      <StudioMap tools={studioTools} index={studioIndex} />
      <section aria-labelledby="s-loop" className={styles.block}>
        <h2 id="s-loop">{ts("loop.title")}</h2>
        <p>{ts("loop.lead")}</p>
        <Loop runs={runs.value} />
      </section>
    </article>
  );
}
