import type { Config } from "@react-router/dev/config";

// GitHub Pages serves the site under /<repo>/. CI passes it as BASE_PATH (from actions/configure-pages);
// local builds default to "/".
const basename = process.env.BASE_PATH ?? "/";

export default {
  appDirectory: "src",
  ssr: false,
  // Every static route becomes real HTML, so deep links return 200 on Pages. The splat route (and later dynamic
  // routes not listed here) is served by 404.html, the SPA fallback.
  prerender: ({ getStaticPaths }) => getStaticPaths(),
  basename,
} satisfies Config;
