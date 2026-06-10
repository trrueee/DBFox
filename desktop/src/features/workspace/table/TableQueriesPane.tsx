export function TableQueriesPane({ tableId, onOpenSqlConsole }: { tableId: string; onOpenSqlConsole: () => void }) {
  const queries = [
    `SELECT * FROM ${tableId} LIMIT 100;`,
    `SELECT status, COUNT(*) FROM ${tableId} GROUP BY status;`,
  ];

  return (
    <div className="p-4 flex flex-col gap-3">
      {queries.map((sql, index) => (
        <div key={sql} className="border border-slate-200 rounded-lg p-3 bg-white hover:border-indigo-300 cursor-pointer" onClick={onOpenSqlConsole}>
          <div className="font-semibold text-[11px] text-slate-800 mb-2">样例查询 {index + 1}</div>
          <pre className="text-[10px] font-mono text-blue-600 whitespace-pre-wrap">{sql}</pre>
        </div>
      ))}
    </div>
  );
}
