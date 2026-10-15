import { useTranslation } from "react-i18next";
import { clip } from "../format";
import { SafeText } from "../SafeText";
import styles from "../studio.module.css";
import { type InfoEntry, NOT_PUBLISHED, type StudioTool } from "../types";

const NVIDIA = /nvidia|tensorrt/i;

/** The non-affiliation notice applies to NVIDIA products: by name, or by an NVIDIA or TensorRT licence reference. */
export function isNvidiaTool(tool: StudioTool): boolean {
  return NVIDIA.test(tool.name) || tool.spdx.some((id) => NVIDIA.test(id));
}

/** Block 1: version from the lock, licence, ring, environment, capability probe (FR-019-09, FR-019-42). */
export function IdentityBlock({ tool, info }: { tool: StudioTool; info: InfoEntry }) {
  const { t } = useTranslation("studio");
  const probe = info.probe;
  const localOnly = tool.performance === "local-only" || probe.metrics === NOT_PUBLISHED;
  const publicMetrics =
    probe.status === "pass" && !localOnly && probe.metrics && typeof probe.metrics === "object"
      ? Object.entries(probe.metrics).filter(([, v]) => Number.isFinite(v))
      : [];

  return (
    <section data-block="identity" className={styles.block} aria-labelledby="b-identity">
      <h2 id="b-identity">{t("blocks.identity.title")}</h2>
      <dl className={styles.facts}>
        <dt>{t("blocks.identity.version")}</dt>
        <dd>
          {clip(info.version.value)}
          {info.version.lock ? ` (${clip(info.version.lock)})` : ""}
        </dd>
        {info.version.release_date && (
          <>
            <dt>{t("blocks.identity.released")}</dt>
            <dd>{clip(info.version.release_date)}</dd>
          </>
        )}
        <dt>{t("blocks.identity.licence")}</dt>
        <dd>{tool.spdx.map(clip).join(", ")}</dd>
        <dt>{t("blocks.identity.licenceClass")}</dt>
        <dd>{clip(tool.licence_class)}</dd>
        <dt>{t("blocks.identity.ring")}</dt>
        <dd>{clip(tool.ring)}</dd>
        <dt>{t("blocks.identity.env")}</dt>
        <dd>{tool.envs.map(clip).join(", ")}</dd>
        <dt>{t("blocks.identity.probe")}</dt>
        <dd data-testid="probe-status" data-status={probe.status}>
          {probe.status === "pass" && <span>{t("probe.pass")}</span>}
          {probe.status === "fail" && <span>{t("probe.fail")}</span>}
          {probe.status === "skip" && <span>{t("probe.skip")}</span>}
          {probe.status === "not-probed" && <span>{t("probe.notProbed")}</span>}
          {probe.status !== "not-probed" && (
            <span>
              {" "}
              {t("probe.on", { date: clip(probe.date), gpu: clip(probe.gpu), driver: clip(probe.driver) })}
            </span>
          )}
          {probe.status === "fail" && probe.error !== undefined && (
            <>
              {" "}
              <SafeText value={probe.error} />
            </>
          )}
          {probe.status === "pass" && localOnly && <span> {NOT_PUBLISHED}</span>}
          {publicMetrics.length > 0 && (
            <ul className={styles.plain}>
              {publicMetrics.map(([name, value]) => (
                <li key={name}>
                  {clip(name)}: {value}
                </li>
              ))}
            </ul>
          )}
        </dd>
      </dl>
      {localOnly && probe.status !== "pass" && <p>{NOT_PUBLISHED}</p>}
      {isNvidiaTool(tool) && <p className={styles.notice}>{t("blocks.identity.nvidia")}</p>}
    </section>
  );
}
