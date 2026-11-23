// The 3D chunk of the terrain view (FR-018-01, FR-018-07, ADR-0038): three.js through React Three Fiber, the 3D Tiles renderer for the
// published tilesets, drei orbit controls. This file and everything it imports load by dynamic import after hydration, so none of it
// is part of the initial JavaScript of a page (NFR-018-02).
//
// One renderer owns one canvas: `createRenderer` makes a WebGPURenderer for the canvas R3F hands over and records its backend; with
// `?renderer=webgl`, or where WebGPU cannot start, the same class runs its WebGL 2 backend. A WebGL 2 context is never requested on a
// canvas that took a WebGPU one, because the renderer decides the backend once, before it touches the canvas.
import { OrbitControls } from "@react-three/drei";
import { Canvas, type RootState, useFrame, useThree } from "@react-three/fiber";
import { TilesRenderer } from "3d-tiles-renderer/three";
import { type ComponentRef, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { type Camera, type Object3D, Sphere, Vector3, type WebGLRenderer } from "three";
import { WebGPURenderer } from "three/webgpu";

export type RendererKind = "webgpu" | "webgl2";

export interface TileProgress {
  /** Tiles being fetched or parsed right now. */
  active: number;
  /** Tiles of this tileset that are loaded and shown. */
  loaded: number;
}

export interface TerrainCanvasProps {
  lod0Url: string;
  /** Set after the visitor asked for more detail; cleared again to stop and unload it. */
  detailUrl: string | null;
  summaryId: string;
  label: string;
  motion: "full" | "reduced";
  /** Changes when the visitor pressed "Reset view". */
  resetKey: number;
  onRenderer: (kind: RendererKind) => void;
  onProgress: (which: "lod0" | "detail", progress: TileProgress) => void;
  onError: (which: "lod0" | "detail") => void;
}

interface RendererRecord {
  canvasId: string;
  kind: RendererKind;
  purpose: "scene" | "splat";
}

let canvasCounter = 0;
const records: RendererRecord[] = [];

/** `window.__pitstudio.renderers`: one record per live renderer, the id of its canvas (the E2E tests read it). */
function registerRenderer(record: RendererRecord): () => void {
  const w = window as unknown as { __pitstudio?: Record<string, unknown> };
  w.__pitstudio = { ...(w.__pitstudio ?? {}), renderers: records };
  records.push(record);
  return () => {
    const i = records.indexOf(record);
    if (i >= 0) records.splice(i, 1);
  };
}

export function wantsWebGL(search: string): boolean {
  return new URLSearchParams(search).get("renderer") === "webgl";
}

async function createRenderer(
  props: { canvas: HTMLCanvasElement | OffscreenCanvas },
  forceWebGL: boolean,
): Promise<{ renderer: WebGLRenderer; kind: RendererKind }> {
  const canvas = props.canvas as HTMLCanvasElement;
  const renderer = new WebGPURenderer({ canvas, antialias: true, forceWebGL });
  await renderer.init();
  const kind: RendererKind = (renderer.backend as { isWebGPUBackend?: boolean }).isWebGPUBackend
    ? "webgpu"
    : "webgl2";
  canvasCounter += 1;
  canvas.id = `scene-canvas-${canvasCounter}`;
  canvas.dataset.renderer = kind;
  const unregister = registerRenderer({ canvasId: canvas.id, kind, purpose: "scene" });
  const dispose = renderer.dispose.bind(renderer);
  renderer.dispose = () => {
    unregister();
    return dispose();
  };
  return { renderer: renderer as unknown as WebGLRenderer, kind };
}

const SPHERE = new Sphere();
const CENTER = new Vector3();

interface Framing {
  center: Vector3;
  radius: number;
}

/** One 3D Tiles tileset in the scene; the group turns the tileset's Z-up site frame into three.js Y-up. */
function Tiles({
  url,
  which,
  errorTarget,
  hidden,
  onFrame,
  onProgress,
  onError,
}: {
  url: string;
  which: "lod0" | "detail";
  errorTarget: number;
  hidden: boolean;
  onFrame?: (framing: Framing) => void;
  onProgress: TerrainCanvasProps["onProgress"];
  onError: TerrainCanvasProps["onError"];
}) {
  const { camera, gl, scene } = useThree();
  const tiles = useMemo(() => new TilesRenderer(url), [url]);
  const callbacks = useRef({ onFrame, onProgress, onError });
  callbacks.current = { onFrame, onProgress, onError };
  const last = useRef(0);

  useEffect(() => {
    tiles.group.rotation.x = -Math.PI / 2;
    tiles.setCamera(camera as Camera);
    scene.add(tiles.group as Object3D);
    return () => {
      scene.remove(tiles.group as Object3D);
      tiles.dispose();
    };
  }, [tiles, camera, scene]);

  useEffect(() => {
    tiles.errorTarget = errorTarget;
  }, [tiles, errorTarget]);

  useEffect(() => {
    tiles.group.visible = !hidden;
  }, [tiles, hidden]);

  useEffect(() => {
    const framed = () => {
      tiles.group.updateMatrixWorld(true);
      if (callbacks.current.onFrame && tiles.getBoundingSphere(SPHERE)) {
        CENTER.copy(SPHERE.center).applyMatrix4(tiles.group.matrixWorld);
        callbacks.current.onFrame({ center: CENTER.clone(), radius: SPHERE.radius });
      }
    };
    const failed = () => callbacks.current.onError(which);
    tiles.addEventListener("load-tile-set", framed);
    tiles.addEventListener("load-error", failed);
    return () => {
      tiles.removeEventListener("load-tile-set", framed);
      tiles.removeEventListener("load-error", failed);
    };
  }, [tiles, which]);

  useFrame((state) => {
    tiles.setResolutionFromRenderer(camera as Camera, gl as unknown as WebGLRenderer);
    tiles.group.updateMatrixWorld(true);
    tiles.update();
    const stats = (tiles as unknown as { stats: { downloading: number; parsing: number } }).stats;
    const now = state.clock.elapsedTime;
    if (now - last.current > 0.25) {
      last.current = now;
      callbacks.current.onProgress(which, {
        active: stats.downloading + stats.parsing,
        loaded: tiles.visibleTiles?.size ?? 0,
      });
    }
  });
  return null;
}

/** Orbit controls with keyboard operation: arrow keys pan and rotate, plus and minus zoom. */
function Controls({
  motion,
  resetKey,
  target,
}: {
  motion: "full" | "reduced";
  resetKey: number;
  target: Framing | null;
}) {
  const { camera, gl } = useThree();
  const controls = useRef<ComponentRef<typeof OrbitControls>>(null);

  useEffect(() => {
    const c = controls.current;
    if (!c) return;
    c.listenToKeyEvents(gl.domElement);
    const onKey = (e: KeyboardEvent) => {
      const factor = e.key === "+" || e.key === "=" ? 0.85 : e.key === "-" ? 1.18 : null;
      if (factor === null) return;
      camera.position.sub(c.target).multiplyScalar(factor).add(c.target);
      c.update();
      e.preventDefault();
    };
    gl.domElement.addEventListener("keydown", onKey);
    return () => gl.domElement.removeEventListener("keydown", onKey);
  }, [camera, gl]);

  // resetKey is a trigger: pressing "Reset view" frames the terrain again
  // biome-ignore lint/correctness/useExhaustiveDependencies: resetKey only re-runs the framing
  useEffect(() => {
    const c = controls.current;
    if (!c || !target) return;
    c.target.copy(target.center);
    camera.position.set(
      target.center.x,
      target.center.y + target.radius * 1.1,
      target.center.z + target.radius * 1.9,
    );
    camera.lookAt(target.center);
    c.update();
  }, [camera, target, resetKey]);

  return (
    <OrbitControls
      ref={controls as never}
      makeDefault
      enableDamping={motion === "full"}
      dampingFactor={0.08}
      maxPolarAngle={Math.PI * 0.495}
      keyPanSpeed={40}
    />
  );
}

export default function TerrainCanvas(props: TerrainCanvasProps) {
  const forceWebGL = typeof location !== "undefined" && wantsWebGL(location.search);
  const [target, setTarget] = useState<Framing | null>(null);
  const [detailShown, setDetailShown] = useState(false);
  const { detailUrl, onProgress } = props;

  useEffect(() => {
    if (!detailUrl) setDetailShown(false);
  }, [detailUrl]);
  const progress = useCallback<TerrainCanvasProps["onProgress"]>(
    (which, p) => {
      if (which === "detail" && p.loaded > 0) setDetailShown(true);
      onProgress(which, p);
    },
    [onProgress],
  );

  return (
    <Canvas
      camera={{ fov: 45, near: 5, far: 40000, position: [0, 2500, 3500] }}
      frameloop="always"
      dpr={[1, 2]}
      gl={async (p) => (await createRenderer(p as { canvas: HTMLCanvasElement }, forceWebGL)).renderer}
      onCreated={(state: RootState) => {
        const el = state.gl.domElement;
        el.setAttribute("data-testid", "scene-canvas");
        el.setAttribute("aria-describedby", props.summaryId);
        el.setAttribute("aria-label", props.label);
        el.setAttribute("role", "img");
        el.tabIndex = 0;
        props.onRenderer(el.dataset.renderer === "webgpu" ? "webgpu" : "webgl2");
      }}
    >
      <color attach="background" args={["#cfd8dc"]} />
      <hemisphereLight args={["#e6eef5", "#6d5f52", 1.1]} />
      <directionalLight position={[1500, 2500, 1200]} intensity={2.2} />
      <Tiles
        url={props.lod0Url}
        which="lod0"
        errorTarget={16}
        hidden={detailShown}
        onFrame={setTarget}
        onProgress={progress}
        onError={props.onError}
      />
      {detailUrl && (
        <Tiles
          url={detailUrl}
          which="detail"
          errorTarget={8}
          hidden={false}
          onProgress={progress}
          onError={props.onError}
        />
      )}
      <Controls motion={props.motion} resetKey={props.resetKey} target={target} />
    </Canvas>
  );
}
