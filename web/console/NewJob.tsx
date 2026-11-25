import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Alert } from "./Alert";
import { api, type JobRequest, type Json, message, type StageRef } from "./api";
import { useLoad } from "./hooks";

const key = (s: StageRef) => `${s.id}${s.variant ? `@${s.variant}` : ""}`;

/** The run form: one POST /jobs with exactly what the maintainer ticked (no stage ticked means every stage). */
export function NewJob() {
  const { t } = useTranslation();
  const recipes = useLoad(api.recipes, "recipes");
  const valid = (recipes.data?.recipes ?? []).filter((r) => r.valid && r.id);
  const [chosen, setChosen] = useState<string>();
  const recipe = chosen ?? valid[0]?.id ?? undefined;
  const detail = useLoad<Json>(() => (recipe ? api.recipe(recipe) : Promise.resolve({})), recipe ?? "");
  const stages = (Array.isArray(detail.data?.stages) ? detail.data.stages : []) as StageRef[];
  const [profile, setProfile] = useState("");
  const [ticked, setTicked] = useState<string[]>([]);
  const [force, setForce] = useState(false);
  const [rerun, setRerun] = useState(false);
  const [status, setStatus] = useState("");
  const [failure, setFailure] = useState<string>();

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!recipe) return;
    const req: JobRequest = { recipe, profile };
    const picked = stages.filter((s) => ticked.includes(key(s)));
    if (picked.length)
      req.stages = picked.map((s) => ({ id: s.id, ...(s.variant ? { variant: s.variant } : {}) }));
    if (force) req.force = true;
    if (rerun) req.rerun_check = true;
    try {
      const created = await api.createJob(req);
      setStatus(t("form.queued", { id: created.job_id }));
      setFailure(undefined);
    } catch (err) {
      setStatus("");
      setFailure(message(err));
    }
  };

  return (
    <>
      <Alert text={failure ?? recipes.error ?? detail.error} />
      <form aria-label={t("form.name")} onSubmit={(e) => void submit(e)}>
        {valid.length === 0 && !recipes.loading && <p>{t("form.noRecipes")}</p>}
        <label>
          {t("form.recipe")}
          <select
            value={recipe ?? ""}
            onChange={(e) => {
              setChosen(e.target.value);
              setTicked([]);
            }}
          >
            {valid.map((r) => (
              <option key={r.path} value={r.id ?? ""}>
                {r.id}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t("form.profile")}
          <input
            type="text"
            value={profile}
            onChange={(e) => setProfile(e.target.value)}
            required
            autoComplete="off"
            spellCheck={false}
          />
        </label>
        <fieldset>
          <legend>{t("form.stages")}</legend>
          {stages.map((s) => (
            <label key={key(s)} className="check">
              <input
                type="checkbox"
                checked={ticked.includes(key(s))}
                onChange={(e) =>
                  setTicked((list) =>
                    e.target.checked ? [...list, key(s)] : list.filter((k) => k !== key(s)),
                  )
                }
              />
              {key(s)}
            </label>
          ))}
        </fieldset>
        <label className="check">
          <input type="checkbox" checked={force} onChange={(e) => setForce(e.target.checked)} />
          {t("form.force")}
        </label>
        <label className="check">
          <input type="checkbox" checked={rerun} onChange={(e) => setRerun(e.target.checked)} />
          {t("form.rerun")}
        </label>
        <button type="submit">{t("form.submit")}</button>
      </form>
      <p role="status">{status}</p>
    </>
  );
}
