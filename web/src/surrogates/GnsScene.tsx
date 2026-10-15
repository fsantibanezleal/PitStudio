import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useModelAvailability } from "~/engines/surrogates/availability";
import {
  GNS_ENVELOPE,
  GNS_FAMILIES,
  type GnsFamily,
  gnsIsExtrapolation,
  type Range,
} from "~/engines/surrogates/envelope";
import { NumberControl } from "./NumberControl";
import styles from "./surrogates.module.css";

export const GNS_MODEL_ID = "gns-a3";
/** The engine cap of the table of spec 018 (section 7.1) and the default scene of FR-011-09. */
export const GNS_PARTICLE_MAX = 5000;
export const GNS_PARTICLE_DEFAULT = 2000;
const PARTICLE_RANGE: Range = { min: 100, max: GNS_PARTICLE_MAX };

const DEFAULTS: Record<string, number> = {
  column_aspect_ratio: 1,
  column_width: 0.5,
  pour_height: 0.2,
  pour_rate: 1.1,
  crest_height: 0.15,
  dump_rate: 1,
};

function defaultsOf(family: GnsFamily): Record<string, number> {
  const out: Record<string, number> = {};
  for (const name of Object.keys(GNS_ENVELOPE[family])) out[name] = DEFAULTS[name] as number;
  return out;
}

/**
 * The A3 live GNS scene (FR-011-09, FR-011-11): the geometry controls, the extrapolation label and the declared availability of the
 * model. Until the trained ONNX model is published (`models/gns-a3.surrogate-io.json`) the scene computes nothing and shows the
 * state "not yet trained"; it never draws a rollout, an error or a step time it did not compute.
 */
export function GnsScene({ tier }: { tier: "t0" | "t1" | "t2" }) {
  const { t } = useTranslation("surrogates");
  const availability = useModelAvailability(GNS_MODEL_ID);
  const [family, setFamily] = useState<GnsFamily>("column-collapse");
  const [values, setValues] = useState<Record<string, number>>(defaultsOf("column-collapse"));
  const [count, setCount] = useState(GNS_PARTICLE_DEFAULT);
  const [started, setStarted] = useState(false);
  const extrapolation = gnsIsExtrapolation(family, values);
  const notice =
    availability === "checking" ? null : availability === "published" ? "runtimeMissing" : "notTrained";
  return (
    <section
      className={styles.scene}
      aria-label={t("gns.region")}
      data-testid="gns-scene"
      data-tier={tier}
      data-availability={availability}
    >
      <div className={styles.controls}>
        <div className={styles.control}>
          <label htmlFor="gns-family">{t("gns.family")}</label>
          <select
            id="gns-family"
            value={family}
            onChange={(event) => {
              const next = event.target.value as GnsFamily;
              setFamily(next);
              setValues(defaultsOf(next));
            }}
          >
            {GNS_FAMILIES.map((id) => (
              <option key={id} value={id}>
                {t(`gns.families.${id}`)}
              </option>
            ))}
          </select>
        </div>
        {Object.entries(GNS_ENVELOPE[family]).map(([name, range]) => (
          <NumberControl
            key={`${family}-${name}`}
            label={t(`gns.params.${name}`)}
            value={values[name] as number}
            range={range}
            onChange={(next) => setValues((previous) => ({ ...previous, [name]: next }))}
          />
        ))}
        <NumberControl
          label={t("gns.count")}
          value={count}
          range={PARTICLE_RANGE}
          step="1"
          onChange={(next) => setCount(Math.min(Math.round(next), GNS_PARTICLE_MAX))}
        />
        <button type="button" onClick={() => setStarted(true)}>
          {t("gns.start")}
        </button>
      </div>
      {extrapolation && (
        <p className={styles.extrapolation} data-testid="extrapolation">
          {t("extrapolation")}
        </p>
      )}
      {notice && (
        <p className={styles.note} role="status" data-testid="surrogate-notice" data-started={started}>
          {t(notice, { engine: "gns" })}
        </p>
      )}
      {availability === "checking" && <p className={styles.note}>{t("checking")}</p>}
    </section>
  );
}
