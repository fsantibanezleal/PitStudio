// The interactive tool map (FR-019-01, FR-019-05): React Flow at the build-time positions of the studio index. This module
// is only ever imported dynamically, after hydration, so React Flow belongs to no route's initial JavaScript (FR-019-03).
import "@xyflow/react/dist/style.css";
import {
  type Edge,
  type EdgeProps,
  getBezierPath,
  Handle,
  type Node,
  type NodeProps,
  Position,
  ReactFlow,
} from "@xyflow/react";
import { Lock } from "lucide-react";
import { type KeyboardEvent, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router";
import { clip } from "./format";
import { LICENCE_ICONS, NODE_H, NODE_W, nodeLabel, orderedTools, statusKey } from "./StaticMap";
import styles from "./studio.module.css";
import type { IndexEdgeJson, StudioIndex, StudioTool } from "./types";

interface ToolNodeData extends Record<string, unknown> {
  tool: StudioTool;
  band: string;
  order: number;
}

interface HandoffData extends Record<string, unknown> {
  edge: IndexEdgeJson;
}

function ToolNode({ data }: NodeProps<Node<ToolNodeData>>) {
  const { t } = useTranslation("studio");
  const navigate = useNavigate();
  const { tool, band, order } = data;
  const Icon = LICENCE_ICONS[tool.licence_class] ?? Lock;
  const to = `/studio/tools/${encodeURIComponent(tool.id)}/`;
  const onKeyDown = (event: KeyboardEvent<HTMLAnchorElement>) => {
    // Enter activates a link natively; Space does not, and the map promises both (FR-019-05).
    if (event.key === " ") {
      event.preventDefault();
      void navigate(to);
    }
  };
  return (
    <>
      <Handle type="target" position={Position.Left} isConnectable={false} className={styles.flowHandle} />
      <Link
        to={to}
        className={`nopan nodrag ${styles.flowNode}`}
        data-testid="tool-node"
        data-tool={tool.id}
        data-lane={tool.lane}
        data-ring={tool.ring}
        data-licence-class={tool.licence_class}
        data-status={tool.status}
        data-band={band}
        data-order={order}
        aria-label={nodeLabel(tool, tool.lane, tool.ring, tool.licence_class, tool.status)}
        onKeyDown={onKeyDown}
        style={{ width: NODE_W, height: NODE_H }}
      >
        <span className={styles.flowNodeHead}>
          <strong>{clip(tool.name)}</strong>
          <span data-testid="licence-icon">
            <Icon size={16} />
          </span>
        </span>
        <span className={styles.flowNodeMeta}>
          <span data-testid="lane-label">{t(`lane.${tool.lane}`)}</span>
          <span data-testid="ring-badge">{tool.ring}</span>
        </span>
        {tool.status === "not-yet-run" && <span className={styles.flowNodeNote}>{t("notYetRun")}</span>}
        {tool.status === "evaluated-not-adopted" && (
          <span className={styles.flowNodeNote}>{t(`status.${statusKey(tool.status)}`)}</span>
        )}
      </Link>
      <Handle type="source" position={Position.Right} isConnectable={false} className={styles.flowHandle} />
    </>
  );
}

function Handoff({
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
}: EdgeProps<Edge<HandoffData>>) {
  const { t } = useTranslation("studio");
  const edge = (data as HandoffData).edge;
  const [path, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
  });
  const label =
    edge.state === "observed"
      ? `${edge.kind} · ${t("map.observed", { run: clip(edge.evidence?.run_id ?? "") })}`
      : `${edge.kind} · ${t("map.planned")}`;
  return (
    <g
      data-testid="map-edge"
      data-from={edge.from}
      data-to={edge.to}
      data-kind={edge.kind}
      data-state={edge.state}
    >
      <path
        d={path}
        fill="none"
        className={styles.mapEdge}
        {...(edge.state === "planned" ? { strokeDasharray: "6 4" } : {})}
      />
      <text x={labelX} y={labelY - 4} textAnchor="middle" className={styles.mapEdgeLabel}>
        {label}
      </text>
    </g>
  );
}

const nodeTypes = { tool: ToolNode };
const edgeTypes = { handoff: Handoff };

export default function ToolMap({
  tools,
  index,
  onReady,
}: {
  tools: readonly StudioTool[];
  index: StudioIndex;
  onReady?: () => void;
}) {
  const [ready, setReady] = useState(false);
  const { t } = useTranslation("studio");

  const { nodes, edges, height } = useMemo(() => {
    const ordered = [...orderedTools(tools, index, "map"), ...orderedTools(tools, index, "not-adopted")];
    const nodes: Node<ToolNodeData>[] = ordered.map(({ tool, info }) => ({
      id: tool.id,
      type: "tool",
      position: { x: info.position.x_px, y: info.position.y_px },
      data: { tool, band: info.position.band, order: info.position.order },
      width: NODE_W,
      height: NODE_H,
      draggable: false,
      focusable: false,
      selectable: false,
    }));
    const edges: Edge<HandoffData>[] = index.edges.map((edge) => ({
      id: `${edge.from}>${edge.to}>${edge.kind}`,
      type: "handoff",
      source: edge.from,
      target: edge.to,
      data: { edge },
      focusable: false,
      selectable: false,
    }));
    const height = Math.max(320, ...index.tools.map((i) => i.position.y_px + NODE_H + 60));
    return { nodes, edges, height };
  }, [tools, index]);

  return (
    <section
      data-testid="tool-map"
      data-ready={ready ? "true" : "false"}
      className={styles.flowFrame}
      style={{ height }}
      aria-label={t("map.alt")}
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        fitView
        fitViewOptions={{ padding: 0.05 }}
        minZoom={0.3}
        maxZoom={1.5}
        nodesDraggable={false}
        nodesConnectable={false}
        nodesFocusable={false}
        edgesFocusable={false}
        elementsSelectable={false}
        zoomOnScroll={false}
        preventScrolling={false}
        onInit={() => {
          setReady(true);
          // the nodes are placed, focusable and clickable (NFR-019-02)
          performance.mark("studio:map-interactive");
          onReady?.();
        }}
      />
    </section>
  );
}
