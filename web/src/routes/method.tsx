import { MethodPage } from "~/methods/MethodPage";
import { methodBySlug, methodRegistry } from "~/methods/registry";
import { methodStatuses } from "~/methods/statuses";
import { publishedBundles } from "~/results/bundles";
import { NotFound } from "~/shell/NotFound";
import type { Route } from "./+types/method";

export const meta: Route.MetaFunction = ({ params }) => [{ title: `${params.slug ?? "Method"} · PitStudio` }];

export default function MethodRoute({ params }: Route.ComponentProps) {
  const method = methodBySlug(params.slug);
  if (!method) return <NotFound />;
  return <MethodPage method={method} status={methodStatuses(methodRegistry, publishedBundles)[method.id]} />;
}
