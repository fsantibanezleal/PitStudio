// T-018-113 [red] · NFR-018-01 (first view at most 2 MB encoded) and FR-020-55 (the reader draws the chart series of the published
// runs): what a case page needs for its first view is requested once and only when it is wanted. The web manifest is fetched once
// for every component of a page (it was fetched once per component, ten times on a case page); a published run's chart files are
// requested when its chart list is opened, not when the page loads; a still below the fold is requested when it nears the viewport.
// Oracles: the counts of `fetch` calls and of `src` attributes the tests make themselves (arithmetic, no reference implementation);
// the measure of 2026-11-24 on the built site: nine extra manifest fetches (13.4 KB gzip each), 15 chart files (about 470 KB gzip) on
// the C1 Scene tab and three stills (about 750 KB) loaded with the page.
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { RunChartList } from "~/charts/RunCharts";
import { renderApp } from "~/test-support/render";
import { LazyImg } from "./LazyImg";
import { useWebManifest } from "./manifest";

const RUN = "20261124T100000Z-a3-dem-repose-20k";

function record(id: string, kind: string) {
  return {
    id,
    run_id: RUN,
    git_sha: "abcdef0123456789abcdef0123456789abcdef01",
    path: `assets/${RUN}/${id}.json`,
    bytes: 100,
    sha256: "1".repeat(64),
    kind,
    producer: { tool: "pitstudio", stage: { id: "s50_evaluate" } },
    inputs: [],
    cases: ["A3"],
    lane: "static",
    licence_class: "own",
    spdx: "CC-BY-4.0",
  };
}

function stubFetch(files: Record<string, unknown>) {
  const fn = vi.fn(async (url: string) => {
    const key = String(url).replace(/^.*?(assets\/)/, "$1");
    return key in files ? { ok: true, json: async () => files[key] } : { ok: false, json: async () => null };
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}
const calls = (fn: ReturnType<typeof vi.fn>, part: string) =>
  fn.mock.calls.filter((c) => String(c[0]).includes(part)).length;

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("NFR-018-01 · the web manifest is fetched once for the whole page", () => {
  function Probe({ name }: { name: string }) {
    const m = useWebManifest();
    return <span data-testid={name}>{m.status}</span>;
  }

  it("NFR-018-01 · five components that read the manifest cause one request", async () => {
    const fetchFn = stubFetch({
      "assets/manifest.json": { kind: "web-index", artefacts: [record("a", "chart-series")] },
    });
    await renderApp(
      <>
        {["a", "b", "c", "d", "e"].map((n) => (
          <Probe key={n} name={n} />
        ))}
      </>,
    );
    await waitFor(() => expect(screen.getByTestId("e").textContent).toBe("ready"));
    expect(calls(fetchFn, "assets/manifest.json")).toBe(1);
  });

  it("NFR-018-01 · a failing manifest is nothing published for every consumer, with one request", async () => {
    const fetchFn = stubFetch({});
    await renderApp(
      <>
        <Probe name="a" />
        <Probe name="b" />
      </>,
    );
    await waitFor(() => expect(screen.getByTestId("b").textContent).toBe("ready"));
    expect(calls(fetchFn, "assets/manifest.json")).toBe(1);
  });
});

describe("FR-020-55 · the chart files of a run are requested when its list is opened", () => {
  it("FR-020-55 · the closed list names the count from the manifest and requests no chart file", async () => {
    const fetchFn = stubFetch({
      "assets/manifest.json": {
        kind: "web-index",
        artefacts: [record("one", "chart-series"), record("two", "chart-series"), record("x", "table")],
      },
    });
    await renderApp(<RunChartList caseId="A3" runId={RUN} />);
    const list = await screen.findByTestId("run-charts");
    expect(list.textContent).toContain("(2)");
    await new Promise((r) => setTimeout(r, 50));
    expect(calls(fetchFn, `${RUN}/one.json`) + calls(fetchFn, `${RUN}/two.json`)).toBe(0);
    expect(list.hasAttribute("open")).toBe(false);
  });

  it("FR-020-55 · opening the list requests the chart files of that run", async () => {
    const fetchFn = stubFetch({
      "assets/manifest.json": { kind: "web-index", artefacts: [record("one", "chart-series")] },
    });
    await renderApp(<RunChartList caseId="A3" runId={RUN} />);
    const list = (await screen.findByTestId("run-charts")) as HTMLDetailsElement;
    list.open = true;
    fireEvent(list, new Event("toggle"));
    await waitFor(() => expect(calls(fetchFn, `${RUN}/one.json`)).toBe(1));
  });

  it("FR-020-55 · a run with no chart-series artefact has no list", async () => {
    stubFetch({ "assets/manifest.json": { kind: "web-index", artefacts: [record("x", "table")] } });
    await renderApp(<RunChartList caseId="A3" runId={RUN} />);
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByTestId("run-charts")).toBeNull();
  });
});

describe("NFR-018-01 · a still is requested when it nears the viewport", () => {
  type Callback = (entries: Array<{ isIntersecting: boolean }>) => void;
  let callbacks: Callback[] = [];
  beforeEach(() => {
    callbacks = [];
    class FakeObserver {
      constructor(cb: Callback) {
        callbacks.push(cb);
      }
      observe() {}
      disconnect() {}
      unobserve() {}
    }
    vi.stubGlobal("IntersectionObserver", FakeObserver);
  });

  it("NFR-018-01 · the image has no src before it intersects and its src after", () => {
    render(<LazyImg src="/assets/x.webp" alt="a still" />);
    const img = screen.getByAltText("a still");
    expect(img.hasAttribute("src")).toBe(false);
    act(() => callbacks[0]?.([{ isIntersecting: false }]));
    expect(img.hasAttribute("src")).toBe(false);
    act(() => callbacks[0]?.([{ isIntersecting: true }]));
    expect(img.getAttribute("src")).toBe("/assets/x.webp");
  });

  it("NFR-018-01 · the box keeps its place (width and height attributes) so the page does not jump", () => {
    render(<LazyImg src="/assets/x.webp" alt="a still" width={1920} height={1080} />);
    const img = screen.getByAltText("a still");
    expect(img.getAttribute("width")).toBe("1920");
    expect(img.getAttribute("height")).toBe("1080");
  });

  it("NFR-018-01 · a browser without IntersectionObserver gets the image at once", () => {
    vi.stubGlobal("IntersectionObserver", undefined);
    render(<LazyImg src="/assets/y.webp" alt="b still" />);
    expect(screen.getByAltText("b still").getAttribute("src")).toBe("/assets/y.webp");
  });
});
