import type { MethodStatus } from "./registry";

type Translate = (key: string, options?: Record<string, unknown>) => string;

/** The words of a computed status: "pass", "fail", or "Not yet run" while no published result exists. */
export function statusText(t: Translate, status: MethodStatus | undefined): string {
  if (status === "pass") return t("methodsPage.pass");
  if (status === "fail") return t("methodsPage.fail");
  return t("pending.status");
}
