/** SHA-256 of a UTF-8 string as lowercase hex (Web Crypto; needs a secure context — https or localhost). */
export async function sha256Hex(text: string): Promise<string> {
  const bytes = new TextEncoder().encode(text);
  const hash = await globalThis.crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(hash), (b) => b.toString(16).padStart(2, "0")).join("");
}

/** True when the passphrase hashes to the build-time digest. Surrounding whitespace is ignored. */
export async function matchesDigest(passphrase: string, digest: string): Promise<boolean> {
  if (!digest) return false;
  return (await sha256Hex(passphrase.trim())) === digest.toLowerCase();
}

/** sessionStorage key, namespaced by repo because every app shares the github.io origin. */
export function accessKey(repo: string): string {
  return `${repo}:access`;
}
