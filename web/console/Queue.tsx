import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Alert } from "./Alert";
import { api, message } from "./api";
import { useLoad } from "./hooks";

export function Queue() {
  const { t } = useTranslation();
  const { data, error, loading, reload } = useLoad(api.queue, "queue", 3000);
  const [failure, setFailure] = useState<string>();

  const cancel = async (id: string) => {
    try {
      await api.cancelJob(id);
      setFailure(undefined);
    } catch (e) {
      setFailure(message(e));
    }
    reload();
  };

  return (
    <>
      <Alert text={failure ?? error} />
      {loading && !data && <p>{t("loading")}</p>}
      {data && (
        <table aria-label={t("queue.table")}>
          <thead>
            <tr>
              {["job", "recipe", "state", "run", "stage", "shards", "action"].map((c) => (
                <th key={c} scope="col">
                  {t(`col.${c}`)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.jobs.map((j) => (
              <tr key={j.job_id}>
                <td>
                  <code>{j.job_id}</code>
                </td>
                <td>{j.recipe}</td>
                <td>{j.state}</td>
                <td>{j.run_id ?? "–"}</td>
                <td>{j.stage ? `${j.stage.id}${j.stage.variant ? `@${j.stage.variant}` : ""}` : "–"}</td>
                <td>{j.shards ? `${j.shards.done}/${j.shards.total}` : "–"}</td>
                <td>
                  {(j.state === "queued" || j.state === "running") && (
                    <button
                      type="button"
                      aria-label={t("queue.cancelJob", { id: j.job_id })}
                      onClick={() => void cancel(j.job_id)}
                    >
                      {t("queue.cancel")}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {data && data.jobs.length === 0 && <p>{t("empty")}</p>}
    </>
  );
}
