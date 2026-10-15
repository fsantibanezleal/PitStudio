import { useState } from "react";
import { useTranslation } from "react-i18next";

const LIMIT = 200;
const REPLACEMENT = "�";

/** C0 and C1 controls (a line feed and a tab are kept), DEL, and the bidirectional override and isolate characters. */
function isUnsafe(code: number): boolean {
  if (code === 0x09 || code === 0x0a) return false;
  return (
    code < 0x20 ||
    (code >= 0x7f && code <= 0x9f) ||
    (code >= 0x202a && code <= 0x202e) ||
    (code >= 0x2066 && code <= 0x2069)
  );
}

/** The first `limit` code points of `value` (all of it when `limit` is Infinity) with every unsafe character replaced, and whether more followed. */
export function sanitize(value: string, limit: number): { text: string; cut: boolean } {
  let text = "";
  let count = 0;
  for (const ch of value) {
    if (count === limit) return { text, cut: true };
    text += isUnsafe(ch.codePointAt(0) ?? 0) ? REPLACEMENT : ch;
    count += 1;
  }
  return { text, cut: false };
}

/**
 * A manifest, run card or registry string as escaped text (FR-019-40): controls replaced, cut after 200 characters
 * with an expander. React renders the string as a text node, so no markup in it is ever parsed.
 */
export function SafeText({ value }: { value: string }) {
  const { t } = useTranslation("studio");
  const [open, setOpen] = useState(false);
  const { text, cut } = sanitize(String(value), open ? Number.POSITIVE_INFINITY : LIMIT);
  const truncated = cut || open ? sanitize(String(value), LIMIT).cut : false;
  return (
    <span data-testid="safe-text" data-truncated={String(truncated)}>
      <span data-testid="safe-text-value">{cut ? `${text}…` : text}</span>
      {truncated && (
        <button type="button" data-testid="expand" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
          {open ? t("safe.showLess") : t("safe.showFull")}
        </button>
      )}
    </span>
  );
}
