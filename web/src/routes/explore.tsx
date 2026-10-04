import { PageStub } from "~/shell/PageStub";
import type { Route } from "./+types/explore";

export const meta: Route.MetaFunction = () => [{ title: "PitStudio — open-pit mining simulation studio" }];

export default function ExplorePage() {
  return <PageStub page="explore" />;
}
