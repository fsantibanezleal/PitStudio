import { useTranslation } from "react-i18next";
import { clip } from "../format";
import styles from "../studio.module.css";
import type { ArtefactLike } from "../types";

/** Block 4: the licence and the data each artefact of the tool was made from; the chips of the run sit on the cards (FR-019-15). */
export function ProvenanceBlock({ artefacts }: { artefacts: ArtefactLike[] }) {
  const { t } = useTranslation("studio");
  return (
    <section data-block="provenance" className={styles.block} aria-labelledby="b-provenance">
      <h2 id="b-provenance">{t("blocks.provenance.title")}</h2>
      <p>{t("blocks.provenance.lead")}</p>
      {artefacts.length === 0 ? (
        <p>{t("blocks.provenance.none")}</p>
      ) : (
        <ul className={styles.plain}>
          {artefacts.map((a) => {
            const inputs = a.inputs.filter((i) => i.kind !== "artefact");
            return (
              <li key={`${a.run_id}/${a.id}`} data-provenance={a.id}>
                <strong>{clip(a.id)}</strong> · {clip(a.licence_class)} · {clip(a.spdx)}
                {inputs.length > 0
                  ? ` · ${t("blocks.provenance.from")} ${inputs.map((i) => clip(i.id)).join(", ")}`
                  : ""}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
