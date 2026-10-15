import { StudioPage } from "~/studio/StudioPage";
import type { Route } from "./+types/studio";

export const meta: Route.MetaFunction = () => [{ title: "Studio · PitStudio" }];

export default function StudioRoute() {
  return <StudioPage />;
}
