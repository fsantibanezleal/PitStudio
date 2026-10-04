import { PageStub } from "~/shell/PageStub";
import type { Route } from "./+types/results";

export const meta: Route.MetaFunction = () => [{ title: "Results · PitStudio" }];

export default function ResultsPage() {
  return <PageStub page="results" />;
}
