import { ArrowDown, ArrowUp, ArrowUpDown } from 'lucide-react';

// Generic dense data-grid: `columns` = [{ key, label, align?, format?, sortable? }]
export default function DataTable({ columns, rows, sortBy, sortDir, onSort, loading }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-800">
      <table className="w-full min-w-[760px] border-collapse text-left text-[11px]">
        <thead className="sticky top-0 bg-slate-100 dark:bg-slate-900">
          <tr>
            {columns.map((col) => {
              const isSorted = sortBy === col.key;
              const Icon = isSorted ? (sortDir === 'asc' ? ArrowUp : ArrowDown) : ArrowUpDown;
              return (
                <th
                  key={col.key}
                  onClick={col.sortable === false ? undefined : () => onSort(col.key)}
                  className={`whitespace-nowrap border-b border-slate-200 dark:border-slate-800 px-3 py-2 font-mono text-[10px] uppercase tracking-wide text-slate-500 dark:text-slate-400 ${
                    col.sortable === false ? '' : 'cursor-pointer select-none hover:text-cyan-700 dark:hover:text-cyan-300'
                  } ${col.align === 'right' ? 'text-right' : 'text-left'}`}
                >
                  <span className="inline-flex items-center gap-1">
                    {col.label}
                    {col.sortable !== false && (
                      <Icon size={10} className={isSorted ? 'text-cyan-600 dark:text-cyan-400' : 'text-slate-400 dark:text-slate-700'} />
                    )}
                  </span>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && !loading && (
            <tr>
              <td colSpan={columns.length} className="px-3 py-8 text-center text-slate-500 dark:text-slate-400">
                No rows match the current filters.
              </td>
            </tr>
          )}
          {rows.map((row, i) => (
            <tr
              key={row.id ?? i}
              className="border-b border-slate-100 transition-colors odd:bg-slate-50/50 hover:bg-slate-100/80 dark:border-slate-800/60 dark:odd:bg-slate-900/20 dark:hover:bg-slate-800/40"
            >
              {columns.map((col) => (
                <td
                  key={col.key}
                  className={`whitespace-nowrap px-3 py-1.5 font-mono text-slate-800 dark:text-slate-300 ${
                    col.align === 'right' ? 'text-right' : 'text-left'
                  }`}
                >
                  {col.format ? col.format(row[col.key], row) : String(row[col.key] ?? '—')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
