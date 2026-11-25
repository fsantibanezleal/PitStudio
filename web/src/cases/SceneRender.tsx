import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { loadAsset } from "~/assets/loader";
import { type MediaCapabilitiesLike, pickVideoSource } from "~/media/pickVideoSource";
import { NVIDIA_TOOL_IDS, type ToolInfo } from "./builtWith";
import styles from "./cases.module.css";
import { LazyImg } from "./LazyImg";
import type { RenderState } from "./renderSummary";
import type { Lang } from "./types";

type PlayState = "idle" | "loading" | "playing" | "unavailable" | "failed" | "integrity";

/** Seconds of the flyover as the label under a still: 0 s, 10 s, 20 s. */
const seconds = (t: number) => `${Number.isInteger(t) ? t : t.toFixed(1)} s`;

/**
 * The rendered scene of a case page (FR-018-73), the same component on every page. The poster and the stills are shown at once; the
 * clip is requested only after a click (preload none, no autoplay), the file is chosen by MediaCapabilities and its SHA-256 is
 * verified before it is used. A failure leaves the poster and the stills and says so in a status message. The producer attribution
 * is the label of the published summary, in place on the video and on every still.
 */
export function SceneRender({
  state,
  tools,
  mediaCapabilities,
  fetchImpl,
}: {
  state: RenderState;
  tools: readonly ToolInfo[];
  /** `undefined` reads `navigator.mediaCapabilities`; `null` means there is none. */
  mediaCapabilities?: MediaCapabilitiesLike | null;
  fetchImpl?: typeof fetch;
}) {
  const { t, i18n } = useTranslation("cases");
  const lang: Lang = i18n.resolvedLanguage === "es" ? "es" : "en";
  const [play, setPlay] = useState<PlayState>("idle");
  const video = useRef<HTMLVideoElement | null>(null);
  const objectUrl = useRef<string | null>(null);
  const started = useRef(false);
  const base = import.meta.env.BASE_URL;

  useEffect(
    () => () => {
      if (objectUrl.current) URL.revokeObjectURL(objectUrl.current);
    },
    [],
  );

  if (state.status === "loading") return null;
  const model = state.model;
  if (!model) {
    return (
      <section
        className={styles.panel}
        data-testid="scene-render"
        data-state="not-run"
        aria-labelledby="scene-render-title"
      >
        <h2 id="scene-render-title">{t("render.title")}</h2>
        <p>
          <span className={styles.pending}>{t("notYetRun")}</span> · {t("render.pending")}
        </p>
      </section>
    );
  }

  const producerLine = `${model.label} ${model.producer.version}. ${t("builtWith.usedSentence")}`;
  const files = model.video?.files ?? [];

  const start = async () => {
    if (started.current || !model.video) return;
    started.current = true;
    setPlay("loading");
    const capabilities =
      mediaCapabilities !== undefined
        ? mediaCapabilities
        : ((typeof navigator !== "undefined"
            ? (navigator as { mediaCapabilities?: unknown }).mediaCapabilities
            : null) as MediaCapabilitiesLike | null | undefined);
    const picked = await pickVideoSource(files, capabilities);
    if (!picked) {
      started.current = false;
      setPlay("unavailable");
      return;
    }
    const sha = model.video.sha256ByPath[picked.path];
    const loaded = sha
      ? await loadAsset(
          { path: picked.path, sha256: sha, bytes: model.video.bytesByPath[picked.path] ?? 0 },
          { baseUrl: base, fetch: fetchImpl },
        )
      : null;
    const el = video.current;
    if (!loaded?.ok || !el) {
      started.current = false;
      setPlay(
        loaded && !loaded.ok && loaded.reason === "integrity" ? "integrity" : sha ? "failed" : "integrity",
      );
      return;
    }
    const url = URL.createObjectURL(new Blob([loaded.bytes as BlobPart], { type: "video/mp4" }));
    objectUrl.current = url;
    el.addEventListener("playing", () => setPlay("playing"), { once: true });
    el.controls = true;
    el.src = url;
    el.load();
    void el.play()?.catch(() => undefined);
    setPlay("playing");
  };

  const posterUrl = model.poster ? `${base}${model.poster.path}` : "";
  const message =
    play === "unavailable"
      ? t("render.unavailable")
      : play === "failed"
        ? t("render.failed")
        : play === "integrity"
          ? t("video.integrity")
          : null;

  return (
    <section
      className={styles.panel}
      data-testid="scene-render"
      data-visual="render"
      data-run={model.runId}
      data-state={play}
      aria-labelledby="scene-render-title"
    >
      <h2 id="scene-render-title">{model.title[lang] || t("render.title")}</h2>
      <figure className={styles.renderFigure}>
        {model.video ? (
          <video
            ref={video}
            data-testid="render-video"
            className={styles.video}
            preload="none"
            poster={posterUrl}
            muted
            playsInline
            aria-label={model.title[lang] || t("render.title")}
          />
        ) : (
          posterUrl && (
            <img
              className={styles.video}
              src={posterUrl}
              alt={t("render.posterAlt")}
              loading="lazy"
              decoding="async"
            />
          )
        )}
        <figcaption>
          <p className={styles.producer} data-producer="render">
            {producerLine}
          </p>
        </figcaption>
      </figure>
      {model.video && (
        <p>
          <button
            type="button"
            onClick={() => void start()}
            disabled={play === "loading" || play === "playing"}
          >
            {t("render.play")}
          </button>{" "}
          <span className={styles.unit}>{t(`render.state.${play}`)}</span>
        </p>
      )}
      {message && <p role="status">{message}</p>}
      {model.stills.length > 0 && (
        <>
          <h3>{t("render.stills")}</h3>
          <ul className={styles.stills}>
            {model.stills.map((s) => (
              <li key={s.artefact.id}>
                <figure data-still={s.artefact.id}>
                  <LazyImg
                    src={`${base}${s.artefact.path}`}
                    alt={t("render.stillAlt", { t: seconds(s.tS) })}
                    width={1920}
                    height={1080}
                  />
                  <figcaption className={styles.unit}>
                    {t("render.stillAt", { t: seconds(s.tS) })} · {model.label}
                  </figcaption>
                </figure>
              </li>
            ))}
          </ul>
        </>
      )}
      <div data-testid="render-built-with">
        <h3>{t("builtWith.title")}</h3>
        <ul className={styles.chips}>
          {model.builtWith.map((id) => {
            const info = tools.find((x) => x.id === id);
            if (!info) return null;
            const nvidia = NVIDIA_TOOL_IDS.includes(id);
            return (
              <li
                key={id}
                className={styles.chip}
                data-chip={id}
                data-nvidia={String(nvidia)}
                data-status="used"
              >
                <Link to={`/studio/tools/${id}/`}>
                  {info.name}
                  {info.version ? ` ${info.version}` : ""}
                </Link>
                <span className={styles.chipMeta}>{t(`render.role.${id}`, { defaultValue: "" })}</span>
                {nvidia && <span className={styles.nvidiaMark}>{t("builtWith.nvidia")}</span>}
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}
