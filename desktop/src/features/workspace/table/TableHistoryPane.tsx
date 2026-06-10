export function TableHistoryPane({ tableId }: { tableId: string }) {
  return (
    <div className="p-4 flex flex-col gap-2 text-[11px] text-slate-600">
      <div className="border border-slate-200 rounded-lg p-3 bg-white">今天 14:12 预览了 {tableId}</div>
      <div className="border border-slate-200 rounded-lg p-3 bg-white">今天 13:58 查看字段结构</div>
      <div className="border border-slate-200 rounded-lg p-3 bg-white">昨天 18:20 作为问数上下文</div>
    </div>
  );
}
