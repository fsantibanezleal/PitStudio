import { type KeyboardEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { clip } from "./format";
import { SafeText } from "./SafeText";
import styles from "./studio.module.css";

const SHA256 = /^[0-9a-f]{64}$/;
const TYPEAHEAD_RESET_MS = 600;

interface Row {
  path: string;
  key: string;
  value: unknown;
  level: number;
  parent: string | null;
  size: number;
  pos: number;
}

const isContainer = (value: unknown): value is Record<string, unknown> | unknown[] =>
  typeof value === "object" && value !== null && Object.keys(value).length > 0;

/** RFC 6901 token: `~` is `~0` and `/` is `~1`. */
const token = (key: string) => key.replaceAll("~", "~0").replaceAll("/", "~1");

function childrenOf(value: unknown, path: string, level: number): Row[] {
  if (!isContainer(value)) return [];
  // `$schema` of a card names its JSON Schema; it is a pointer for tools, not part of the run, so the viewer skips it.
  const entries: Array<[string, unknown]> = Array.isArray(value)
    ? value.map((v, i) => [String(i), v])
    : Object.entries(value).filter(([key]) => !(level === 1 && key === "$schema"));
  return entries.map(([key, v], i) => ({
    path: `${path}/${token(key)}`,
    key,
    value: v,
    level,
    parent: path === "" ? null : path,
    size: entries.length,
    pos: i + 1,
  }));
}

/** The rows that are on screen: the open parents' children, depth first, in document order. */
function visibleRows(root: unknown, open: ReadonlySet<string>): Row[] {
  const out: Row[] = [];
  const walk = (value: unknown, path: string, level: number) => {
    for (const row of childrenOf(value, path, level)) {
      out.push(row);
      if (open.has(row.path)) walk(row.value, row.path, level + 1);
    }
  };
  walk(root, "", 1);
  return out;
}

function Leaf({ value }: { value: unknown }) {
  const { t } = useTranslation("studio");
  if (typeof value === "string") {
    if (SHA256.test(value)) {
      return (
        <>
          <span data-testid="leaf-value" className={styles.mono}>
            {value}
          </span>{" "}
          <button
            type="button"
            data-testid="copy-sha"
            aria-label={t("tree.copySha")}
            onClick={(e) => {
              e.stopPropagation();
              void navigator.clipboard?.writeText(value).catch(() => undefined);
            }}
          >
            {t("tree.copy")}
          </button>
        </>
      );
    }
    return (
      <span data-testid="leaf-value">
        <SafeText value={value} />
      </span>
    );
  }
  let text: string;
  if (Array.isArray(value)) text = "[]";
  else if (typeof value === "object" && value !== null) text = "{}";
  else text = JSON.stringify(value) ?? String(value);
  return <span data-testid="leaf-value">{text}</span>;
}

/**
 * The run card as a collapsible tree with the keys of the WAI-ARIA tree view pattern (FR-019-23). Only the rows of
 * open parents are rendered, so the work is proportional to what the visitor opened, not to the size of the card.
 */
export function ManifestTree({ value }: { value: unknown }) {
  const { t } = useTranslation("studio");
  const [open, setOpen] = useState<ReadonlySet<string>>(() => new Set());
  const [focus, setFocus] = useState<string | null>(null);
  const items = useRef(new Map<string, HTMLElement>());
  const wantFocus = useRef(false);
  const typed = useRef({ text: "", at: 0 });
  const started = useRef(typeof performance !== "undefined" ? performance.now() : 0);

  const rows = useMemo(() => visibleRows(value, open), [value, open]);
  const tabStop = focus !== null && rows.some((r) => r.path === focus) ? focus : (rows[0]?.path ?? null);

  useEffect(() => {
    try {
      performance.measure("studio:manifest-render", { start: started.current, end: performance.now() });
    } catch {
      // User Timing is a measurement aid only
    }
  }, []);

  useEffect(() => {
    if (wantFocus.current && tabStop !== null) {
      wantFocus.current = false;
      items.current.get(tabStop)?.focus();
    }
  });

  const moveTo = useCallback((path: string | undefined) => {
    if (path === undefined) return;
    wantFocus.current = true;
    setFocus(path);
  }, []);

  const toggle = useCallback((path: string, force?: boolean) => {
    setOpen((current) => {
      const next = new Set(current);
      const want = force ?? !next.has(path);
      if (want) next.add(path);
      else next.delete(path);
      return next;
    });
  }, []);

  const onKeyDown = (event: KeyboardEvent<HTMLElement>, row: Row) => {
    if (event.target !== event.currentTarget) return;
    event.stopPropagation();
    const at = rows.findIndex((r) => r.path === row.path);
    const parent = isContainer(row.value);
    const isOpen = open.has(row.path);
    switch (event.key) {
      case "ArrowDown":
        moveTo(rows[Math.min(at + 1, rows.length - 1)]?.path);
        break;
      case "ArrowUp":
        moveTo(rows[Math.max(at - 1, 0)]?.path);
        break;
      case "ArrowRight":
        if (parent && !isOpen) {
          toggle(row.path, true);
          wantFocus.current = true;
        } else if (parent && isOpen) moveTo(rows[at + 1]?.path);
        break;
      case "ArrowLeft":
        if (parent && isOpen) {
          toggle(row.path, false);
          wantFocus.current = true;
        } else if (row.parent !== null) moveTo(row.parent);
        break;
      case "Home":
        moveTo(rows[0]?.path);
        break;
      case "End":
        moveTo(rows[rows.length - 1]?.path);
        break;
      case "Enter":
        if (parent) toggle(row.path);
        break;
      case "*": {
        const siblings = rows.filter(
          (r) => r.parent === row.parent && r.level === row.level && isContainer(r.value),
        );
        setOpen((current) => new Set([...current, ...siblings.map((r) => r.path)]));
        break;
      }
      default: {
        if (event.key.length !== 1 || event.ctrlKey || event.metaKey || event.altKey) return;
        const now = Date.now();
        const buffer =
          now - typed.current.at > TYPEAHEAD_RESET_MS ? event.key : typed.current.text + event.key;
        typed.current = { text: buffer, at: now };
        const needle = buffer.toLowerCase();
        const order = [...rows.slice(at + 1), ...rows.slice(0, at + 1)];
        moveTo(order.find((r) => r.key.toLowerCase().startsWith(needle))?.path);
        break;
      }
    }
    if (["ArrowDown", "ArrowUp", "ArrowRight", "ArrowLeft", "Home", "End", "Enter", "*"].includes(event.key))
      event.preventDefault();
  };

  const renderRow = (row: Row) => {
    const parent = isContainer(row.value);
    const isOpen = parent && open.has(row.path);
    return (
      <li
        key={row.path}
        role="treeitem"
        data-path={row.path}
        aria-level={row.level}
        aria-setsize={row.size}
        aria-posinset={row.pos}
        aria-expanded={parent ? isOpen : undefined}
        tabIndex={row.path === tabStop ? 0 : -1}
        ref={(el) => {
          if (el) items.current.set(row.path, el);
          else items.current.delete(row.path);
        }}
        onKeyDown={(e) => onKeyDown(e, row)}
        onFocus={(e) => {
          if (e.target === e.currentTarget) setFocus(row.path);
        }}
        onClick={(e) => {
          if (e.target !== e.currentTarget && !(e.target as HTMLElement).dataset.row) return;
          e.stopPropagation();
          setFocus(row.path);
          if (parent) toggle(row.path);
        }}
        className={styles.treeItem}
      >
        <span data-row="true" className={styles.treeRow}>
          <span className={styles.treeKey}>{clip(row.key)}</span>
          {parent ? (
            <span data-testid="summary" className={styles.treeSummary}>
              {Array.isArray(row.value)
                ? `[${row.value.length}]`
                : `{${Object.keys(row.value as object).length}}`}
            </span>
          ) : (
            <>
              {": "}
              <Leaf value={row.value} />
            </>
          )}
        </span>
        {isOpen && (
          // biome-ignore lint/a11y/useSemanticElements: role="group" holds the children of a treeitem
          <ul role="group" className={styles.treeGroup}>
            {childrenOf(row.value, row.path, row.level + 1).map(renderRow)}
          </ul>
        )}
      </li>
    );
  };

  return (
    // biome-ignore lint/a11y/noNoninteractiveElementToInteractiveRole: the WAI-ARIA tree pattern requires role="tree" on a list
    <ul role="tree" data-testid="manifest-tree" aria-label={t("tree.label")} className={styles.tree}>
      {childrenOf(value, "", 1).map(renderRow)}
    </ul>
  );
}
