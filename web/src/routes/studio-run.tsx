import { RunPage } from "~/studio/RunPage";
import type { Route } from "./+types/studio-run";

export const meta: Route.MetaFunction = ({ params }) => [
  { title: `${params.runId ?? "Run"} · Studio · PitStudio` },
];

export default function StudioRunRoute({ params }: Route.ComponentProps) {
  return <RunPage id={params.runId} />;
}
