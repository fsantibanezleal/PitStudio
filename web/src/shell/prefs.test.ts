import { describe, expect, it } from "vitest";
import { nextThemePref, resolveLanguage, resolveTheme } from "./prefs";

describe("resolveLanguage", () => {
  it("FR-000-03 · prefers ?lang= over the stored choice", () => {
    expect(resolveLanguage("?lang=es", "en")).toBe("es");
    expect(resolveLanguage("?lang=en", "es")).toBe("en");
  });

  it("FR-000-03 · falls back to the stored choice when ?lang= is missing or invalid", () => {
    expect(resolveLanguage("", "es")).toBe("es");
    expect(resolveLanguage("?lang=fr", "es")).toBe("es");
    expect(resolveLanguage("?lang=", "es")).toBe("es");
  });

  it("FR-000-03 · defaults to English and ignores invalid stored values", () => {
    expect(resolveLanguage("", null)).toBe("en");
    expect(resolveLanguage("?lang=ES", "de")).toBe("en");
    expect(resolveLanguage("?x=1", "<script>")).toBe("en");
  });
});

describe("theme preference", () => {
  it("resolves system from the media query and keeps explicit choices", () => {
    expect(resolveTheme("system", true)).toBe("dark");
    expect(resolveTheme("system", false)).toBe("light");
    expect(resolveTheme("light", true)).toBe("light");
    expect(resolveTheme("dark", false)).toBe("dark");
  });

  it("cycles system → light → dark → system", () => {
    expect(nextThemePref("system")).toBe("light");
    expect(nextThemePref("light")).toBe("dark");
    expect(nextThemePref("dark")).toBe("system");
  });
});
