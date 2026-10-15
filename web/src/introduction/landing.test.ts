import { describe, expect, it } from "vitest";
import { legacyAppTarget } from "./landing";

const at = (path: string) => new URL(path, "https://example.test");

describe("the root forwards old App links and keeps the Introduction for a plain visit", () => {
  it("opens the Introduction for the bare root and for the view own parameters", () => {
    expect(legacyAppTarget(at("/"))).toBeNull();
    expect(legacyAppTarget(at("/?section=trends"))).toBeNull();
    expect(legacyAppTarget(at("/?view=technical&section=pain"))).toBeNull();
    expect(legacyAppTarget(at("/#exec-note-3"))).toBeNull();
  });

  it("forwards the root with a case, tier, language or renderer query to /app, query kept", () => {
    expect(legacyAppTarget(at("/?case=B2"))).toBe("/app?case=B2");
    expect(legacyAppTarget(at("/?lang=es&tier=t0"))).toBe("/app?lang=es&tier=t0");
    expect(legacyAppTarget(at("/?case=A1&renderer=webgl#map"))).toBe("/app?case=A1&renderer=webgl#map");
  });

  it("forwards a root with a hash that is not a source note, hash kept", () => {
    expect(legacyAppTarget(at("/#layers"))).toBe("/app#layers");
  });
});
