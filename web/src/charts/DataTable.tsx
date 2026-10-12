import { useState } from "react";
import { useTranslation } from "react-i18next";
import styles from "./chart.module.css";

export interface TableColumn {
  /** Header text with its unit, e.g. "speed (m/s)". */
  header: string;
  values: ArrayLike<number>;
}

const WINDOW_ROWS = 200;
const ROW_HEIGHT = 26;
/** Up to this many rows are all in the DOM; a longer series is windowed (the rows are still all there, in the data). */
const ALL_ROWS_LIMIT = 5000;

/** A reading as the table shows it: at most 12 significant digits, `null` for a missing reading (never 0). */
function cell(value: number, missing: string): string {
  return Number.isFinite(value) ? String(Number(value.toPrecision(12))) : missing;
}

/**
 * The values of every plotted series from the FULL data (FR-020-11): units in the header cells, the missing readings marked
 * as such. A series longer than 5,000 rows is shown through a scrolling window that renders only the rows in view, so the
 * table of a million samples stays usable; `data-rows` always carries the number of rows of the full data.
 */
export function DataTable({ x, columns, label }: { x: TableColumn; columns: TableColumn[]; label: string }) {
  const { t } = useTranslation("charts");
  const rows = x.values.length;
  const [top, setTop] = useState(0);
  const windowed = rows > ALL_ROWS_LIMIT;
  const first = windowed ? Math.max(0, Math.min(rows - WINDOW_ROWS, top)) : 0;
  const last = windowed ? Math.min(rows, first + WINDOW_ROWS) : rows;
  const missing = t("notAvailable");
  const all = [x, ...columns];

  const body = [];
  for (let i = first; i < last; i++) {
    body.push(
      <tr key={i}>
        {all.map((c, k) => (
          <td key={c.header} data-col={k}>
            {cell(c.values[i] as number, missing)}
          </td>
        ))}
      </tr>,
    );
  }

  const table = (
    <table data-testid="chart-table" data-rows={rows} className={styles.table} aria-label={label}>
      <thead>
        <tr>
          {all.map((c) => (
            <th key={c.header} scope="col">
              {c.header}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {windowed && first > 0 && (
          <tr style={{ height: first * ROW_HEIGHT }}>
            <td colSpan={all.length} />
          </tr>
        )}
        {body}
        {windowed && last < rows && (
          <tr style={{ height: (rows - last) * ROW_HEIGHT }}>
            <td colSpan={all.length} />
          </tr>
        )}
      </tbody>
    </table>
  );

  if (!windowed) return <div className={styles.tableWrap}>{table}</div>;
  return (
    <div
      className={styles.tableWrap}
      onScroll={(event) => setTop(Math.floor(event.currentTarget.scrollTop / ROW_HEIGHT))}
    >
      {table}
    </div>
  );
}
