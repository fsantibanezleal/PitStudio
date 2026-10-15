import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { EquationsSection } from "./EquationsSection";
import { GlossarySection } from "./GlossarySection";
import { BibliographySection, DatasetsSection, FrameworksSection } from "./ListSections";
import { ParametersSection } from "./ParametersSection";
import { type KnowledgeBundle, SECTIONS, type SectionId } from "./types";

const isSection = (s: unknown): s is SectionId => (SECTIONS as readonly unknown[]).includes(s);

/** FR-020-32: the six sections of the knowledge base and the minephys version and commit they were generated from. */
export function KnowledgeView({ bundle, section }: { bundle: KnowledgeBundle; section?: string }) {
  const { t } = useTranslation("results");
  const active: SectionId = isSection(section) ? section : "glossary";
  const commit = String(bundle.source?.minephys_commit ?? "");
  return (
    <div>
      <p data-testid="knowledge-provenance">
        <span title={commit}>
          {t("knowledge.provenance", {
            version: String(bundle.source?.minephys_version ?? ""),
            commit: commit.slice(0, 7),
          })}
        </span>
      </p>
      <nav data-testid="knowledge-nav" aria-label={t("knowledge.navLabel")}>
        <ul>
          {SECTIONS.map((id) => (
            <li key={id}>
              <Link to={`?section=${id}`} data-section={id} aria-current={id === active ? "page" : undefined}>
                {t(`knowledge.nav.${id}`)}
              </Link>
            </li>
          ))}
        </ul>
      </nav>
      {active === "glossary" && <GlossarySection entries={bundle.glossary ?? []} />}
      {active === "equations" && <EquationsSection equations={bundle.equations ?? []} />}
      {active === "parameters" && <ParametersSection parameters={bundle.parameters ?? []} />}
      {active === "datasets" && <DatasetsSection datasets={bundle.datasets ?? []} />}
      {active === "frameworks" && <FrameworksSection frameworks={bundle.frameworks ?? []} />}
      {active === "bibliography" && <BibliographySection bibliography={bundle.bibliography ?? []} />}
    </div>
  );
}
