/**
 * The first `tab` parameter of a query string ("?tab=x" or "tab=x") when it is exactly one of `ids`; otherwise the
 * first id. An unknown, empty, markup, control-character or over-long value gives the default and never throws.
 */
export function parseTabParam(search: string, ids: readonly string[]): string {
  const value = new URLSearchParams(search.length > 4000 ? "" : search).get("tab");
  return value !== null && ids.includes(value) ? value : (ids[0] as string);
}
