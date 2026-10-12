import type { Config } from "@react-router/dev/config";
import { CASE_IDS } from "./src/cases/types";

// GitHub Pages serves the site under /<repo>/. CI passes it as BASE_PATH (from actions/configure-pages);
// local builds default to "/".
const basename = process.env.BASE_PATH ?? "/";

export default {
  appDirectory: "src",
  ssr: false,
  // Every static route becomes real HTML, so deep links return 200 on Pages, and so does each of the 12 canonical case
  // pages (`/cases/<ID>/`, upper case only). The splat route and any other id are served by 404.html, the SPA fallback,
  // which renders the app's not-found page.
  prerender: ({ getStaticPaths }) => [...getStaticPaths(), ...CASE_IDS.map((id) => `/cases/${id}`)],
  basename,
} satisfies Config;
