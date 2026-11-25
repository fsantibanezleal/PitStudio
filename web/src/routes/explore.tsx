import { ExploreView } from "~/cases/ExploreView";
import type { Route } from "./+types/explore";

export const meta: Route.MetaFunction = () => [{ title: "PitStudio — open-pit mining simulation studio" }];

export default function ExplorePage() {
  return <ExploreView />;
}
