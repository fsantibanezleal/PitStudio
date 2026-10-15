import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Alert } from "./Alert";
import { api, type Json } from "./api";
import { useLoad } from "./hooks";

function RecipeDetails({ id }: { id: string }) {
  const { t } = useTranslation();
  const { data, error } = useLoad<Json>(() => api.recipe(id), id);
  return (
    <section aria-label={t("recipes.details")} className="details">
      <h2>{id}</h2>
      <Alert text={error} />
      {data && <pre>{JSON.stringify(data, null, 2)}</pre>}
    </section>
  );
}

export function Recipes() {
  const { t } = useTranslation();
  const { data, error, loading } = useLoad(api.recipes, "recipes");
  const [open, setOpen] = useState<string>();
  return (
    <>
      <Alert text={error} />
      {loading && !data && <p>{t("loading")}</p>}
      {data && (
        <table aria-label={t("recipes.table")}>
          <thead>
            <tr>
              {["id", "case", "stages", "status"].map((c) => (
                <th key={c} scope="col">
                  {t(`col.${c}`)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.recipes.map((r) => (
              <tr key={r.path}>
                <td>
                  {r.id ? (
                    <button type="button" className="link" onClick={() => setOpen(r.id ?? undefined)}>
                      {r.id}
                    </button>
                  ) : (
                    <code>
                      {r.path
                        .split("/")
                        .pop()
                        ?.replace(/\.yaml$/, "")}
                    </code>
                  )}
                </td>
                <td>{r.case ?? "–"}</td>
                <td>{r.stages}</td>
                <td className={r.valid ? "ok" : "bad"}>
                  {r.valid ? t("valid") : t("invalid")}
                  {!r.valid && r.errors[0] && <div className="why">{r.errors[0].message}</div>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {open && <RecipeDetails id={open} />}
    </>
  );
}
