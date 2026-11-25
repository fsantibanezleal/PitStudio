import { useTranslation } from "react-i18next";
import { CatalogueView } from "~/cases/CatalogueView";
import { caseRegistry } from "~/cases/registry";
import { toolRegistry } from "~/cases/tools";
import type { Route } from "./+types/cases";

export const meta: Route.MetaFunction = () => [{ title: "Cases · PitStudio" }];

export default function CasesPage() {
  const { t } = useTranslation("app");
  return (
    <article>
      <h1>{t("pages.cases.title")}</h1>
      <p>{t("pages.cases.lead")}</p>
      <CatalogueView registry={caseRegistry} tools={toolRegistry} />
    </article>
  );
}
