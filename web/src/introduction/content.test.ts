import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { validateExecutive } from "@fasl-work/caos-app-shell";
import { describe, expect, it } from "vitest";
import { EXECUTIVE_SECTIONS, executive } from "./content";

const FILE = resolve(__dirname, "../../content/executive.json");
const PUBLIC = resolve(__dirname, "../../public");
const ILLUSTRATIONS = ["pain", "situation", "proposal"] as const;

function svgOf(name: string): string {
  return readFileSync(resolve(PUBLIC, "executive", `${name}.svg`), "utf8");
}

describe("the executive content file", () => {
  it("is the committed web/content/executive.json, loaded as is", () => {
    expect(executive).toEqual(JSON.parse(readFileSync(FILE, "utf8")));
  });

  it("is valid against the shared shell executive schema (validateExecutive returns no problem)", () => {
    expect(validateExecutive(executive)).toEqual([]);
  });

  it("names the five sections the shell renders as sub-tabs, in order", () => {
    expect(EXECUTIVE_SECTIONS).toEqual(["pain", "context", "situation", "trends", "proposal"]);
  });

  it("carries both languages for the title and the key statement", () => {
    expect(executive.title.en.length).toBeGreaterThan(10);
    expect(executive.title.es.length).toBeGreaterThan(10);
    expect(executive.key_statement.en).not.toEqual(executive.key_statement.es);
  });

  it("lists its sources as https links", () => {
    expect(executive.sources.length).toBeGreaterThan(5);
    for (const source of executive.sources) expect(source.url).toMatch(/^https:\/\//);
  });
});

describe("the three illustrations", () => {
  it("are the files the content names, one per place", () => {
    for (const name of ILLUSTRATIONS) {
      expect(executive.illustrations[name].file).toBe(`executive/${name}.svg`);
    }
  });

  for (const name of ILLUSTRATIONS) {
    describe(name, () => {
      const svg = svgOf(name);

      it("is an inline-ready SVG with a viewBox and no script, image, link or event handler", () => {
        expect(svg).toMatch(/<svg[^>]*viewBox="0 0 960 540"/);
        expect(svg).not.toMatch(/<script|<image|<foreignObject|<a[ >]|href=|\son[a-z]+=/i);
      });

      it("is coloured only with theme tokens, none or currentColor (no hard-coded colour, so dark mode holds)", () => {
        expect(svg).not.toMatch(/#[0-9a-f]{3,8}\b/i);
        expect(svg).not.toMatch(/\b(rgb|rgba|hsl|hsla|oklch|oklab)\(/i);
        const values = [...svg.matchAll(/\b(?:fill|stroke|stop-color)="([^"]*)"/g)].map((m) => m[1] ?? "");
        expect(values.length).toBeGreaterThan(20);
        for (const v of values) expect(v).toMatch(/^(var\(--color-[a-z0-9-]+\)|none|currentColor)$/);
        expect(svg).not.toMatch(/style="[^"]*(#|rgb|hsl)/i);
      });

      it("labels the drawing in English and in Spanish with the same number of labels, no acronym", () => {
        const en = [...svg.matchAll(/<text data-lang="en"[^>]*>([^<]*)<\/text>/g)].map((m) => m[1] ?? "");
        const es = [...svg.matchAll(/<text data-lang="es"[^>]*>([^<]*)<\/text>/g)].map((m) => m[1] ?? "");
        expect(en.length).toBeGreaterThanOrEqual(6);
        expect(es.length).toBe(en.length);
        for (const label of [...en, ...es]) expect(label).not.toMatch(/\b[A-Z]{3,}\b/);
        expect(svg).not.toMatch(/font-family/);
      });

      it("is not a chart: no axes, ticks or data attribute of a chart", () => {
        expect(svg).not.toMatch(/data-chart|<polyline|axis|tick/i);
      });

      it("prefixes its ids so the three drawings do not collide", () => {
        const ids = [...svg.matchAll(/\sid="([^"]+)"/g)].map((m) => m[1] ?? "");
        for (const id of ids) expect(id.startsWith(`${name}-`)).toBe(true);
      });
    });
  }

  it("share the same setting in the pain and the proposal (same pit, same road, same plant)", () => {
    const scene = (name: string) => svgOf(name).match(/<path d="M0 150 L60 150[^>]*>/)?.[0];
    expect(scene("pain")).toBeDefined();
    expect(scene("pain")).toBe(scene("proposal"));
  });
});
