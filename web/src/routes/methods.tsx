import { useTranslation } from "react-i18next";
import { MethodsIndex } from "~/methods/MethodsIndex";
import { methodRegistry } from "~/methods/registry";
import { methodStatuses } from "~/methods/statuses";
import { publishedBundles } from "~/results/bundles";
import type { Route } from "./+types/methods";

export const meta: Route.MetaFunction = () => [{ title: "Methods · PitStudio" }];

export default function MethodsPage() {
  const { t } = useTranslation("app");
  const { t: tResults } = useTranslation("results");
  return (
    <article>
      <h1>{t("pages.methods.title")}</h1>
      <p>{tResults("methodsPage.lead")}</p>
      <MethodsIndex methods={methodRegistry} statuses={methodStatuses(methodRegistry, publishedBundles)} />
    </article>
  );
}
