import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Alert } from "./Alert";
import { api, type Json } from "./api";
import { useLoad } from "./hooks";
import { Telemetry } from "./Telemetry";

const BYTE_UNIT = "B"; // the SI symbol is the same in every language

interface Artefact {
  id: string;
  kind: string;
  media_type?: string;
  bytes: number;
}

function Artefacts({ run, items }: { run: string; items: Artefact[] }) {
  const { t } = useTranslation();
  return (
    <section aria-label={t("runs.artefacts")}>
      <h3>{t("runs.artefacts")}</h3>
      {items.length === 0 && <p>{t("runs.noArtefacts")}</p>}
      {items.map((a) => {
        const url = api.artefactUrl(run, a.id);
        return (
          <article key={a.id} data-testid={`artefact-${a.id}`} className="artefact">
            <h4>
              {a.id} <span className="muted">{`(${a.kind}, ${a.bytes} ${BYTE_UNIT})`}</span>
            </h4>
            {a.media_type?.startsWith("video/") && (
              <video controls preload="none" width="320" src={url} aria-label={a.id}>
                <track kind="captions" />
              </video>
            )}
            {a.media_type?.startsWith("image/") && <img src={url} alt={a.id} width="320" />}
            <p>
              <a href={url}>
                {t("runs.open")} {a.id}
              </a>
            </p>
          </article>
        );
      })}
    </section>
  );
}

function RunDetails({ id, onClose }: { id: string; onClose: () => void }) {
  const { t } = useTranslation();
  const { data, error } = useLoad<Json>(() => api.run(id), id);
  const artefacts = Array.isArray(data?.artefacts) ? (data.artefacts as Artefact[]) : [];
  const notes = Array.isArray(data?.notes) ? (data.notes as string[]) : [];
  const stages = Array.isArray(data?.stages) ? (data.stages as Json[]) : [];
  const tails = stages.filter((s) => typeof s.log_tail === "string" && s.log_tail !== "");
  return (
    <section aria-label={t("runs.details")} className="details">
      <h2>{id}</h2>
      <button type="button" onClick={onClose}>
        {t("runs.close")}
      </button>
      <Alert text={error} />
      {data && (
        <>
          <section aria-label={t("runs.manifest")}>
            <h3>{t("runs.manifest")}</h3>
            {notes.length > 0 && (
              <>
                <h4>{t("runs.notes")}</h4>
                <ul>
                  {notes.map((n) => (
                    <li key={n}>{n}</li>
                  ))}
                </ul>
              </>
            )}
            {tails.map((s) => (
              <div key={String((s.key as Json | undefined)?.id)}>
                <h4>
                  {t("runs.logTail")} {String((s.key as Json | undefined)?.id)}
                </h4>
                <pre>{String(s.log_tail)}</pre>
              </div>
            ))}
            <pre>{JSON.stringify(data, null, 2)}</pre>
          </section>
          <Artefacts run={id} items={artefacts} />
        </>
      )}
      <Telemetry run={id} />
    </section>
  );
}

export function Runs() {
  const { t } = useTranslation();
  const { data, error, loading } = useLoad(api.runs, "runs");
  const [open, setOpen] = useState<string>();
  useEffect(() => {
    if (open && data && !data.runs.some((r) => r.run_id === open)) setOpen(undefined);
  }, [data, open]);
  return (
    <>
      <Alert text={error} />
      {loading && !data && <p>{t("loading")}</p>}
      {data && (
        <table aria-label={t("runs.table")}>
          <thead>
            <tr>
              {["run", "recipe", "state", "stages", "valid"].map((c) => (
                <th key={c} scope="col">
                  {t(`col.${c}`)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.runs.map((r) => (
              <tr key={r.run_id}>
                <td>
                  <button type="button" className="link" onClick={() => setOpen(r.run_id)}>
                    {r.run_id}
                  </button>
                </td>
                <td>{r.recipe ?? "–"}</td>
                <td>{r.state ?? "–"}</td>
                <td>{r.stages}</td>
                <td className={r.valid ? "ok" : "bad"}>{r.valid ? t("valid") : t("invalid")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {open && <RunDetails id={open} onClose={() => setOpen(undefined)} />}
    </>
  );
}
