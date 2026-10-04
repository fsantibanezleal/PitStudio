import { PageStub } from "~/shell/PageStub";
import type { Route } from "./+types/knowledge";

export const meta: Route.MetaFunction = () => [{ title: "Knowledge · PitStudio" }];

export default function KnowledgePage() {
  return <PageStub page="knowledge" />;
}
