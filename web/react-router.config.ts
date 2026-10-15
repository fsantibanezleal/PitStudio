import { readFileSync } from "node:fs";
import type { Config } from "@react-router/dev/config";
import { CASE_IDS } from "./src/cases/types";

// GitHub Pages serves the site under /<repo>/. CI passes it as BASE_PATH (from actions/configure-pages);
// local builds default to "/".
const basename = process.env.BASE_PATH ?? "/";

// The studio pages (spec 019): one page per registry tool and per published run, enumerated from the data that
// `scripts/build-studio-index.mjs` wrote before this build. Without that file (a fresh checkout) there is none to enumerate.
function studioPaths(): string[] {
  try {
    const data = JSON.parse(
      readFileSync(new URL("./src/studio/generated/studio-data.json", import.meta.url), "utf8"),
    ) as {
      tools: Array<{ id: string }>;
      run_ids?: string[];
    };
    return [
      ...data.tools.map((t) => `/studio/tools/${t.id}`),
      ...(data.run_ids ?? []).map((id) => `/studio/runs/${id}`),
    ];
  } catch {
    return [];
  }
}

export default {
  appDirectory: "src",
  ssr: false,
  // Every static route becomes real HTML, so deep links return 200 on Pages, and so does each of the 12 canonical case
  // pages (`/cases/<ID>/`, upper case only). The splat route and any other id are served by 404.html, the SPA fallback,
  // which renders the app's not-found page.
  prerender: ({ getStaticPaths }) => [
    ...getStaticPaths(),
    ...CASE_IDS.map((id) => `/cases/${id}`),
    ...studioPaths(),
  ],
  basename,
} satisfies Config;
