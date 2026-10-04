import { index, type RouteConfig, route } from "@react-router/dev/routes";

export default [
  index("routes/explore.tsx"),
  route("cases", "routes/cases.tsx"),
  route("studio", "routes/studio.tsx"),
  route("theory", "routes/theory.tsx"),
  route("methods", "routes/methods.tsx"),
  route("results", "routes/results.tsx"),
  route("knowledge", "routes/knowledge.tsx"),
  route("*", "routes/not-found.tsx"),
] satisfies RouteConfig;
