import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router";
import { MAX_QUERY, truncateQuery } from "./search";

/** The text of the `q` URL parameter, as typed (a literal string, never a pattern). */
export function useQuery(): [string, (value: string) => void] {
  const [params, setParams] = useSearchParams();
  const q = truncateQuery(params.get("q") ?? "");
  const set = (value: string) => {
    const next = new URLSearchParams(params);
    if (value === "") next.delete("q");
    else next.set("q", truncateQuery(value));
    setParams(next, { replace: true, preventScrollReset: true });
  };
  return [q, set];
}

/** The search field of a knowledge section: `type=search`, at most 2,000 characters, bound to `?q=`. */
export function SearchField() {
  const { t } = useTranslation("results");
  const [q, setQ] = useQuery();
  return (
    <input
      type="search"
      data-testid="search"
      aria-label={t("knowledge.search")}
      placeholder={t("knowledge.search")}
      maxLength={MAX_QUERY}
      value={q}
      onChange={(e) => setQ(e.target.value)}
    />
  );
}
