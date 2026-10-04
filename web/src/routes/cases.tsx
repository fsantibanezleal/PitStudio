import { PageStub } from "~/shell/PageStub";
import type { Route } from "./+types/cases";

export const meta: Route.MetaFunction = () => [{ title: "Cases · PitStudio" }];

export default function CasesPage() {
  return <PageStub page="cases" />;
}
