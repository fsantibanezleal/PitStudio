import { ChartSandbox } from "~/charts/Sandbox";
import type { Route } from "./+types/charts";

export const meta: Route.MetaFunction = () => [{ title: "Charts · PitStudio" }];

export default function ChartsSandboxPage() {
  return <ChartSandbox />;
}
