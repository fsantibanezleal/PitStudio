import { CosmosToolCard } from "~/features/reason/ReasonPanel";
import { PageStub } from "~/shell/PageStub";
import type { Route } from "./+types/studio";

export const meta: Route.MetaFunction = () => [{ title: "Studio · PitStudio" }];

export default function StudioPage() {
  return (
    <>
      <PageStub page="studio" />
      <CosmosToolCard />
    </>
  );
}
