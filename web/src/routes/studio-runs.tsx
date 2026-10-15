import { RunsPage } from "~/studio/RunsPage";
import type { Route } from "./+types/studio-runs";

export const meta: Route.MetaFunction = () => [{ title: "Published runs · Studio · PitStudio" }];

export default function StudioRunsRoute() {
  return <RunsPage />;
}
