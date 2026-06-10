import { ArrowUpDown, Code, Download, Filter, GitMerge, Maximize2, RefreshCw, Search, Sparkles, ZoomIn, ZoomOut } from "lucide-react";

interface TableWorkspaceProps {
  tableId: string;
  currentSubTab: string;
  onSubTabChange: (subTab: string) => void;
  onOpenSqlConsole: () => void;
  onToast: (message: string) => void;
}

export function TableWorkspace({ tableId, currentSubTab, onSubTabChange, onOpenSqlConsole, onToast }: TableWorkspaceProps) {
  return (
    <div className="hifi-table-workspace hifi-tab-pane">
      <div className="hifi-workspace-subtabs">
        {[
          ["preview", "数据预览"],
          ["schema", "字段结构"],
          ["er", "关系图"],
          ["queries", "样例查询"],
          ["history", "使用记录"],
        ].map(([key, label]) => (
          <div key={key} className={`hifi-workspace-subtab ${currentSubTab === key ? "active" : ""}`} onClick={() => onSubTabChange(key)}>
            {label}
          </div>
        ))}
      </div>

      <div className="hifi-subtab-content flex-1 overflow-auto">
        {currentSubTab === "preview" && <PreviewPane tableId={tableId} onOpenSqlConsole={onOpenSqlConsole} onToast={onToast} />}
        {currentSubTab === "schema" && <SchemaPane tableId={tableId} />}
        {currentSubTab === "er" && <ErPane tableId={tableId} />}
        {currentSubTab === "queries" && <QueriesPane tableId={tableId} onOpenSqlConsole={onOpenSqlConsole} />}
        {currentSubTab === "history" && <HistoryPane tableId={tableId} />}
      </div>
    </div>
  );
}

function PreviewPane({ tableId, onOpenSqlConsole, onToast }: { tableId: string; onOpenSqlConsole: () => void; onToast: (message: string) => void }) {
  const isComment = tableId === "comment_infos";
  const isVideo = tableId === "video_infos";

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="hifi-panel-toolbar">
        <div className="hifi-toolbar-left">
          <button className="hifi-toolbar-btn" onClick={() => onToast("数据预览已刷新")}><RefreshCw size={10} /> 刷新</button>
          <button className="hifi-toolbar-btn" onClick={() => onToast("打开过滤器")}><Filter size={10} /> 筛选</button>
          <button className="hifi-toolbar-btn" onClick={() => onToast("打开排序规则")}><ArrowUpDown size={10} /> 排序</button>
          <button className="hifi-toolbar-btn" onClick={() => onToast("已导出数据预览")}><Download size={10} /> 导出</button>
          <button className="hifi-toolbar-btn" onClick={() => onToast("测试数据已生成并写入")}><Sparkles size={10} className="text-yellow-600" /> 生成测试数据</button>
        </div>
        <div className="hifi-toolbar-right">
          <Search size={12} className="text-gray-400 cursor-pointer" />
          <button className="hifi-text-btn flex items-center gap-1" onClick={onOpenSqlConsole}><Code size={11} /> 在 SQL 运行</button>
        </div>
      </div>

      <div className="hifi-table-container flex-1 overflow-auto">
        <table className="hifi-table">
          <thead>
            {isComment ? (
              <tr><th>id</th><th>note_id</th><th>user_id</th><th>content</th><th>status</th><th>created_at</th></tr>
            ) : isVideo ? (
              <tr><th>id</th><th>title</th><th>url</th><th>duration</th><th>play_count</th><th>status</th></tr>
            ) : (
              <tr><th>id</th><th>tenant_id</th><th>name</th><th>account</th><th>status</th><th>created_at</th></tr>
            )}
          </thead>
          <tbody>
            {isComment ? <CommentRows /> : isVideo ? <VideoRows /> : <UserRows />}
          </tbody>
        </table>
      </div>

      <div className="hifi-table-footer">
        <span>共 12,345 条</span>
        <div className="hifi-pagination">
          <span className="text-gray-400 cursor-pointer">&lt;</span>
          <span className="hifi-page-num active">1</span>
          <span className="hifi-page-num">2</span>
          <span className="hifi-page-num">3</span>
          <span>...</span>
          <span className="hifi-page-num">1235</span>
          <span className="text-gray-400 cursor-pointer">&gt;</span>
        </div>
        <select className="border border-gray-200 rounded px-1 text-[10px]" defaultValue="10">
          <option value="10">10条/页</option>
          <option value="20">20条/页</option>
        </select>
      </div>
    </div>
  );
}

function StatusTag({ value }: { value: "active" | "inactive" | "pending" }) {
  return <span className={`hifi-status-tag ${value}`}><span className={`hifi-dot ${value}`} />{value}</span>;
}

function UserRows() {
  return <>
    <tr><td>1</td><td>10001</td><td>张三</td><td>zhangsan</td><td><StatusTag value="active" /></td><td>2024-11-16 10:23:45</td></tr>
    <tr><td>2</td><td>10001</td><td>李四</td><td>lisi</td><td><StatusTag value="active" /></td><td>2024-11-16 10:23:45</td></tr>
    <tr><td>3</td><td>10002</td><td>王五</td><td>wangwu</td><td><StatusTag value="inactive" /></td><td>2024-11-16 10:23:45</td></tr>
    <tr><td>4</td><td>10002</td><td>赵六</td><td>zhaoliu</td><td><StatusTag value="active" /></td><td>2024-11-16 10:23:45</td></tr>
  </>;
}

function CommentRows() {
  return <>
    <tr><td>101</td><td>20001</td><td>1</td><td className="max-w-[200px] truncate" title="这个系统界面太漂亮了！">这个系统界面太漂亮了！</td><td><StatusTag value="active" /></td><td>2024-11-17 08:32:00</td></tr>
    <tr><td>102</td><td>20002</td><td>2</td><td className="max-w-[200px] truncate" title="同意！设计细节直接拉满。">同意！设计细节直接拉满。</td><td><StatusTag value="active" /></td><td>2024-11-17 08:45:10</td></tr>
    <tr><td>103</td><td>20001</td><td>3</td><td className="max-w-[200px] truncate" title="数据字典表在哪里配置？">数据字典表在哪里配置？</td><td><StatusTag value="pending" /></td><td>2024-11-17 09:12:05</td></tr>
  </>;
}

function VideoRows() {
  return <>
    <tr><td>501</td><td>智能问数新手引导</td><td>/videos/guide.mp4</td><td>03:45</td><td>1,240</td><td><StatusTag value="active" /></td></tr>
    <tr><td>502</td><td>ER图表关联教程</td><td>/videos/er_tutorial.mp4</td><td>07:20</td><td>890</td><td><StatusTag value="active" /></td></tr>
  </>;
}

function SchemaPane({ tableId }: { tableId: string }) {
  return (
    <div className="flex flex-col p-3 h-full overflow-auto">
      <span className="text-[10px] text-gray-400 block mb-1">字段列表 (Schema Structure) &gt; {tableId}</span>
      <table className="hifi-table">
        <thead><tr><th>字段名</th><th>类型</th><th>约束</th><th>可空</th><th>默认值</th><th>注释</th></tr></thead>
        <tbody>
          <tr><td>id</td><td className="text-blue-600 font-mono">bigint(20) unsigned</td><td><span className="hifi-constraint-badge pk">PK</span></td><td>否</td><td>—</td><td>主键 ID</td></tr>
          <tr><td>tenant_id</td><td className="text-blue-600 font-mono">bigint(20) unsigned</td><td><span className="hifi-constraint-badge index">INDEX</span></td><td>否</td><td>—</td><td>租户 ID</td></tr>
          <tr><td>name</td><td className="text-blue-600 font-mono">varchar(100)</td><td>—</td><td>否</td><td>—</td><td>名称</td></tr>
        </tbody>
      </table>
    </div>
  );
}

function ErPane({ tableId }: { tableId: string }) {
  return (
    <div className="h-full w-full bg-slate-50 relative overflow-hidden flex flex-col p-4">
      <span className="text-[10px] text-gray-400 block mb-2">ER 关系图 &gt; {tableId}</span>
      <div className="flex-1 relative border border-slate-200 bg-white rounded-xl shadow-inner overflow-hidden">
        <div className="absolute bg-white border border-slate-300 rounded shadow-sm text-[8px] z-10 w-[95px]" style={{ left: "20px", top: "20px" }}>
          <div className="bg-[#EEF2FF] border-b border-slate-200 px-1.5 py-0.5 font-bold flex justify-between"><span>{tableId}</span></div>
          <div className="p-1 leading-normal text-slate-600 font-mono"><div><strong className="text-slate-800">id</strong> (PK)</div><div>tenant_id</div><div>status</div><div>created_at</div></div>
        </div>
        <div className="absolute bg-white border border-slate-300 rounded shadow-sm text-[8px] z-10 w-[95px]" style={{ left: "180px", top: "20px" }}>
          <div className="bg-[#FFF7ED] border-b border-slate-200 px-1.5 py-0.5 font-bold flex justify-between"><span>id_users</span></div>
          <div className="p-1 leading-normal text-slate-600 font-mono"><div><strong className="text-slate-800">id</strong> (PK)</div><div>tenant_id</div><div>account</div></div>
        </div>
        <svg className="absolute inset-0 w-full h-full pointer-events-none"><path d="M115 65 C 145 65, 150 65, 180 65" stroke="#94A3B8" strokeWidth="1.5" fill="none" strokeDasharray="4 2" /></svg>
        <div className="hifi-er-zoom-controls"><div className="hifi-er-zoom-btn"><ZoomIn size={12} /></div><div className="hifi-er-zoom-btn"><ZoomOut size={12} /></div><div className="hifi-er-zoom-btn"><Maximize2 size={12} /></div></div>
      </div>
    </div>
  );
}

function QueriesPane({ tableId, onOpenSqlConsole }: { tableId: string; onOpenSqlConsole: () => void }) {
  return <div className="p-4 flex flex-col gap-3">{[`SELECT * FROM ${tableId} LIMIT 100;`, `SELECT status, COUNT(*) FROM ${tableId} GROUP BY status;`].map((sql, idx) => <div key={sql} className="border border-slate-200 rounded-lg p-3 bg-white hover:border-indigo-300 cursor-pointer" onClick={onOpenSqlConsole}><div className="font-semibold text-[11px] text-slate-800 mb-2">样例查询 {idx + 1}</div><pre className="text-[10px] font-mono text-blue-600 whitespace-pre-wrap">{sql}</pre></div>)}</div>;
}

function HistoryPane({ tableId }: { tableId: string }) {
  return <div className="p-4 flex flex-col gap-2 text-[11px] text-slate-600"><div className="border border-slate-200 rounded-lg p-3 bg-white">今天 14:12 预览了 {tableId}</div><div className="border border-slate-200 rounded-lg p-3 bg-white">今天 13:58 查看字段结构</div><div className="border border-slate-200 rounded-lg p-3 bg-white">昨天 18:20 作为问数上下文</div></div>;
}
