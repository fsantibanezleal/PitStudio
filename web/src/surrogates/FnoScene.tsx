import { useState } from "react";
import { useTranslation } from "react-i18next";
import { noticeKey, useModelAvailability } from "~/engines/surrogates/availability";
import { FNO_ENVELOPE, fnoIsExtrapolation } from "~/engines/surrogates/envelope";
import { NumberControl } from "./NumberControl";
import styles from "./surrogates.module.css";

export type FnoVariant = "C2" | "C3";

/** The controls of each variant, in display order (FR-011-38), with their start values (inside the training range). */
const CONTROLS: Record<FnoVariant, ReadonlyArray<{ name: string; value: number; step: string }>> = {
  C2: [
    { name: "breach_row", value: 32, step: "1" },
    { name: "breach_col", value: 32, step: "1" },
    { name: "release_volume", value: 100000, step: "1000" },
    { name: "yield_stress", value: 100, step: "any" },
    { name: "plastic_viscosity", value: 0.5, step: "any" },
  ],
  C3: [
    { name: "wind_speed", value: 5, step: "any" },
    { name: "wind_direction", value: 90, step: "1" },
  ],
};

export const FNO_MODEL_ID: Record<FnoVariant, string> = { C2: "fno-c2-tailings", C3: "fno-c3-dust" };

/**
 * The C2 and C3 FNO controls (FR-011-38, FR-011-39): spin buttons carrying the training ranges of DC-011-02 as `min` and `max`, the
 * extrapolation label for a value outside them and the declared availability of the model. Until the trained ONNX model is
 * published (`models/<model_id>.surrogate-io.json`) the scene evaluates nothing and shows "not yet trained": no field, no
 * evaluation time and no relative L2 are shown that were not computed.
 */
export function FnoScene({ variant, tier }: { variant: FnoVariant; tier: "t0" | "t1" | "t2" }) {
  const { t } = useTranslation("surrogates");
  const availability = useModelAvailability(FNO_MODEL_ID[variant]);
  const [values, setValues] = useState<Record<string, number>>(
    Object.fromEntries(CONTROLS[variant].map((c) => [c.name, c.value])),
  );
  const names = CONTROLS[variant].map((c) => c.name);
  const extrapolation = fnoIsExtrapolation(names, values);
  const notice = noticeKey(availability.state);
  return (
    <section
      className={styles.scene}
      aria-label={t(variant === "C2" ? "fno.regionC2" : "fno.regionC3")}
      data-testid="fno-scene"
      data-variant={variant}
      data-tier={tier}
      data-availability={availability.state}
    >
      <div className={styles.controls}>
        {CONTROLS[variant].map((control) => (
          <NumberControl
            key={control.name}
            label={t(`fno.params.${control.name}`)}
            value={values[control.name] as number}
            range={FNO_ENVELOPE[control.name] as { min: number; max: number }}
            step={control.step}
            onChange={(next) => setValues((previous) => ({ ...previous, [control.name]: next }))}
          />
        ))}
      </div>
      {extrapolation && (
        <p className={styles.extrapolation} data-testid="extrapolation">
          {t("extrapolation")}
        </p>
      )}
      {notice && (
        <p className={styles.note} role="status" data-testid="surrogate-notice">
          {t(notice, { engine: "fno", passed: availability.passed, total: availability.total })}
        </p>
      )}
      {availability.state === "checking" && <p className={styles.note}>{t("checking")}</p>}
    </section>
  );
}
