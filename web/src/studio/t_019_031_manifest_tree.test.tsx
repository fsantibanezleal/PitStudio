// T-019-031 [red] · FR-019-23: the manifest viewer renders the run card as a collapsible tree operable with the WAI-ARIA tree keys, shows each SHA-256 in full with a copy control and renders every string as text
// (the 500 ms bound for a 200 KB card is the E2E half: web/e2e/t_019_031_run_page.spec.ts).
//
// Expected API: `~/studio/ManifestTree` (web/src/studio/ManifestTree.tsx): named export ManifestTree({ value: unknown }) rendering `ul[role="tree"][data-testid="manifest-tree"][aria-label]` whose
//   items are `li[role="treeitem"][data-path="<JSON pointer>"][aria-level][aria-setsize][aria-posinset]`; an object or array with entries has `aria-expanded` ("false" until opened) and, while open, a
//   `ul[role="group"]` of its children (collapsed children are not rendered); exactly one item has tabindex 0 (roving tab index), the others -1, and the focused item is the `li` itself;
//   a leaf shows its key and `[data-testid="leaf-value"]`: strings through `~/studio/SafeText` (text, cut at 200 characters with an expander), numbers, booleans and null as their JSON text, an empty object or array as
//   `{}` or `[]`; a string that is a SHA-256 (64 lower-case hex characters) is shown in full with `button[data-testid="copy-sha"]` (accessible name "Copy SHA-256") that writes it to the clipboard.
//   Keys of the WAI-ARIA authoring practices tree view: Down / Up move to the next / previous VISIBLE item; Right opens a closed parent, moves to the first child of an open one; Left closes an open parent, else moves to the parent;
//   Home / End first / last visible item; Enter toggles a parent; `*` opens all siblings of the focused item; typing characters moves to the next visible item whose key starts with them.
// Oracles: the WAI-ARIA 1.2 tree pattern keys; the valid run card of DC-001-01 (top-level keys in order: kind, schema_version, run_id, recipe, git_sha, git_dirty, runner_version, created, profile, seed, published, launcher,
// gpu, stages, artefacts, notes; stages: 3 entries; recipe.sha256 = 64 times "e").
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createElement } from "react";
import { describe, expect, it } from "vitest";
import { ManifestTree } from "~/studio/ManifestTree";
import { renderApp } from "~/test-support/render";
import { loadRunCardExample } from "~/test-support/studio-fixtures";

const TOP = [
  "kind",
  "schema_version",
  "run_id",
  "recipe",
  "git_sha",
  "git_dirty",
  "runner_version",
  "created",
  "profile",
  "seed",
  "published",
  "launcher",
  "gpu",
  "stages",
  "artefacts",
  "notes",
];
const card = () => loadRunCardExample() as unknown;
const items = () => Array.from(document.querySelectorAll<HTMLElement>('[role="treeitem"]'));
const item = (path: string) =>
  document.querySelector<HTMLElement>(`[role="treeitem"][data-path="${path}"]`) as HTMLElement;
const focusedPath = () => (document.activeElement as HTMLElement | null)?.getAttribute("data-path");
const render = (value: unknown = card()) => renderApp(createElement(ManifestTree, { value }));
const visiblePaths = () =>
  items()
    .filter((i) => !i.parentElement?.closest('[role="treeitem"][aria-expanded="false"]'))
    .map((i) => i.getAttribute("data-path"));
const startAt = async (user: ReturnType<typeof userEvent.setup>, path: string) => {
  await user.tab();
  const target = item(path);
  target.focus();
  expect(document.activeElement).toBe(target);
};

describe("structure (FR-019-23)", () => {
  it("FR-019-23 · is a tree with one top-level item per key of the run card, in card order, with level, size and position", async () => {
    await render();
    const tree = screen.getByTestId("manifest-tree");
    expect(tree.getAttribute("role")).toBe("tree");
    expect((tree.getAttribute("aria-label") ?? "").length).toBeGreaterThan(0);
    const top = items().filter((i) => i.getAttribute("aria-level") === "1");
    expect(top.map((i) => i.getAttribute("data-path"))).toEqual(TOP.map((k) => `/${k}`));
    top.forEach((i, n) => {
      expect(i.getAttribute("aria-setsize")).toBe(String(TOP.length));
      expect(i.getAttribute("aria-posinset")).toBe(String(n + 1));
    });
  });

  it("FR-019-23 · objects and arrays are collapsed at first and their children are not rendered; scalars have no aria-expanded", async () => {
    await render();
    for (const key of ["recipe", "gpu", "stages", "artefacts", "notes"]) {
      expect(item(`/${key}`).getAttribute("aria-expanded"), key).toBe("false");
      expect(item(`/${key}`).querySelector('[role="group"]'), key).toBeNull();
    }
    for (const key of ["kind", "run_id", "seed", "published", "git_dirty"])
      expect(item(`/${key}`).hasAttribute("aria-expanded"), key).toBe(false);
    expect(items()).toHaveLength(TOP.length);
  });

  it("FR-019-23 · a roving tab index: exactly one item is a tab stop and Tab reaches it", async () => {
    await render();
    expect(items().filter((i) => i.getAttribute("tabindex") === "0")).toHaveLength(1);
    expect(items().filter((i) => i.getAttribute("tabindex") === "-1")).toHaveLength(TOP.length - 1);
    const user = userEvent.setup();
    await user.tab();
    expect(document.activeElement?.getAttribute("role")).toBe("treeitem");
    expect(document.activeElement?.getAttribute("data-path")).toBe("/kind");
  });

  it("FR-019-23 · leaves show scalars as their JSON text: strings, numbers, booleans, null, empty containers", async () => {
    await render({ s: "text", n: 42, f: 1.5, t: true, z: null, o: {}, a: [] });
    const leaf = (k: string) => item(`/${k}`).querySelector('[data-testid="leaf-value"]')?.textContent;
    expect(leaf("s")).toBe("text");
    expect(leaf("n")).toBe("42");
    expect(leaf("f")).toBe("1.5");
    expect(leaf("t")).toBe("true");
    expect(leaf("z")).toBe("null");
    expect(leaf("o")).toBe("{}");
    expect(leaf("a")).toBe("[]");
    expect(item("/o").hasAttribute("aria-expanded")).toBe(false);
  });
});

describe("keys of the tree pattern (FR-019-23)", () => {
  it("FR-019-23 · Right opens a closed parent and keeps focus; Right again moves to its first child", async () => {
    await render();
    const user = userEvent.setup();
    await startAt(user, "/stages");
    await user.keyboard("{ArrowRight}");
    expect(item("/stages").getAttribute("aria-expanded")).toBe("true");
    expect(focusedPath()).toBe("/stages");
    const children = Array.from(item("/stages").querySelectorAll('[role="group"] > [role="treeitem"]'));
    expect(children.map((c) => c.getAttribute("data-path"))).toEqual(["/stages/0", "/stages/1", "/stages/2"]);
    for (const c of children) {
      expect(c.getAttribute("aria-level")).toBe("2");
      expect(c.getAttribute("aria-setsize")).toBe("3");
    }
    await user.keyboard("{ArrowRight}");
    expect(focusedPath()).toBe("/stages/0");
  });

  it("FR-019-23 · Left closes an open parent, and from a child or a closed parent moves to the parent; at the top level it does nothing", async () => {
    await render();
    const user = userEvent.setup();
    await startAt(user, "/stages");
    await user.keyboard("{ArrowRight}{ArrowRight}{ArrowLeft}");
    expect(focusedPath()).toBe("/stages");
    expect(item("/stages").getAttribute("aria-expanded")).toBe("true");
    await user.keyboard("{ArrowLeft}");
    expect(item("/stages").getAttribute("aria-expanded")).toBe("false");
    await user.keyboard("{ArrowLeft}");
    expect(focusedPath()).toBe("/stages");
  });

  it("FR-019-23 · Down and Up move over the visible items only: closed subtrees are skipped, open ones are entered", async () => {
    await render();
    const user = userEvent.setup();
    await startAt(user, "/gpu");
    await user.keyboard("{ArrowDown}");
    expect(focusedPath()).toBe("/stages");
    await user.keyboard("{ArrowDown}");
    expect(focusedPath()).toBe("/artefacts");
    await user.keyboard("{ArrowUp}{ArrowRight}{ArrowDown}");
    expect(focusedPath()).toBe("/stages/0");
    await user.keyboard("{ArrowUp}");
    expect(focusedPath()).toBe("/stages");
    expect(visiblePaths()).toContain("/stages/2");
  });

  it("FR-019-23 · Up on the first item and Down on the last visible item stay where they are", async () => {
    await render();
    const user = userEvent.setup();
    await startAt(user, "/kind");
    await user.keyboard("{ArrowUp}");
    expect(focusedPath()).toBe("/kind");
    await user.keyboard("{End}{ArrowDown}");
    expect(focusedPath()).toBe("/notes");
  });

  it("FR-019-23 · Home goes to the first item, End to the last visible one (a child of an open last parent)", async () => {
    await render();
    const user = userEvent.setup();
    await startAt(user, "/run_id");
    await user.keyboard("{End}");
    expect(focusedPath()).toBe("/notes");
    await user.keyboard("{ArrowRight}{End}");
    expect(focusedPath()).toBe("/notes/0");
    await user.keyboard("{Home}");
    expect(focusedPath()).toBe("/kind");
  });

  it("FR-019-23 · Enter toggles a parent and does nothing to a leaf", async () => {
    await render();
    const user = userEvent.setup();
    await startAt(user, "/recipe");
    await user.keyboard("{Enter}");
    expect(item("/recipe").getAttribute("aria-expanded")).toBe("true");
    await user.keyboard("{Enter}");
    expect(item("/recipe").getAttribute("aria-expanded")).toBe("false");
    await startAt(user, "/kind");
    await user.keyboard("{Enter}");
    expect(item("/kind").hasAttribute("aria-expanded")).toBe(false);
  });

  it("FR-019-23 · * opens every sibling of the focused item at its level", async () => {
    await render();
    const user = userEvent.setup();
    await startAt(user, "/recipe");
    await user.keyboard("*");
    for (const key of ["recipe", "gpu", "stages", "artefacts", "notes"])
      expect(item(`/${key}`).getAttribute("aria-expanded"), key).toBe("true");
  });

  it("FR-019-23 · typing characters moves to the next visible item whose key starts with them", async () => {
    await render();
    const user = userEvent.setup();
    await startAt(user, "/kind");
    await user.keyboard("r");
    expect(focusedPath()).toBe("/run_id");
  });

  it("FR-019-23 · several characters typed together select by their common prefix", async () => {
    await render();
    const user = userEvent.setup();
    await startAt(user, "/kind");
    await user.keyboard("re");
    expect(focusedPath()).toBe("/recipe");
  });

  it("FR-019-23 · moving the focus moves the tab stop with it", async () => {
    await render();
    const user = userEvent.setup();
    await startAt(user, "/kind");
    await user.keyboard("{ArrowDown}{ArrowDown}");
    expect(
      items()
        .filter((i) => i.getAttribute("tabindex") === "0")
        .map((i) => i.getAttribute("data-path")),
    ).toEqual(["/run_id"]);
  });
});

describe("digests and text (FR-019-23)", () => {
  it("FR-019-23 · a SHA-256 is shown in full, never truncated, with a copy control that puts the whole digest on the clipboard", async () => {
    await render();
    const user = userEvent.setup();
    await startAt(user, "/recipe");
    await user.keyboard("{ArrowRight}");
    const leaf = item("/recipe/sha256");
    expect(leaf.querySelector('[data-testid="leaf-value"]')?.textContent).toBe("e".repeat(64));
    const copy = within(leaf).getByTestId("copy-sha");
    expect(copy.getAttribute("aria-label") ?? copy.textContent).toContain("Copy SHA-256");
    await user.click(copy);
    expect(await navigator.clipboard.readText()).toBe("e".repeat(64));
  });

  it("FR-019-23 · only 64-character lower-case hex strings get the copy control: a 63-character, an upper-case and a 65-character string do not", async () => {
    await render({ ok: "a".repeat(64), short: "a".repeat(63), upper: "A".repeat(64), long: "a".repeat(65) });
    expect(item("/ok").querySelector('[data-testid="copy-sha"]')).not.toBeNull();
    for (const k of ["short", "upper", "long"])
      expect(item(`/${k}`).querySelector('[data-testid="copy-sha"]'), k).toBeNull();
  });

  it("FR-019-23 · strings are text: markup in a value or in a key creates no element", async () => {
    const { container } = await render({
      "<b>key</b>": "<img src=x onerror=alert(1)>",
      notes: ["<script>alert(1)</script>"],
    });
    const user = userEvent.setup();
    await startAt(user, "/notes");
    await user.keyboard("{ArrowRight}");
    expect(container.querySelector("img, script, b")).toBeNull();
    expect(container.textContent).toContain("<img src=x onerror=alert(1)>");
    expect(container.textContent).toContain("<script>alert(1)</script>");
  });

  it("FR-019-23 · a long string is cut at 200 characters with an expander (FR-019-40)", async () => {
    await render({ log: "L".repeat(5000) });
    expect(within(item("/log")).getByTestId("expand")).toBeTruthy();
    expect((item("/log").textContent ?? "").length).toBeLessThan(400);
  });

  it("FR-019-23 · keys that need escaping in a JSON pointer keep a valid, unambiguous path (~0 for ~ and ~1 for /)", async () => {
    await render({ "a/b": 1, "c~d": 2 });
    expect(item("/a~1b")).not.toBeNull();
    expect(item("/c~0d")).not.toBeNull();
  });
});

describe("size (FR-019-23)", () => {
  it("FR-019-23 · a card with 5,000 artefacts renders only its top level at first: the work is proportional to what is open", async () => {
    const big = {
      ...(card() as Record<string, unknown>),
      artefacts: Array.from({ length: 5000 }, (_, i) => ({
        id: `a-${i}`,
        sha256: "a".repeat(64),
        nested: { x: i },
      })),
    };
    await render(big);
    expect(items()).toHaveLength(TOP.length);
    expect(document.querySelectorAll("*").length).toBeLessThan(1500);
  });

  it("FR-019-23 · an empty object and a deeply nested value (depth 40) do not crash the viewer", async () => {
    let deep: unknown = "leaf";
    for (let i = 0; i < 40; i++) deep = { n: deep };
    const { container } = await render({ deep });
    expect(container.querySelector('[role="tree"]')).not.toBeNull();
    await render({});
    expect(document.querySelectorAll('[role="tree"]').length).toBeGreaterThan(0);
  });
});
