// T-018-021 [red] · FR-018-02 (unit half): the case rail of the Explore route.
//
// Expected component API (to be created by the green commit; the test fixes it):
//   module  ~/cases/CaseRail        export  function CaseRail(props: {
//                                      registry: CaseRegistry;            // DC-018-01 document (specs/018-web-cases/contracts/cases.schema.json)
//                                      selected?: string | null;          // canonical case id, or anything else = nothing selected
//                                      onSelect?: (id: string) => void;   // called when the visitor selects an entry
//                                    })
//   Active language = the i18n language of the shell (`useTranslation().i18n.resolvedLanguage`), "en" or "es".
//   DOM contract:
//     - five `role="group"` elements in the order A, B, C, D, E; the accessible name of each contains the category
//       letter (as a whole word) and `registry.categories[letter].title[lang]`;
//     - inside group X one `li[data-case-id="<id>"]` per case of category X, in canonical order (A1 A2 A3 | B1 B2 | ...),
//       whatever the key order of the registry objects, and nothing for ids outside the 12 canonical ids;
//     - each `li` holds exactly one `button` (selects; `aria-pressed="true"` iff the entry is the selected one; its accessible
//       name contains the case id and `title[lang]`) and exactly one `a` whose href is `/cases/<id>/` (FR-018-02);
//     - titles are rendered as text, never as markup.
// Oracles: FR-018-02 (12 entries, 5 groups, order); titles and category names from the valid registry example of DC-018-01.
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { CaseRail } from "~/cases/CaseRail";
import {
  CASE_IDS,
  type CaseRegistryJson,
  GROUPS,
  loadCaseRegistry,
  withReversedKeys,
} from "~/test-support/fixtures";
import { props, renderApp } from "~/test-support/render";

const registry = loadCaseRegistry();

function items(container: HTMLElement): HTMLElement[] {
  return [...container.querySelectorAll<HTMLElement>("li[data-case-id]")];
}

describe("case rail (FR-018-02)", () => {
  it("FR-018-02 · shows exactly 12 entries in 5 labelled groups A, B, C, D, E in canonical order", async () => {
    const { container } = await renderApp(<CaseRail registry={props(registry)} />);
    expect(items(container).map((li) => li.dataset.caseId)).toEqual([...CASE_IDS]);
    const groups = screen.getAllByRole("group");
    expect(groups).toHaveLength(5);
    GROUPS.forEach(([letter, ids], i) => {
      const title = registry.categories[letter]?.title.en ?? "";
      const named = screen.getByRole("group", {
        name: new RegExp(`\\b${letter}\\b.*${title}|${title}.*\\b${letter}\\b`),
      });
      expect(named).toBe(groups[i]);
      const group = groups[i] as HTMLElement;
      expect(items(group).map((li) => li.dataset.caseId)).toEqual([...ids]);
    });
  });

  it("FR-018-02 · the order does not depend on the key order of the registry", async () => {
    const { container } = await renderApp(<CaseRail registry={props(withReversedKeys(registry))} />);
    expect(items(container).map((li) => li.dataset.caseId)).toEqual([...CASE_IDS]);
    const groups = screen.getAllByRole("group");
    expect(groups.map((g) => items(g).length)).toEqual([3, 2, 3, 2, 2]);
  });

  it("FR-018-02 · each entry shows its registry title and links to /cases/<id>/", async () => {
    const { container } = await renderApp(<CaseRail registry={props(registry)} />);
    expect(items(container)).toHaveLength(12);
    for (const li of items(container)) {
      const id = li.dataset.caseId as string;
      const title = registry.cases[id]?.title.en as string;
      expect(li.textContent).toContain(title);
      const links = within(li).getAllByRole("link");
      expect(links).toHaveLength(1);
      expect(links[0]?.getAttribute("href")).toBe(`/cases/${id}/`);
      const buttons = within(li).getAllByRole("button");
      expect(buttons).toHaveLength(1);
      expect(buttons[0]?.textContent).toContain(id);
      expect(buttons[0]?.textContent).toContain(title);
    }
  });

  it("FR-018-02 · titles and group labels follow the active language (ES)", async () => {
    const { container } = await renderApp(<CaseRail registry={props(registry)} />, { lang: "es" });
    expect(items(container)).toHaveLength(12);
    for (const li of items(container)) {
      const id = li.dataset.caseId as string;
      expect(li.textContent).toContain(registry.cases[id]?.title.es as string);
    }
    for (const [letter] of GROUPS) {
      const es = registry.categories[letter]?.title.es as string;
      expect(screen.getByRole("group", { name: new RegExp(es) })).toBeTruthy();
    }
  });
});

describe("case rail selection (FR-018-03, component half)", () => {
  it("FR-018-02 · marks exactly the selected entry with aria-pressed and the rest as not pressed", async () => {
    await renderApp(<CaseRail registry={props(registry)} selected="C1" />);
    const pressed = screen.getAllByRole("button", { pressed: true });
    expect(pressed).toHaveLength(1);
    expect(pressed[0]?.closest("li")?.dataset.caseId).toBe("C1");
    expect(screen.getAllByRole("button", { pressed: false })).toHaveLength(11);
  });

  it("FR-018-02 · selecting an entry by click or by keyboard calls onSelect with its id and does not navigate", async () => {
    const onSelect = vi.fn();
    const user = userEvent.setup();
    const { container } = await renderApp(<CaseRail registry={props(registry)} onSelect={onSelect} />);
    const b2 = items(container).find((li) => li.dataset.caseId === "B2") as HTMLElement;
    await user.click(within(b2).getByRole("button"));
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect).toHaveBeenLastCalledWith("B2");
    const e1 = items(container).find((li) => li.dataset.caseId === "E1") as HTMLElement;
    within(e1).getByRole("button").focus();
    await user.keyboard("{Enter}");
    expect(onSelect).toHaveBeenLastCalledWith("E1");
    await user.keyboard(" ");
    expect(onSelect).toHaveBeenCalledTimes(3);
  });
});

describe("case rail hostile inputs (FR-018-02)", () => {
  it("FR-018-02 · renders a title with markup as plain text, never as an element", async () => {
    const hostile = structuredClone(registry) as CaseRegistryJson;
    const evil = '<img src=x onerror="alert(1)"><script>alert(2)</script>';
    (hostile.cases.A1 as { title: { en: string } }).title.en = evil;
    const { container } = await renderApp(<CaseRail registry={props(hostile)} />);
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("script")).toBeNull();
    expect(container.textContent).toContain(evil);
  });

  it("FR-018-02 · ignores case ids outside the 12 canonical ids and renders no link for them", async () => {
    const hostile = structuredClone(registry) as CaseRegistryJson;
    for (const key of ["X9", "a1", "../etc/passwd", "A1/../B1", "A4"]) {
      hostile.cases[key] = structuredClone(registry.cases.A1) as never;
    }
    const { container } = await renderApp(<CaseRail registry={props(hostile)} />);
    expect(items(container).map((li) => li.dataset.caseId)).toEqual([...CASE_IDS]);
    const hrefs = within(container)
      .getAllByRole("link")
      .map((a) => a.getAttribute("href"));
    expect(hrefs).toEqual(CASE_IDS.map((id) => `/cases/${id}/`));
  });

  it("FR-018-02 · an unknown, lower-case, empty or hostile `selected` value selects nothing and does not throw", async () => {
    for (const selected of ["a1", "X9", "", "../B1", "<b>", null, undefined]) {
      const { unmount } = await renderApp(<CaseRail registry={props(registry)} selected={selected} />);
      expect(screen.getAllByRole("button", { pressed: false })).toHaveLength(12);
      expect(screen.queryAllByRole("button", { pressed: true })).toHaveLength(0);
      unmount();
    }
  });
});
