import { type ReactNode, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { loadAsset } from "~/assets/loader";
import styles from "~/cases/cases.module.css";
import type { SimClock } from "~/sim/clock";
import { type MediaCapabilitiesLike, pickVideoSource, type VideoFile } from "./pickVideoSource";
import { needsReseek } from "./videoSync";

export type VideoState = "idle" | "loading" | "playing" | "unavailable" | "integrity-failed";

export interface VideoCardProps {
  files: VideoFile[];
  posterUrl: string;
  baseUrl: string;
  clock: SimClock;
  title: string;
  sha256ByPath: Record<string, string>;
  bytesByPath?: Record<string, number>;
  /** `undefined` reads `navigator.mediaCapabilities`; `null` means there is none. */
  mediaCapabilities?: MediaCapabilitiesLike | null;
  fetchImpl?: typeof fetch;
  /** Transport controls shown under the video (the page clock). */
  children?: ReactNode;
}

/**
 * A replay video bound to the page clock (FR-018-23..27): no bytes before the clock plays (preload none, WebP poster), the file is
 * chosen by MediaCapabilities, its SHA-256 is verified before it is used, and a failure leaves the poster, a message and the
 * REPLAY badge, never touching the clock.
 */
export function VideoCard(props: VideoCardProps) {
  const { files, posterUrl, clock, title, children } = props;
  const { t } = useTranslation("cases");
  const [state, setState] = useState<VideoState>("idle");
  const [source, setSource] = useState<VideoFile | null | undefined>(undefined);
  const video = useRef<HTMLVideoElement | null>(null);
  const started = useRef(false);
  const objectUrl = useRef<string | null>(null);
  const latest = useRef(props);
  latest.current = props;
  const load = useRef<() => void>(() => undefined);

  // Which file this browser can show (known before any byte is requested).
  useEffect(() => {
    let live = true;
    const capabilities =
      props.mediaCapabilities !== undefined
        ? props.mediaCapabilities
        : ((typeof navigator !== "undefined"
            ? (navigator as { mediaCapabilities?: unknown }).mediaCapabilities
            : null) as MediaCapabilitiesLike | null | undefined);
    void pickVideoSource(files, capabilities).then((picked) => {
      if (!live) return;
      setSource(picked);
      if (!picked) setState("unavailable");
    });
    return () => {
      live = false;
    };
  }, [files, props.mediaCapabilities]);

  // Keep the video with the clock: scrub and step seek it, play and pause drive it, drift beyond two frames re-seeks it.
  const fps = source?.encoder.fps ?? clock.fps;
  useEffect(() => {
    const el = video.current;
    if (!el) return;
    const seekTo = (t: number) => {
      try {
        el.currentTime = t;
      } catch {
        // a video that cannot seek yet is brought to the clock when its metadata has loaded
      }
    };
    let wasPlaying = clock.getState().playing;
    const apply = (s: { t: number; rate: number; playing: boolean }) => {
      const hasSource = el.hasAttribute("src");
      if (s.playing && s.rate > 0) {
        if (hasSource) {
          if (needsReseek(el.currentTime, s.t, fps)) seekTo(s.t);
          el.playbackRate = Math.min(16, Math.max(0.0625, s.rate));
          if (el.paused) void el.play()?.catch(() => undefined);
        }
      } else {
        if (hasSource && !el.paused) el.pause();
        if (Math.abs(el.currentTime - s.t) > 1e-9) seekTo(s.t);
      }
    };
    const off = clock.subscribe((s) => {
      if (s.playing && !wasPlaying) load.current();
      wasPlaying = s.playing;
      apply(s);
    });
    // While it plays, every animation frame compares the video with the clock.
    let frame = 0;
    const watch = () => {
      const s = clock.getState();
      if (s.playing) apply(s);
      frame = requestAnimationFrame(watch);
    };
    if (typeof requestAnimationFrame === "function") frame = requestAnimationFrame(watch);
    if (wasPlaying) load.current();
    return () => {
      off();
      if (typeof cancelAnimationFrame === "function") cancelAnimationFrame(frame);
    };
  }, [clock, fps]);

  // Fetch the chosen file the first time the clock plays, verify it, then give it to the element as a blob.
  load.current = () => {
    if (started.current) return;
    const { current } = latest;
    const picked = source;
    if (!picked) return;
    started.current = true;
    setState("loading");
    const sha = current.sha256ByPath[picked.path];
    void (async () => {
      if (!sha) {
        setState("integrity-failed");
        return;
      }
      const loaded = await loadAsset(
        { path: picked.path, sha256: sha, bytes: current.bytesByPath?.[picked.path] ?? 0 },
        { baseUrl: current.baseUrl, fetch: current.fetchImpl },
      );
      if (!loaded.ok) {
        setState(loaded.reason === "integrity" ? "integrity-failed" : "unavailable");
        return;
      }
      const el = video.current;
      if (!el) return;
      const url = URL.createObjectURL(new Blob([loaded.bytes as BlobPart]));
      objectUrl.current = url;
      el.addEventListener(
        "loadedmetadata",
        () => {
          try {
            el.currentTime = clock.getState().t;
          } catch {
            // the clock is the authority; the next frame re-seeks
          }
          if (clock.getState().playing) void el.play()?.catch(() => undefined);
        },
        { once: true },
      );
      el.addEventListener("playing", () => setState("playing"), { once: true });
      el.src = url;
      el.load();
      if (clock.getState().playing) void el.play()?.catch(() => undefined);
    })();
  };

  // The file may be chosen after the clock already plays.
  useEffect(() => {
    if (source && clock.getState().playing) load.current();
  }, [source, clock]);

  useEffect(
    () => () => {
      if (objectUrl.current) URL.revokeObjectURL(objectUrl.current);
    },
    [],
  );

  return (
    <article className={styles.card} data-testid="video-card" data-state={state} aria-label={title}>
      <div className={styles.chips}>
        <h3>{title}</h3>
        <span className={styles.lane} data-lane="replay" data-testid="lane-badge">
          {t("lane.replay")}
        </span>
        <span className={styles.unit}>{t(`video.state.${state}`)}</span>
      </div>
      <video
        ref={video}
        data-testid="media-video"
        className={styles.video}
        preload="none"
        poster={posterUrl}
        muted
        playsInline
        aria-label={title}
      />
      {state === "unavailable" && <p role="status">{t("video.unavailable")}</p>}
      {state === "integrity-failed" && <p role="status">{t("video.integrity")}</p>}
      {children}
    </article>
  );
}
