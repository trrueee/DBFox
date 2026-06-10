export function TableSchemaPane({ tableId }: { tableId: string }) {
  return (
    <div className="flex flex-col p-3 h-full overflow-auto">
      <span className="text-[10px] text-gray-400 block mb-1">字段列表 (Schema Structure) &gt; {tableId}</span>
      <table className="hifi-table">
        <thead>
          <tr><th>字段名</th><th>类型</th><th>约束</th><th>可空</th><th>默认值</th><th>注释</th></tr>
        </thead>
        <tbody>
          <tr><td>id</td><td className="text-blue-600 font-mono">bigint(20) unsigned</td><td><span className="hifi-constraint-badge pk">PK</span></td><td>否</td><td>—</td><td>主键 ID</td></tr>
          <tr><td>tenant_id</td><td className="text-blue-600 font-mono">bigint(20) unsigned</td><td><span className="hifi-constraint-badge index">INDEX</span></td><td>否</td><td>—</td><td>租户 ID</td></tr>
          <tr><td>name</td><td className="text-blue-600 font-mono">varchar(100)</td><td>—</td><td>否</td><td>—</td><td>名称</td></tr>
        </tbody>
      </table>
    </div>
  );
}
