import { useTranslation } from "react-i18next";
import { clip } from "../format";
import styles from "../studio.module.css";
import type { RunCard, StudioTool } from "../types";

const SAFE = /^[A-Za-z0-9._-]+(?:\/[A-Za-z0-9._-]+)*$/;

/** A repository-relative path or a plain name; anything absolute or odd keeps only its last segment, never a directory of the machine. */
export function relativeToken(value: unknown): string | null {
  if (typeof value !== "string" || value === "") return null;
  if (SAFE.test(value) && !value.split("/").includes("..")) return value;
  const last = value.split(/[\\/]/).filter(Boolean).pop() ?? "";
  return SAFE.test(last) && last !== ".." ? last : null;
}

/** Block 7: the runner commands of the tool's published runs and what they need (FR-019-18). */
export function ReproduceBlock({ tool, runs }: { tool: StudioTool; runs: RunCard[] }) {
  const { t } = useTranslation("studio");
  const mine = runs.filter((r) => r.stages.some((s) => s.tool === tool.id));
  return (
    <section data-block="reproduce" className={styles.block} aria-labelledby="b-reproduce">
      <h2 id="b-reproduce">{t("blocks.reproduce.title")}</h2>
      {mine.map((run) => {
        const recipe = relativeToken(run.recipe?.path);
        const profile = relativeToken(run.profile);
        return (
          <div key={run.run_id} data-run={run.run_id}>
            <p>{clip(run.run_id)}</p>
            {recipe && (
              <code data-command className={styles.command}>
                {`uv run studio run ${recipe}${profile ? ` --profile ${profile}` : ""}`}
              </code>
            )}
          </div>
        );
      })}
      {mine.length === 0 && <p>{t("blocks.reproduce.noRuns")}</p>}
      {tool.licence_class === "reference-only" && <p>{t("blocks.reproduce.needsNvidia")}</p>}
    </section>
  );
}
