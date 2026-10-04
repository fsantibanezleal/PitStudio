import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

export interface BuildInfo {
  version: string;
  gitSha: string;
  buildDate: string;
}

function gitSha(): string {
  if (process.env.GITHUB_SHA) return process.env.GITHUB_SHA.slice(0, 7);
  try {
    return execFileSync("git", ["rev-parse", "--short=7", "HEAD"], {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
    }).trim();
  } catch {
    return "unknown";
  }
}

/** SHA-256 hex of the demo passphrase (trimmed, as the gate compares it); "" when there is none. */
export function accessDigest(passphrase: string | undefined): string {
  const phrase = passphrase?.trim();
  return phrase ? createHash("sha256").update(phrase, "utf8").digest("hex") : "";
}

/** Version from the repo's VERSION file, short commit SHA, and build date (SOURCE_DATE_EPOCH when set). */
export function buildInfo(): BuildInfo {
  const version = readFileSync(fileURLToPath(new URL("../VERSION", import.meta.url)), "utf8").trim();
  const epoch = process.env.SOURCE_DATE_EPOCH;
  const date = epoch ? new Date(Number(epoch) * 1000) : new Date();
  return { version, gitSha: gitSha(), buildDate: date.toISOString().slice(0, 10) };
}
