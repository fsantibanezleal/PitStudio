import { useEffect } from "react";
import { useLoaderData, useNavigate } from "react-router";
import { executive } from "~/introduction/content";
import { IntroductionView } from "~/introduction/IntroductionView";
import { legacyAppTarget } from "~/introduction/landing";
import type { Route } from "./+types/introduction";

export const meta: Route.MetaFunction = () => [
  { title: "Introduction · PitStudio" },
  {
    name: "description",
    content:
      "The industry problem behind PitStudio, framed for decision makers: the pain, the context, the current situation, the trends and the proposal.",
  },
];

/**
 * The executive content is read at build time and travels as page data, not as script: the start page is the
 * Introduction and its scripts stay within the gzip budget (NFR-018-02).
 */
export function loader() {
  return executive;
}

export default function IntroductionPage() {
  const data = useLoaderData<typeof loader>();
  const navigate = useNavigate();

  // The site root is the Introduction and is prerendered as such. An old App link (`/?case=B2`, a hash) is forwarded to /app
  // right after hydration, with its query and hash kept.
  useEffect(() => {
    const target = legacyAppTarget(new URL(window.location.href));
    if (target) void navigate(target, { replace: true });
  }, [navigate]);

  return <IntroductionView data={data} />;
}
