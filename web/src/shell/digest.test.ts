import { describe, expect, it } from "vitest";
import { accessKey, matchesDigest, sha256Hex } from "./digest";

// FIPS 180-2 test vectors.
const ABC = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad";
const EMPTY = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855";

describe("sha256Hex", () => {
  it("matches the published test vectors", async () => {
    expect(await sha256Hex("abc")).toBe(ABC);
    expect(await sha256Hex("")).toBe(EMPTY);
  });

  it("hashes non-ASCII text as UTF-8", async () => {
    expect(await sha256Hex("rajo abierto ñ")).toMatch(/^[0-9a-f]{64}$/);
    expect(await sha256Hex("ñ")).not.toBe(await sha256Hex("n"));
  });
});

describe("matchesDigest", () => {
  it("FR-000-04 · accepts the right passphrase, ignoring surrounding whitespace and digest case", async () => {
    expect(await matchesDigest("abc", ABC)).toBe(true);
    expect(await matchesDigest("  abc\n", ABC.toUpperCase())).toBe(true);
  });

  it("FR-000-04 · rejects wrong passphrases and never matches an empty digest", async () => {
    expect(await matchesDigest("abd", ABC)).toBe(false);
    expect(await matchesDigest("", EMPTY.slice(0, 63))).toBe(false);
    expect(await matchesDigest("", "")).toBe(false);
  });

  it("namespaces the session key by repo", () => {
    expect(accessKey("PitStudio")).toBe("PitStudio:access");
  });
});
