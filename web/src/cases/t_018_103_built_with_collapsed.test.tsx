// T-018-103 [red] · FR-018-80: the Built with section of a case page is collapsed on load behind a native disclosure, its summary row
// gives the counts of used and planned parts, and its chips stay in the document. Oracle: the owner requirement of 2026-11-23, the FR text.
import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { renderApp } from "~/test-support/render";
import { BuiltWithSection } from "./BuiltWithView";
import type { BuiltGroups, BuiltItem } from "./builtWith";

const item = (id: string, status: "used" | "planned", nvidia = false): BuiltItem => ({
  id,
  name: id.toUpperCase(),
  version: null,
  licence: null,
  href: `/studio/tools/${id}/`,
  nvidia,
  status,
});
const groups: BuiltGroups = {
  omniverse: [item("ovrtx", "used", true), item("openusd", "used", true)],
  frameworks: [item("pytorch", "used"), item("onnx", "planned")],
  methods: [item("m13", "planned")],
  data: [item("egms", "planned")],
};

describe("FR-018-80 Built with is a collapsed disclosure", () => {
  for (const [lang, counts] of [
    ["en", "3 used, 3 planned"],
    ["es", "3 usados, 3 planificados"],
  ] as const) {
    it(`FR-018-80 · ${lang} · collapsed on load, counts in the summary, chips in the document, opens on activation`, async () => {
      await renderApp(<BuiltWithSection groups={groups} />, { lang });
      const details = screen.getByTestId("built-with").querySelector("details") as HTMLDetailsElement;
      expect(details).not.toBeNull();
      expect(details.open).toBe(false);
      const summary = details.querySelector("summary") as HTMLElement;
      expect(summary.textContent).toContain(counts);
      expect(document.querySelectorAll("[data-chip]").length).toBe(6);
      expect(details.querySelectorAll("[data-chip]").length).toBe(6);
      fireEvent.click(summary);
      expect(details.open).toBe(true);
    });
  }

  it("FR-018-80 · the summary row stays short and the open state is not stored", async () => {
    await renderApp(<BuiltWithSection groups={groups} />);
    const summary = screen.getByTestId("built-with").querySelector("summary") as HTMLElement;
    expect((summary.textContent ?? "").length).toBeLessThan(60);
    expect(window.localStorage.length).toBe(0);
    expect(window.sessionStorage.length).toBe(0);
  });
});
