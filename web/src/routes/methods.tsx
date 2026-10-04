import { PageStub } from "~/shell/PageStub";
import type { Route } from "./+types/methods";

export const meta: Route.MetaFunction = () => [{ title: "Methods · PitStudio" }];

export default function MethodsPage() {
  return <PageStub page="methods" />;
}
