import { Eye, Globe, House, Lock, Quote, Repeat, Unlock } from "lucide-react";
import type { ComponentType } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { clip } from "./format";
import styles from "./studio.module.css";
import type { IndexEdgeJson, InfoEntry, StudioIndex, StudioTool } from "./types";

export const BAND_ORDER = [
  "scene",
  "physics",
  "sensors-synthetic-data",
  "training",
  "acceleration",
  "encoding",
  "web",
] as const;

/** One lucide icon per licence class; the seven are distinct so that the class is readable without colour. */
export const LICENCE_ICONS: Record<string, ComponentType<{ size?: number; x?: number; y?: number }>> = {
  "public-domain": Globe,
  "open-no-attribution": Unlock,
  own: House,
  attribution: Quote,
  "share-alike": Repeat,
  "display-only": Eye,
  "reference-only": Lock,
};

export const NODE_W = 172;
export const NODE_H = 64;
const NAME_CHARS = 24;

export function statusKey(status: string): string {
  return status === "done" ? "done" : status === "evaluated-not-adopted" ? "notAdopted" : "notYetRun";
}

export function nodeLabel(tool: StudioTool, lane: string, ring: string, licence: string, status: string) {
  return `${clip(tool.name)} — lane ${lane}, ring ${ring}, licence ${licence}, status ${status}`;
}

/** Tools in the DOM and Tab order: band order of FR-019-02, then the order within the band. */
export function orderedTools(tools: readonly StudioTool[], index: StudioIndex, group: "map" | "not-adopted") {
  const info = new Map(index.tools.map((t) => [t.id, t] as const));
  return tools
    .map((tool) => ({ tool, info: info.get(tool.id) as InfoEntry | undefined }))
    .filter(
      (e): e is { tool: StudioTool; info: InfoEntry } =>
        e.info !== undefined && e.info.position.group === group,
    )
    .sort(
      (a, b) =>
        BAND_ORDER.indexOf(a.info.position.band as (typeof BAND_ORDER)[number]) -
          BAND_ORDER.indexOf(b.info.position.band as (typeof BAND_ORDER)[number]) ||
        a.info.position.order - b.info.position.order ||
        a.tool.id.localeCompare(b.tool.id),
    );
}

function edgeGeometry(edge: IndexEdgeJson, positions: Map<string, InfoEntry["position"]>) {
  const from = positions.get(edge.from);
  const to = positions.get(edge.to);
  if (!from || !to) return null;
  const x1 = from.x_px + NODE_W;
  const y1 = from.y_px + NODE_H / 2;
  const x2 = to.x_px;
  const y2 = to.y_px + NODE_H / 2;
  const mid = (x1 + x2) / 2;
  return { d: `M ${x1} ${y1} C ${mid} ${y1}, ${mid} ${y2}, ${x2} ${y2}`, lx: mid, ly: (y1 + y2) / 2 };
}

/**
 * The prerendered, static view of the tool map (FR-019-04): an SVG of the graph at the build-time positions of the
 * index and a data table of the same graph. It works without JavaScript; the interactive map replaces the SVG after
 * hydration (FR-019-03).
 */
export function StaticMap({
  tools,
  index,
  hideSvg = false,
}: {
  tools: readonly StudioTool[];
  index: StudioIndex;
  hideSvg?: boolean;
}) {
  const { t } = useTranslation("studio");
  const positions = new Map(index.tools.map((i) => [i.id, i.position] as const));
  const mapTools = orderedTools(tools, index, "map");
  const outTools = orderedTools(tools, index, "not-adopted");
  const width = Math.max(600, ...index.tools.map((i) => i.position.x_px + NODE_W + 40));
  const height = Math.max(300, ...index.tools.map((i) => i.position.y_px + NODE_H + 40));

  const renderNode = ({ tool, info }: { tool: StudioTool; info: InfoEntry }) => {
    const Icon = LICENCE_ICONS[tool.licence_class] ?? Lock;
    const { x_px: x, y_px: y } = info.position;
    const name = clip(tool.name);
    const shown = name.length > NAME_CHARS ? `${name.slice(0, NAME_CHARS - 1)}…` : name;
    return (
      <Link
        key={tool.id}
        to={`/studio/tools/${encodeURIComponent(tool.id)}/`}
        data-testid="tool-node"
        data-tool={tool.id}
        data-lane={tool.lane}
        data-ring={tool.ring}
        data-licence-class={tool.licence_class}
        data-status={tool.status}
        data-x={x}
        data-y={y}
        aria-label={nodeLabel(tool, tool.lane, tool.ring, tool.licence_class, tool.status)}
        className={styles.mapNode}
      >
        <rect
          x={x}
          y={y}
          width={NODE_W}
          height={NODE_H}
          rx={6}
          className={styles.mapNodeBox}
          data-lane={tool.lane}
        />
        <text x={x + 10} y={y + 20} className={styles.mapNodeName}>
          {shown}
        </text>
        <text x={x + 10} y={y + 38} data-testid="lane-label" className={styles.mapNodeMeta}>
          {t(`lane.${tool.lane}`)}
        </text>
        <text x={x + 90} y={y + 38} data-testid="ring-badge" className={styles.mapNodeMeta}>
          {tool.ring}
        </text>
        <g data-testid="licence-icon">
          <Icon size={16} x={x + NODE_W - 26} y={y + 6} />
        </g>
        {tool.status === "not-yet-run" && (
          <text x={x + 10} y={y + 56} className={styles.mapNodeNote}>
            {t("notYetRun")}
          </text>
        )}
      </Link>
    );
  };

  const neighbours = (id: string, dir: "in" | "out") =>
    index.edges
      .filter((e) => (dir === "in" ? e.to === id : e.from === id))
      .map((e) => (dir === "in" ? e.from : e.to))
      .join(", ");

  return (
    <section data-testid="static-map" className={styles.staticMap}>
      <svg
        role="img"
        aria-label={t("map.alt")}
        viewBox={`0 0 ${width} ${height}`}
        width="100%"
        className={styles.mapSvg}
        hidden={hideSvg}
      >
        {index.edges.map((edge) => {
          const g = edgeGeometry(edge, positions);
          if (!g) return null;
          const label =
            edge.state === "observed"
              ? `${edge.kind} · ${t("map.observed", { run: clip(edge.evidence?.run_id ?? "") })}`
              : `${edge.kind} · ${t("map.planned")}`;
          return (
            <g
              key={`${edge.from}>${edge.to}>${edge.kind}`}
              data-testid="map-edge"
              data-from={edge.from}
              data-to={edge.to}
              data-kind={edge.kind}
              data-state={edge.state}
            >
              <path
                d={g.d}
                fill="none"
                className={styles.mapEdge}
                {...(edge.state === "planned" ? { strokeDasharray: "6 4" } : {})}
              />
              <text x={g.lx} y={g.ly - 4} textAnchor="middle" className={styles.mapEdgeLabel}>
                {label}
              </text>
            </g>
          );
        })}
        <g data-testid="map-group">{mapTools.map(renderNode)}</g>
        <g data-testid="not-adopted-group" aria-label={t("map.notAdopted")}>
          {outTools.length > 0 && (
            <text
              x={Math.min(...outTools.map((e) => e.info.position.x_px))}
              y={Math.min(...outTools.map((e) => e.info.position.y_px)) - 8}
              className={styles.mapGroupLabel}
            >
              {t("map.notAdopted")}
            </text>
          )}
          {outTools.map(renderNode)}
        </g>
      </svg>
      <table data-testid="tool-table" className={styles.table}>
        <caption>{t("map.tableCaption")}</caption>
        <thead>
          <tr>
            {["tool", "env", "lane", "ring", "licence", "status", "inbound", "outbound"].map((c) => (
              <th key={c} scope="col">
                {t(`map.col.${c}`)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {[...mapTools, ...outTools].map(({ tool }) => (
            <tr key={tool.id} data-tool={tool.id}>
              <td>
                <Link to={`/studio/tools/${encodeURIComponent(tool.id)}/`}>{clip(tool.name)}</Link>
              </td>
              <td>{tool.envs.join(", ")}</td>
              <td>{t(`lane.${tool.lane}`)}</td>
              <td>{tool.ring}</td>
              <td>{tool.licence_class}</td>
              <td>{t(`status.${statusKey(tool.status)}`)}</td>
              <td>{neighbours(tool.id, "in")}</td>
              <td>{neighbours(tool.id, "out")}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
