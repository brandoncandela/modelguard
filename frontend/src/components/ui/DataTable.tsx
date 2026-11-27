import { type CSSProperties, type ReactNode, useMemo, useState } from "react";
import { Empty } from "./index";

export interface Column<T> {
  key: string;
  header: ReactNode;
  render?: (row: T) => ReactNode;
  sort?: (row: T) => string | number | null | undefined;
  align?: "left" | "right";
  className?: string;
}

export function DataTable<T>({ rows, columns, onRowClick, rowKey, empty = "No records.", initialSort, dense, maxHeight }: {
  rows: T[]; columns: Column<T>[]; onRowClick?: (r: T) => void; rowKey: (r: T) => string; empty?: ReactNode;
  initialSort?: { key: string; dir: "asc" | "desc" }; dense?: boolean; maxHeight?: string;
}) {
  const [sort, setSort] = useState(initialSort);
  const sorted = useMemo(() => {
    if (!sort) return rows;
    const col = columns.find((c) => c.key === sort.key);
    if (!col?.sort) return rows;
    const get = col.sort;
    return [...rows].sort((a, b) => {
      const x = get(a), y = get(b);
      if (x === y) return 0;
      if (x === null || x === undefined) return 1;
      if (y === null || y === undefined) return -1;
      return (x < y ? -1 : 1) * (sort.dir === "asc" ? 1 : -1);
    });
  }, [rows, sort, columns]);
  if (!rows.length) return <Empty>{empty}</Empty>;
  return (
    <div className="overflow-auto" style={maxHeight ? { maxHeight } : undefined}>
      {/* On phones, keep about 112px per column and scroll sideways instead of breaking IDs and dates mid-token. */}
      <table className="w-full border-separate border-spacing-0 max-sm:min-w-[var(--dt-min)]"
        style={{ "--dt-min": `${Math.min(columns.length * 112, 960)}px` } as CSSProperties}>
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key} className={`th ${c.align === "right" ? "text-right" : ""} ${c.className ?? ""}`}
                aria-sort={sort?.key === c.key ? (sort.dir === "asc" ? "ascending" : "descending") : undefined}>
                {c.sort ? (
                  <button className="inline-flex items-center gap-1 uppercase hover:text-ink"
                    onClick={() => setSort((s) => ({ key: c.key, dir: s?.key === c.key && s.dir === "asc" ? "desc" : "asc" }))}>
                    {c.header}{sort?.key === c.key ? (sort.dir === "asc" ? " ▲" : " ▼") : ""}
                  </button>
                ) : c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((r) => (
            <tr key={rowKey(r)} className={onRowClick ? "tr-click" : ""} onClick={onRowClick ? () => onRowClick(r) : undefined}
              tabIndex={onRowClick ? 0 : undefined} onKeyDown={onRowClick ? (e) => e.key === "Enter" && onRowClick(r) : undefined}>
              {columns.map((c) => (
                <td key={c.key} className={`td ${dense ? "py-1.5" : ""} ${c.align === "right" ? "text-right tabular-nums" : ""} ${c.className ?? ""}`}>
                  {c.render ? c.render(r) : String((r as any)[c.key] ?? "–")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
