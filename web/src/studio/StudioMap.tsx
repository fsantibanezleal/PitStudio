import { Component, lazy, type ReactNode, Suspense, useState } from "react";
import { useTranslation } from "react-i18next";
import { useHydrated } from "~/shell/useHydrated";
import { StaticMap } from "./StaticMap";
import styles from "./studio.module.css";
import type { StudioIndex, StudioTool } from "./types";

// React Flow is requested only here, after hydration, so it belongs to no route's initial JavaScript (FR-019-03).
const ToolMap = lazy(() => import("./ToolMap"));

function Unavailable() {
  const { t } = useTranslation("studio");
  return (
    <section data-testid="tool-map" data-ready="false" aria-label={t("map.alt")}>
      <p data-testid="map-unavailable" role="status" className={styles.notice}>
        {t("map.unavailable")}
      </p>
    </section>
  );
}

/** A chunk that fails to load (HTTP error, offline, script error) leaves the static map and says so (FR-019-39). */
class MapBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch() {
    // the failure is shown on the page; nothing is thrown further
  }
  render() {
    return this.state.failed ? <Unavailable /> : this.props.children;
  }
}

/** The tool map: the prerendered static SVG and table first, the interactive map once it has loaded. */
export function StudioMap({ tools, index }: { tools: readonly StudioTool[]; index: StudioIndex }) {
  const hydrated = useHydrated();
  const [ready, setReady] = useState(false);
  return (
    <div>
      {hydrated && (
        <MapBoundary>
          <Suspense fallback={null}>
            <ToolMap tools={tools} index={index} onReady={() => setReady(true)} />
          </Suspense>
        </MapBoundary>
      )}
      <StaticMap tools={tools} index={index} hideSvg={ready} />
    </div>
  );
}
