import { useTranslation } from "react-i18next";
import { SafeText } from "../SafeText";
import styles from "../studio.module.css";
import type { StudioTool } from "../types";

/** Block 8: the alternatives the registry records as rejected, with their reasons (FR-019-19). */
export function AlternativesBlock({ tool }: { tool: StudioTool }) {
  const { t } = useTranslation("studio");
  const list = tool.alternatives_rejected ?? [];
  return (
    <section data-block="alternatives" className={styles.block} aria-labelledby="b-alternatives">
      <h2 id="b-alternatives">{t("blocks.alternatives.title")}</h2>
      {list.length === 0 ? (
        <p>{t("blocks.alternatives.none")}</p>
      ) : (
        <ul className={styles.plain}>
          {list.map((a, i) => (
            // biome-ignore lint/suspicious/noArrayIndexKey: the registry order is the identity of a rejected alternative
            <li key={i} data-testid="alternative">
              <strong>
                <SafeText value={a.name} />
              </strong>
              : <SafeText value={a.reason} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
