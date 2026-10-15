/** Query parameters the Introduction itself uses: the open view (`technical`) and the open executive sub-tab. */
const OWN_PARAMS = new Set(["section", "view"]);

/** The hash of a source note inside the executive view. */
const SOURCE_NOTE = /^#exec-note-\d+$/;

/**
 * The root is the Introduction. An old link to the App (the root with a case, tier, language or renderer query, or a hash
 * such as `/?case=B2`) is forwarded to `/app` with both kept; the bare root and the Introduction's own parameters stay.
 * Returns the target path (relative to the router basename) or null when the root should open the Introduction.
 */
export function legacyAppTarget(url: URL): string | null {
  const foreignQuery = [...url.searchParams.keys()].some((key) => !OWN_PARAMS.has(key));
  const foreignHash = url.hash !== "" && !SOURCE_NOTE.test(url.hash);
  return foreignQuery || foreignHash ? `/app${url.search}${url.hash}` : null;
}
