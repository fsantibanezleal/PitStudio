// T-018-098 [red] · FR-018-75: the footer provenance line counts the runs the web manifest lists and says "no results published"
// only when it lists none; English and Spanish. Oracles: the FR text and the manifests the test serves (counts written by hand).
import { render, screen, waitFor } from "@testing-library/react";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { shellConfig } from "~/app/config";
import { provenanceItems } from "~/app/provenance";
import { makeArtefact, makeWebIndex } from "~/test-support/fixtures";
import { ShellConfigContext } from "./config";
import { Footer } from "./Footer";
import { i18n } from "./i18n";

const NONE = "No data, models or simulation results are published yet.";

function serve(index: unknown, ok = true) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({ ok, json: async () => index })),
  );
}

async function footer(lang: "en" | "es" = "en") {
  await i18n.changeLanguage(lang);
  return render(
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>
        <ShellConfigContext.Provider value={shellConfig}>
          <Footer />
        </ShellConfigContext.Provider>
      </MemoryRouter>
    </I18nextProvider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("FR-018-75 the provenance items", () => {
  it("FR-018-75 · counts the runs: none, one and several", () => {
    expect(provenanceItems(0)).toEqual([{ labelKey: "footer.provenanceNone" }]);
    expect(provenanceItems(1)).toEqual([
      { labelKey: "footer.provenanceRuns", values: { count: 1 }, href: "/studio/runs/" },
    ]);
    expect(provenanceItems(6)).toEqual([
      { labelKey: "footer.provenanceRuns", values: { count: 6 }, href: "/studio/runs/" },
    ]);
  });

  it("FR-018-75 · says nothing false while the manifest is still being read", () => {
    expect(provenanceItems(null)).toEqual([{ labelKey: "footer.provenanceLoading" }]);
  });
});

describe("FR-018-75 the footer of the app", () => {
  it("FR-018-75 · states how many runs are published, counting a run once however many artefacts it has", async () => {
    const index = makeWebIndex([
      makeArtefact({ id: "a", run_id: "20261011T083000Z-a1" }),
      makeArtefact({ id: "b", run_id: "20261011T083000Z-a1" }),
      makeArtefact({ id: "c", run_id: "20261012T083000Z-c1" }),
    ]);
    index.runs = [{ run_id: "20261013T083000Z-d1", manifest: "x/manifest.json", sha256: "0".repeat(64) }];
    serve(index);
    await footer();
    await waitFor(() => expect(screen.getByRole("contentinfo").textContent).toContain("3 published runs"));
    expect(screen.getByRole("contentinfo").textContent).not.toContain(NONE);
    expect(screen.getByRole("link", { name: /3 published runs/ }).getAttribute("href")).toBe("/studio/runs/");
  });

  it("FR-018-75 · uses the singular for one run", async () => {
    serve(makeWebIndex([makeArtefact()]));
    await footer();
    await waitFor(() => expect(screen.getByRole("contentinfo").textContent).toContain("1 published run"));
    expect(screen.getByRole("contentinfo").textContent).not.toContain("1 published runs");
  });

  it("FR-018-75 · keeps the statement that nothing is published only when the manifest lists no run, or cannot be read", async () => {
    serve(makeWebIndex([]));
    const { unmount } = await footer();
    await waitFor(() => expect(screen.getByRole("contentinfo").textContent).toContain(NONE));
    unmount();
    serve(null, false);
    await footer();
    await waitFor(() => expect(screen.getByRole("contentinfo").textContent).toContain(NONE));
  });

  it("FR-018-75 · is translated: Spanish count and Spanish none", async () => {
    serve(makeWebIndex([makeArtefact(), makeArtefact({ id: "b", run_id: "20261012T083000Z-c1" })]));
    const { unmount } = await footer("es");
    await waitFor(() =>
      expect(screen.getByRole("contentinfo").textContent).toContain("2 ejecuciones publicadas"),
    );
    unmount();
    serve(makeWebIndex([]));
    await footer("es");
    await waitFor(() =>
      expect(screen.getByRole("contentinfo").textContent).toContain("Aún no se publican datos"),
    );
  });
});
