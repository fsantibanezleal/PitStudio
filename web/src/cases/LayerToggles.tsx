import { useTranslation } from "react-i18next";
import styles from "./cases.module.css";
import { LAYER_IDS, type LayerId } from "./types";

export interface LayerTogglesProps {
  /** The layer ids the case lists in the registry. */
  layers: readonly string[];
  /** Layers with a published artefact for the case; the others are disabled with "Not yet run". */
  published: ReadonlySet<LayerId>;
  visible: ReadonlySet<LayerId>;
  onToggle: (layer: LayerId) => void;
}

/** One toggle per layer of the case, in the canonical layer order (FR-018-04). `aria-pressed` is the visibility. */
export function LayerToggles({ layers, published, visible, onToggle }: LayerTogglesProps) {
  const { t } = useTranslation("cases");
  const shown = LAYER_IDS.filter((layer) => layers.includes(layer));

  return (
    <fieldset data-testid="layers" aria-label={t("layers.title")} className={styles.layers}>
      {shown.map((layer) => {
        const enabled = published.has(layer);
        return (
          <button
            key={layer}
            type="button"
            data-layer={layer}
            aria-pressed={enabled && visible.has(layer)}
            disabled={!enabled}
            className={styles.layer}
            onClick={() => onToggle(layer)}
          >
            {t(`layers.${layer}`)}
            {!enabled && <span className={styles.pending}> {t("notYetRun")}</span>}
          </button>
        );
      })}
    </fieldset>
  );
}
