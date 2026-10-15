// Public documentation pages are read on the repository's default branch.
export const DOCS_BASE = "https://github.com/fsantibanezleal/PitStudio/blob/main/";

export function docsHref(page: string): string {
  return `${DOCS_BASE}${page.split("/").map(encodeURIComponent).join("/")}`;
}
