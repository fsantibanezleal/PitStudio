import { ToolPage } from "~/studio/ToolPage";
import type { Route } from "./+types/studio-tool";

export const meta: Route.MetaFunction = ({ params }) => [
  { title: `${params.toolId ?? "Tool"} · Studio · PitStudio` },
];

export default function StudioToolRoute({ params }: Route.ComponentProps) {
  return <ToolPage id={params.toolId} />;
}
