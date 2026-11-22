// T-018-096 [red] · FR-018-73: the rendered scene section of a case page. A published render run (summary `render.json` plus the NVENC
// pair, the WebP poster and the stills of the run) is shown from one component on every case page: poster and stills at once, the
// video only after a click (ADR-0038 line 67: no autoplay, no bytes before a user action, MediaCapabilities picks the file), the
// producer attribution in place on the visual, the tools in Built with. A newer run replaces the older by publishing alone.
// Oracles: the summary shape written by `studio import-run` kind render (tests/unit/test_import_run.py), the FR text, the owner's
// attribution label "Rendered with NVIDIA Omniverse RTX (ovrtx)" (2026-11-22).
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { loadCaseRegistry } from "~/test-support/fixtures";
import { renderApp } from "~/test-support/render";
import { deriveBuiltWith, type ToolInfo } from "./builtWith";
import { type RenderModel, readRender, renderCandidates } from "./sceneRender";
import { SceneRender } from "./SceneRender";
import type { ArtefactRecord, CaseEntry } from "./types";

const RUN = "20261122T060455Z-bingham-flyover";
const NEWER = "20261123T010000Z-bingham-flyover";
const LABEL = "Rendered with NVIDIA Omniverse RTX (ovrtx)";
const SHA = (c: string) => c.repeat(64);

function art(id: string, run: string, extra: Record<string, unknown> = {}): ArtefactRecord {
  return {
    id,
    run_id: run,
    git_sha: "a".repeat(40),
    path: `assets/${run}/${id}.bin`,
    bytes: 1000,
    sha256: SHA("1"),
    kind: "image",
    producer: { tool: "nvenc-ffmpeg", stage: { id: "st56_encode" } },
    inputs: [],
    lane: "static",
    licence_class: "own",
    spdx: "CC-BY-4.0",
    ...extra,
  } as ArtefactRecord;
}

function video(id: string, run: string, codec: "av1" | "h264", bytes: number, sha: string): ArtefactRecord {
  const [width, height] = codec === "av1" ? [1920, 1080] : [1280, 720];
  return art(id, run, {
    kind: "video",
    lane: "replay",
    path: `assets/${run}/${id}.mp4`,
    bytes,
    sha256: sha,
    media_type: "video/mp4",
    encoder: { codec, width, height, fps: 30, duration_s: 20 },
  });
}

function published(run: string, bytes = new Uint8Array([1, 2, 3, 4])): ArtefactRecord[] {
  return [
    art("bingham-flyover-render", run, { kind: "table", path: `assets/${run}/render.json` }),
    video("bingham-flyover-av1", run, "av1", bytes.length, SHA("a")),
    video("bingham-flyover-h264", run, "h264", bytes.length, SHA("b")),
    art("bingham-flyover-poster", run, { path: `assets/${run}/bingham-flyover.webp` }),
    art("bingham-flyover-still-0s", run, { path: `assets/${run}/flyover-0s.webp` }),
    art("bingham-flyover-still-10s", run, { path: `assets/${run}/flyover-10s.webp` }),
    art("bingham-flyover-still-20s", run, { path: `assets/${run}/flyover-20s.webp` }),
  ];
}

function summary(run: string, over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    schema_version: "1.0",
    kind: "render-summary",
    run_id: run,
    label: LABEL,
    title: { en: "Bingham Canyon flyover, rendered with NVIDIA Omniverse RTX", es: "Sobrevuelo de Bingham Canyon" },
    producer: { tool: "ovrtx", version: "0.5.0.377615" },
    scene: { id: "a1-bingham" },
    built_with: ["openusd", "ovrtx", "nvenc-ffmpeg"],
    resolution: [1920, 1080],
    fps: 30,
    duration_s: 20,
    video: {
      id: "bingham-flyover",
      files: ["bingham-flyover-av1", "bingham-flyover-h264"],
      poster: "bingham-flyover-poster",
    },
    stills: [
      { artefact: "bingham-flyover-still-20s", t_s: 20 },
      { artefact: "bingham-flyover-still-0s", t_s: 0 },
      { artefact: "bingham-flyover-still-10s", t_s: 10 },
    ],
    ...over,
  };
}

const tools: ToolInfo[] = [
  { id: "openusd", name: "OpenUSD", version: "26.5", licence: "Apache-2.0" },
  { id: "ovrtx", name: "ovrtx", version: "0.5.0.377615", licence: "LicenseRef-NvidiaProprietary" },
  { id: "nvenc-ffmpeg", name: "NVENC / FFmpeg", version: "8.1.3", licence: "LGPL-2.1-or-later" },
];

function model(run = RUN, bytes?: Uint8Array): RenderModel {
  const arts = published(run, bytes);
  const m = readRender(summary(run), arts, arts[0] as ArtefactRecord);
  expect(m).not.toBeNull();
  return m as RenderModel;
}

describe("FR-018-73 which render a case page shows", () => {
  it("lists the render summaries that apply to the case, newest run first, and nothing else", () => {
    const arts = [
      ...published(RUN),
      ...published(NEWER),
      art("c1-results", NEWER, { kind: "table", cases: ["C1"] }),
      art("other-render", NEWER, { kind: "table", path: `assets/${NEWER}/other.json` }),
      art("a2-flyover-render", NEWER, { kind: "table", cases: ["A2"], path: `assets/${NEWER}/render.json` }),
    ];
    expect(renderCandidates(arts, "C1").map((a) => a.run_id)).toEqual([NEWER, RUN]);
    expect(renderCandidates(arts, "A2").map((a) => a.id)).toEqual([
      "a2-flyover-render",
      "bingham-flyover-render",
      "bingham-flyover-render",
    ]);
    expect(renderCandidates([], "C1")).toEqual([]);
  });
});

describe("FR-018-73 reading a published render summary", () => {
  it("builds the model: label, producer, built-with tools, the pair, the poster and the stills by flyover time", () => {
    const m = model();
    expect(m.runId).toBe(RUN);
    expect(m.label).toBe(LABEL);
    expect(m.producer).toEqual({ tool: "ovrtx", version: "0.5.0.377615" });
    expect(m.builtWith).toEqual(["openusd", "ovrtx", "nvenc-ffmpeg"]);
    expect(m.video?.files.map((f) => [f.encoder.codec, f.encoder.height])).toEqual([
      ["av1", 1080],
      ["h264", 720],
    ]);
    expect(m.video?.poster?.path).toBe(`assets/${RUN}/bingham-flyover.webp`);
    expect(m.stills.map((s) => s.tS)).toEqual([0, 10, 20]);
    expect(m.stills.map((s) => s.artefact.path)).toEqual([
      `assets/${RUN}/flyover-0s.webp`,
      `assets/${RUN}/flyover-10s.webp`,
      `assets/${RUN}/flyover-20s.webp`,
    ]);
  });

  it("keeps the poster and the stills when the video files are not in the index", () => {
    const arts = published(RUN).filter((a) => a.kind !== "video");
    const m = readRender(summary(RUN), arts, arts[0] as ArtefactRecord);
    expect(m?.video).toBeNull();
    expect(m?.stills).toHaveLength(3);
  });

  it("refuses a summary that is damaged, of another run, without a label or of another kind", () => {
    const arts = published(RUN);
    const head = arts[0] as ArtefactRecord;
    for (const bad of [
      null,
      "text",
      [],
      summary(RUN, { kind: "run" }),
      summary(RUN, { label: "" }),
      summary(RUN, { label: 7 }),
      summary(RUN, { run_id: NEWER }),
      summary(RUN, { producer: { tool: "ovrtx" } }),
      summary(RUN, { stills: "none" }),
    ])
      expect(readRender(bad, arts, head)).toBeNull();
  });

  it("drops a still or a video that belongs to another run or is not an image or a video", () => {
    const arts = [
      ...published(RUN).filter((a) => a.id !== "bingham-flyover-still-10s"),
      art("bingham-flyover-still-10s", NEWER, { path: `assets/${NEWER}/x.webp` }),
    ];
    const m = readRender(summary(RUN), arts, arts[0] as ArtefactRecord);
    expect(m?.stills.map((s) => s.tS)).toEqual([0, 20]);
  });
});

const yes = { supported: true, smooth: true, powerEfficient: true };
const no = { supported: false, smooth: false, powerEfficient: false };

function caps(av1: unknown, h264: unknown) {
  return {
    decodingInfo: vi.fn(async (c: { video: { contentType: string } }) => (c.video.contentType.includes("av01") ? av1 : h264)),
  };
}

async function sha256(bytes: Uint8Array): Promise<string> {
  const d = await crypto.subtle.digest("SHA-256", bytes as BufferSource);
  return [...new Uint8Array(d)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function serving(bytes: Uint8Array) {
  const sha = await sha256(bytes);
  const m = model(RUN, bytes);
  for (const f of m.video?.files ?? []) m.video!.sha256ByPath[f.path] = sha;
  const fetchImpl = vi.fn(async () => new Response(bytes as BodyInit, { status: 200 }));
  return { m, fetchImpl: fetchImpl as unknown as typeof fetch, calls: fetchImpl };
}

function stubMedia() {
  const play = vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
  vi.spyOn(HTMLMediaElement.prototype, "load").mockImplementation(() => undefined);
  if (!URL.createObjectURL) URL.createObjectURL = () => "blob:render";
  vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:render");
  return play;
}

describe("FR-018-73 the section on a case page", () => {
  it("shows the poster and the stills at once, the label in place and the tools, and loads no video before a click", async () => {
    const { m, fetchImpl, calls } = await serving(new Uint8Array([9, 9, 9]));
    await renderApp(<SceneRender state={{ status: "ready", model: m }} tools={tools} fetchImpl={fetchImpl} mediaCapabilities={caps(yes, yes)} />);
    const section = screen.getByTestId("scene-render");
    const el = section.querySelector("video") as HTMLVideoElement;
    expect(el.getAttribute("preload")).toBe("none");
    expect(el.hasAttribute("autoplay")).toBe(false);
    expect(el.hasAttribute("src")).toBe(false);
    expect(el.getAttribute("poster")).toMatch(new RegExp(`assets/${RUN}/bingham-flyover\\.webp$`));
    expect(within(section).getAllByRole("img")).toHaveLength(3);
    expect(section.querySelector("[data-producer='render']")?.textContent).toContain(LABEL);
    expect(section.querySelector("[data-producer='render']")?.textContent).toContain("0.5.0.377615");
    for (const fig of section.querySelectorAll("figure[data-still]")) expect(fig.textContent).toContain(LABEL);
    expect(["0 s", "10 s", "20 s"].every((t) => section.textContent?.includes(t))).toBe(true);
    const built = within(section).getByTestId("render-built-with");
    for (const id of ["openusd", "ovrtx", "nvenc-ffmpeg"]) expect(built.querySelector(`[data-chip='${id}']`)).not.toBeNull();
    expect(built.querySelector("[data-chip='ovrtx']")?.getAttribute("data-nvidia")).toBe("true");
    expect(calls).not.toHaveBeenCalled();
  });

  it("loads the AV1 file after a click when the browser decodes it efficiently, and plays it without autoplay before", async () => {
    const play = stubMedia();
    const { m, fetchImpl, calls } = await serving(new Uint8Array([1, 2, 3]));
    await renderApp(<SceneRender state={{ status: "ready", model: m }} tools={tools} fetchImpl={fetchImpl} mediaCapabilities={caps(yes, yes)} />);
    expect(play).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: /play/i }));
    await waitFor(() => expect(calls).toHaveBeenCalledTimes(1));
    expect(String(calls.mock.calls[0]?.[0])).toMatch(/bingham-flyover-av1\.mp4$/);
    await waitFor(() => expect(play).toHaveBeenCalled());
    expect(screen.getByTestId("scene-render").querySelector("video")?.getAttribute("src")).toBe("blob:render");
  });

  it("falls back to the H.264 file when AV1 is not power efficient", async () => {
    stubMedia();
    const { m, fetchImpl, calls } = await serving(new Uint8Array([1, 2, 3]));
    await renderApp(
      <SceneRender state={{ status: "ready", model: m }} tools={tools} fetchImpl={fetchImpl} mediaCapabilities={caps({ ...yes, powerEfficient: false }, yes)} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /play/i }));
    await waitFor(() => expect(calls).toHaveBeenCalledTimes(1));
    expect(String(calls.mock.calls[0]?.[0])).toMatch(/bingham-flyover-h264\.mp4$/);
  });

  it("says so, with the poster and the stills intact, when the browser decodes neither file or the download fails", async () => {
    stubMedia();
    const { m, fetchImpl, calls } = await serving(new Uint8Array([1]));
    const first = await renderApp(<SceneRender state={{ status: "ready", model: m }} tools={tools} fetchImpl={fetchImpl} mediaCapabilities={caps(no, no)} />);
    fireEvent.click(screen.getByRole("button", { name: /play/i }));
    expect((await screen.findByRole("status")).textContent).toMatch(/not available in this browser/i);
    expect(calls).not.toHaveBeenCalled();
    first.unmount();
    const failing = vi.fn(async () => {
      throw new Error("offline");
    }) as unknown as typeof fetch;
    await renderApp(<SceneRender state={{ status: "ready", model: m }} tools={tools} fetchImpl={failing} mediaCapabilities={caps(yes, yes)} />);
    fireEvent.click(screen.getByRole("button", { name: /play/i }));
    expect((await screen.findByRole("status")).textContent).toMatch(/could not be loaded/i);
    const section = screen.getByTestId("scene-render");
    expect(section.querySelector("video")?.getAttribute("poster")).toBeTruthy();
    expect(within(section).getAllByRole("img")).toHaveLength(3);
  });

  it("refuses a file whose SHA-256 differs from the manifest", async () => {
    stubMedia();
    const { m, fetchImpl } = await serving(new Uint8Array([1, 2, 3]));
    for (const f of m.video?.files ?? []) (m.video as NonNullable<RenderModel["video"]>).sha256ByPath[f.path] = SHA("0");
    await renderApp(<SceneRender state={{ status: "ready", model: m }} tools={tools} fetchImpl={fetchImpl} mediaCapabilities={caps(yes, yes)} />);
    fireEvent.click(screen.getByRole("button", { name: /play/i }));
    expect((await screen.findByRole("status")).textContent).toMatch(/integrity check failed/i);
    expect(screen.getByTestId("scene-render").querySelector("video")?.hasAttribute("src")).toBe(false);
  });

  it("works with the video absent: poster and stills, no play button", async () => {
    const m = { ...model(), video: null } satisfies RenderModel;
    await renderApp(<SceneRender state={{ status: "ready", model: m }} tools={tools} />);
    const section = screen.getByTestId("scene-render");
    expect(within(section).queryByRole("button", { name: /play/i })).toBeNull();
    expect(section.querySelector("video")).toBeNull();
    expect(within(section).getAllByRole("img").length).toBe(3);
    expect(section.querySelector("[data-producer='render']")?.textContent).toContain(LABEL);
  });

  it("says Not yet run when no render is published, and nothing while the manifest loads", async () => {
    const view = await renderApp(<SceneRender state={{ status: "ready", model: null }} tools={tools} />);
    expect(screen.getByTestId("scene-render").textContent).toMatch(/not yet run/i);
    view.unmount();
    const loading = await renderApp(<SceneRender state={{ status: "loading", model: null }} tools={tools} />);
    expect(loading.container.querySelector("[data-testid='scene-render']")).toBeNull();
  });

  it("is translated: the Spanish section has its own title and no English control label", async () => {
    await renderApp(<SceneRender state={{ status: "ready", model: model() }} tools={tools} />, { lang: "es" });
    const section = screen.getByTestId("scene-render");
    expect(section.querySelector("h2")?.textContent).not.toMatch(/rendered scene/i);
    expect(within(section).getByRole("button").textContent).not.toMatch(/play the flyover/i);
  });
});

describe("FR-018-72 and FR-018-73 the render tools in Built with", () => {
  const entry = loadCaseRegistry().cases.C1 as unknown as CaseEntry;
  const methods = [{ id: "M14", name: { en: "Slope forecasting", es: "Pronostico" }, slug: "m14" }];

  it("adds the tools of the published render to every case as used, NVIDIA tools in the Omniverse group", () => {
    expect(Object.keys(entry.tools)).not.toContain("ovrtx");
    const g = deriveBuiltWith({
      entry,
      tools,
      methods,
      usedTools: new Set(),
      usedMethods: new Set(),
      lang: "en",
      renderTools: ["openusd", "ovrtx", "nvenc-ffmpeg", "not-a-tool"],
    });
    const used = (list: { id: string; status: string }[], id: string) => list.find((i) => i.id === id)?.status;
    expect(used(g.omniverse, "ovrtx")).toBe("used");
    expect(used(g.omniverse, "openusd")).toBe("used");
    expect(used(g.frameworks, "nvenc-ffmpeg")).toBe("used");
    expect([...g.omniverse, ...g.frameworks].some((i) => i.id === "not-a-tool")).toBe(false);
    expect(g.omniverse.find((i) => i.id === "ovrtx")?.href).toBe("/studio/tools/ovrtx/");
  });

  it("lists a tool once when the case already names it, and without render tools nothing changes", () => {
    const base = { entry, tools, methods, usedTools: new Set<string>(), usedMethods: new Set<string>(), lang: "en" as const };
    const plain = deriveBuiltWith(base);
    const same = deriveBuiltWith({ ...base, renderTools: [] });
    expect(same).toEqual(plain);
    const first = [...plain.omniverse, ...plain.frameworks][0]?.id as string;
    const again = deriveBuiltWith({ ...base, renderTools: [first] });
    expect([...again.omniverse, ...again.frameworks].filter((i) => i.id === first)).toHaveLength(1);
  });
});
