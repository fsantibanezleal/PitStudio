import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import styles from "~/cases/cases.module.css";
import { UnverifiedBadge } from "./ParametersSection";
import type { EquationRow } from "./types";

type Evaluate = (engine: string, equation: string) => Promise<{ value: number; unit: string }>;

function TryIt({ engine, equation, evaluate }: { engine: string; equation: string; evaluate?: Evaluate }) {
  const { t } = useTranslation("results");
  const [result, setResult] = useState<{ value: number; unit: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const press = async () => {
    setResult(null);
    setError(null);
    if (!evaluate) {
      setError(t("knowledge.eq.noEngine"));
      return;
    }
    try {
      setResult(await evaluate(engine, equation));
    } catch {
      setError(t("knowledge.eq.failed"));
    }
  };
  return (
    <div data-testid="try-it" data-engine={engine}>
      <button type="button" onClick={press}>
        {t("knowledge.eq.tryIt")}
      </button>
      {result && Number.isFinite(result.value) && (
        <p data-testid="try-result">
          {t("knowledge.eq.result", { value: String(result.value), unit: result.unit })}
        </p>
      )}
      {error && <p role="alert">{error}</p>}
    </div>
  );
}

/**
 * FR-020-34: per equation the rendering made at build time (`html`, or the LaTeX as code when there is none), its symbols with
 * units, source, verification, implementing symbol and theory link, and a "Try it" panel only where a browser engine exists.
 */
export function EquationsSection({ equations, evaluate }: { equations: EquationRow[]; evaluate?: Evaluate }) {
  const { t } = useTranslation("results");
  return (
    <section data-testid="equations" aria-label={t("knowledge.nav.equations")}>
      {equations.map((e) => (
        <article key={e.id} data-equation={e.id} id={`eq-${e.id}`} className={styles.card}>
          <h3>{e.title}</h3>
          <div data-testid="eq-rendered">
            {e.html ? (
              // The only HTML the client inserts: KaTeX output rendered at build time from the bundle's own LaTeX.
              // biome-ignore lint/security/noDangerouslySetInnerHtml: build-time KaTeX markup, never user input
              <span dangerouslySetInnerHTML={{ __html: e.html }} />
            ) : (
              <code>{e.latex}</code>
            )}
          </div>
          <table className={styles.table}>
            <thead>
              <tr>
                <th scope="col">{t("knowledge.eq.symbol")}</th>
                <th scope="col">{t("knowledge.eq.meaning")}</th>
                <th scope="col">{t("knowledge.eq.units")}</th>
              </tr>
            </thead>
            <tbody>
              {e.symbols.map((s) => (
                <tr key={s.symbol}>
                  <td>
                    <code>{s.symbol}</code>
                  </td>
                  <td>{s.meaning}</td>
                  <td>{s.units}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {e.citation && (
            <p>
              <Link to={`/knowledge/?section=bibliography#${e.citation}`}>
                {t("knowledge.eq.source", { key: e.citation, page: e.page ?? "" })}
              </Link>
            </p>
          )}
          {e.verification === "UNVERIFIED" && <UnverifiedBadge />}
          {e.function && (
            <p>
              {t("knowledge.eq.function")}: <code data-field="function">{e.function}</code>
            </p>
          )}
          {e.theory && (
            <p>
              <Link data-testid="theory-link" to={`/theory/${e.theory.topic}/#${e.theory.anchor}`}>
                {t("knowledge.eq.theory")}
              </Link>
            </p>
          )}
          {e.engine && <TryIt engine={e.engine.id} equation={e.id} evaluate={evaluate} />}
        </article>
      ))}
    </section>
  );
}
