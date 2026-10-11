import { CasePage } from "~/cases/CasePage";
import type { Route } from "./+types/case";

export const meta: Route.MetaFunction = ({ params }) => [{ title: `${params.id ?? "Case"} · PitStudio` }];

export default function CaseRoute({ params }: Route.ComponentProps) {
  return <CasePage id={params.id} />;
}
