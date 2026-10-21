import type { ReactNode } from 'react';
import EmptyState from './EmptyState';

export interface Column<T> {
  header: string;
  cell: (row: T) => ReactNode;
}

interface DataTableProps<T> {
  /** Names the table for screen readers. */
  caption: string;
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string | number;
  /** Shown instead of the table when there are no rows, e.g. "No products found". */
  emptyMessage: string;
}

/** The standard table for list screens: a header row, one row per record, an empty state. */
export default function DataTable<T>({
  caption,
  columns,
  rows,
  rowKey,
  emptyMessage,
}: DataTableProps<T>) {
  if (rows.length === 0) return <EmptyState message={emptyMessage} />;
  return (
    <table className="data-table">
      <caption className="visually-hidden">{caption}</caption>
      <thead>
        <tr>
          {columns.map((column) => (
            <th key={column.header} scope="col">
              {column.header}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={rowKey(row)}>
            {columns.map((column) => (
              <td key={column.header}>{column.cell(row)}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
