import { PageStub } from "~/shell/PageStub";
import type { Route } from "./+types/theory";

export const meta: Route.MetaFunction = () => [{ title: "Theory · PitStudio" }];

export default function TheoryPage() {
  return <PageStub page="theory" />;
}
