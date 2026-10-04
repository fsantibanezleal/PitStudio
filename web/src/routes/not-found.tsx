import { NotFound } from "~/shell/NotFound";
import type { Route } from "./+types/not-found";

export const meta: Route.MetaFunction = () => [{ title: "Not found · PitStudio" }];

export default function NotFoundPage() {
  return <NotFound />;
}
