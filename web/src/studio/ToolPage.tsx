import { useTranslation } from "react-i18next";
import { NotFound } from "~/shell/NotFound";
import shell from "~/shell/shell.module.css";
import { AlternativesBlock } from "./blocks/Alternatives";
import { ArtefactsBlock } from "./blocks/Artefacts";
import { IdentityBlock } from "./blocks/Identity";
import { LimitsBlock } from "./blocks/Limits";
import { ProvenanceBlock } from "./blocks/ProvenanceBlock";
import { ReproduceBlock } from "./blocks/Reproduce";
import { RoleBlock } from "./blocks/Role";
import { WhereRanBlock } from "./blocks/WhereRan";
import {
  caseRegistry,
  studioIndex,
  toolById,
  useRunBundles,
  useRunSummaries,
  useStudioManifest,
} from "./data";
import { clip } from "./format";

/** `/studio/tools/<id>`: the eight blocks of a studio tool (FR-019-08); any other id is the not-found page (FR-019-20). */
export function ToolPage({ id }: { id: string | undefined }) {
  const tool = toolById(id);
  if (!tool) return <NotFound />;
  return <KnownToolPage toolId={tool.id} />;
}

function KnownToolPage({ toolId }: { toolId: string }) {
  const { t } = useTranslation("studio");
  const tool = toolById(toolId);
  const info = studioIndex.tools.find((i) => i.id === toolId);
  const manifest = useStudioManifest();
  const summaries = useRunSummaries();
  const mine = manifest.value.artefacts.filter((a) => a.producer.tool === toolId);
  // The runs that matter to the page: those that produced an artefact of the tool and those whose stages ran it (a failed variant leaves no artefact).
  const ids = [
    ...mine.map((a) => a.run_id),
    ...summaries.value
      .filter((r) => ((r as unknown as { tools?: string[] }).tools ?? []).includes(toolId))
      .map((r) => r.run_id),
  ];
  const bundles = useRunBundles(ids, false);
  const cards = bundles.value.map((b) => b.card);
  if (!tool || !info) return <NotFound />;

  return (
    <article className={shell.page}>
      <h1>{clip(tool.name)}</h1>
      <p className={shell.lead}>{t("toolPage.lead")}</p>
      <IdentityBlock tool={tool} info={info} />
      <RoleBlock tool={tool} cases={caseRegistry} />
      <ArtefactsBlock tool={tool} artefacts={mine} runs={cards} cards={cards} />
      <ProvenanceBlock artefacts={tool.status === "evaluated-not-adopted" ? [] : mine} />
      <WhereRanBlock artefacts={tool.status === "evaluated-not-adopted" ? [] : mine} runs={cards} />
      <LimitsBlock tool={tool} runs={cards} />
      <ReproduceBlock tool={tool} runs={cards} />
      <AlternativesBlock tool={tool} />
    </article>
  );
}
