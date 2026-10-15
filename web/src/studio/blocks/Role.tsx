import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { type CaseRegistry, orderedCaseIds } from "~/cases/types";
import { SafeText } from "../SafeText";
import styles from "../studio.module.css";
import type { StudioTool } from "../types";

/** Block 2: the tool's mining role and the cases of the case registry that use it (FR-019-11). */
export function RoleBlock({ tool, cases }: { tool: StudioTool; cases: CaseRegistry }) {
  const { t } = useTranslation("studio");
  const users = orderedCaseIds(cases).filter((id) => Object.hasOwn(cases.cases[id]?.tools ?? {}, tool.id));
  return (
    <section data-block="role" className={styles.block} aria-labelledby="b-role">
      <h2 id="b-role">{t("blocks.role.title")}</h2>
      <p>
        <SafeText value={tool.role} />
      </p>
      {users.length > 0 ? (
        <p>
          {t("blocks.role.cases")}:{" "}
          {users.map((id) => (
            <Link key={id} to={`/cases/${id}/`} className={styles.chip}>
              {id}
            </Link>
          ))}
        </p>
      ) : (
        <p>{t("blocks.role.none")}</p>
      )}
    </section>
  );
}
