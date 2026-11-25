import { GpuPage } from "~/studio/GpuPage";
import type { Route } from "./+types/studio-gpu";

export const meta: Route.MetaFunction = () => [{ title: "GPU evidence · Studio · PitStudio" }];

export default function StudioGpuRoute() {
  return <GpuPage />;
}
