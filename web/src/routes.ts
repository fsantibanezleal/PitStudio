import { index, type RouteConfig, route } from "@react-router/dev/routes";

export default [
  index("routes/explore.tsx"),
  route("cases", "routes/cases.tsx"),
  route("cases/:id", "routes/case.tsx"),
  route("studio", "routes/studio.tsx"),
  route("studio/tools/:toolId", "routes/studio-tool.tsx"),
  route("studio/runs", "routes/studio-runs.tsx"),
  route("studio/runs/:runId", "routes/studio-run.tsx"),
  route("studio/gpu", "routes/studio-gpu.tsx"),
  route("theory", "routes/theory.tsx"),
  route("methods", "routes/methods.tsx"),
  route("methods/:slug", "routes/method.tsx"),
  route("results", "routes/results.tsx"),
  route("knowledge", "routes/knowledge.tsx"),
  // Unlisted sandbox of the interactive chart (driven by the browser tests, not linked from the navigation).
  route("charts", "routes/charts.tsx"),
  route("*", "routes/not-found.tsx"),
] satisfies RouteConfig;
