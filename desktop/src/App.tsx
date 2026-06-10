import { useMemo, useState, type KeyboardEvent, type MouseEvent } from "react";
import { ArrowUpDown, ChevronDown, ChevronRight, Code, Columns3, Copy, Database, Download, FileText, Filter, GitMerge, Info, Layers, Play, Plus, RefreshCw, Search, Send, Sparkles, Table2, Terminal, Trash2, X } from "lucide-react";
import "./App.css";

type TabType = "ask" | "table" | "sql" | "multi" | "result";
type TableSubTab = "preview" | "schema" | "relations" | "queries" | "history";
type DrawerType = "props" | "ai";
type MenuType = "database" | "schema" | "table" | "multi-table";
type TableMeta = { name: string; comment: string; module: string };
type Tab = { id: string; title: string; type: TabType; tableName?: string; tables?: string[]; query?: string; sql?: string };
type MenuState = { visible: boolean; x: number; y: number; type: MenuType; target: string };

const SOURCE = { name: "prod-mysql", version: "MySQL 8.0", schema: "小红书数据" };
const MODULES: { name: string; tables: TableMeta[] }[] = [
  { name: "账号模块", tables: [{ name: "id_users", comment: "用户基础信息", module: "账号模块" }, { name: "id_organizations", comment: "组织架构信息", module: "账号模块" }, { name: "id_departments", comment: "部门信息", module: "账号模块" }] },
  { name: "内容模块", tables: [{ name: "note_infos", comment: "笔记信息", module: "内容模块" }, { name: "video_infos", comment: "视频信息", module: "内容模块" }] },
  { name: "互动模块", tables: [{ name: "comment_infos", comment: "评论数据", module: "互动模块" }, { name: "like_infos", comment: "点赞数据", module: "互动模块" }, { name: "favorite_infos", comment: "收藏数据", module: "互动模块" }] },
  { name: "流量模块", tables: [{ name: "video_watch_records", comment: "视频观看记录", module: "流量模块" }] },
  { name: "配置表", tables: [{ name: "config_system", comment: "系统配置", module: "配置表" }, { name: "config_dict", comment: "数据字典", module: "配置表" }] }
];
const ALL_TABLES = MODULES.flatMap((m) => m.tables);
const TABLE_ROWS: Record<string, Record<string, string | number>[]> = {
  id_users: [
    { id: 1, tenant_id: 10001, name: "张三", account: "zhangsan", status: "active", created_at: "2024-11-16 10:23:45" },
    { id: 2, tenant_id: 10001, name: "李四", account: "lisi", status: "active", created_at: "2024-11-16 10:23:45" },
    { id: 3, tenant_id: 10002, name: "王五", account: "wangwu", status: "inactive", created_at: "2024-11-16 10:23:45" },
    { id: 4, tenant_id: 10002, name: "赵六", account: "zhaoliu", status: "pending", created_at: "2024-11-16 10:23:45" }
  ],
  comment_infos: [
    { id: 101, note_id: 20001, user_id: 1, content: "这个系统界面太漂亮了！", status: "active", created_at: "2024-11-17 08:32:00" },
    { id: 102, note_id: 20002, user_id: 2, content: "同意，设计细节直接拉满。", status: "active", created_at: "2024-11-17 08:45:10" },
    { id: 103, note_id: 20001, user_id: 3, content: "数据字典表在哪里配置？", status: "pending", created_at: "2024-11-17 09:12:05" }
  ],
  video_infos: [
    { id: 501, title: "智能问数新手引导", url: "/videos/guide.mp4", duration: "03:45", play_count: 1240, status: "active" },
    { id: 502, title: "ER 图表关联教程", url: "/videos/er.mp4", duration: "07:20", play_count: 890, status: "active" }
  ]
};
const SCHEMA_ROWS = [
  ["id", "bigint unsigned", "PK", "否", "—", "主键 ID"],
  ["tenant_id", "bigint unsigned", "INDEX", "否", "—", "租户 ID"],
  ["name", "varchar(100)", "—", "否", "—", "名称"],
  ["status", "enum", "—", "否", "'active'", "状态"],
  ["created_at", "datetime", "INDEX", "否", "CURRENT_TIMESTAMP", "创建时间"]
];
const DEFAULT_SQL = "SELECT\n  u.name,\n  COUNT(c.id) AS comment_count\nFROM id_users u\nLEFT JOIN comment_infos c ON u.id = c.user_id\nGROUP BY u.id, u.name\nORDER BY comment_count DESC;";
const RESULT_SQL = "SELECT\n  DATE(created_at) AS date,\n  COUNT(id) AS total_comments\nFROM comment_infos\nWHERE created_at >= CURDATE() - INTERVAL 7 DAY\nGROUP BY DATE(created_at)\nORDER BY date;";

function meta(name?: string) { return ALL_TABLES.find((t) => t.name === name); }
function rows(name: string) { return TABLE_ROWS[name] ?? TABLE_ROWS.id_users; }
function cols(name: string) { return Object.keys(rows(name)[0] ?? {}); }
function Status({ value }: { value: string | number }) {
  const text = String(value);
  return ["active", "inactive", "pending"].includes(text) ? <span className={`status ${text}`}><i />{text}</span> : <>{text}</>;
}
function TabIcon({ type }: { type: TabType }) {
  if (type === "ask") return <Sparkles size={14} />;
  if (type === "table") return <Table2 size={14} />;
  if (type === "sql") return <Terminal size={14} />;
  if (type === "multi") return <GitMerge size={14} />;
  return <Layers size={14} />;
}

export default function App() {
  const [q, setQ] = useState("");
  const [ask, setAsk] = useState("帮我查一下最近 7 天新增用户数量趋势");
  const [tabs, setTabs] = useState<Tab[]>([{ id: "ask", title: "问数工作台", type: "ask" }]);
  const [active, setActive] = useState("ask");
  const [selected, setSelected] = useState<string[]>([]);
  const [ctxTables, setCtxTables] = useState<string[]>([]);
  const [subtabs, setSubtabs] = useState<Record<string, TableSubTab>>({});
  const [sqlDrafts, setSqlDrafts] = useState<Record<string, string>>({});
  const [ran, setRan] = useState<Record<string, boolean>>({});
  const [drawer, setDrawer] = useState<{ open: boolean; type: DrawerType }>({ open: false, type: "props" });
  const [menu, setMenu] = useState<MenuState>({ visible: false, x: 0, y: 0, type: "table", target: "" });
  const [toast, setToast] = useState<string | null>(null);
  const tab = tabs.find((t) => t.id === active) ?? tabs[0];
  const filtered = useMemo(() => MODULES.map((m) => ({ ...m, tables: m.tables.filter((t) => `${t.name} ${t.comment}`.toLowerCase().includes(q.toLowerCase())) })).filter((m) => m.tables.length), [q]);
  const notify = (s: string) => { setToast(s); window.setTimeout(() => setToast(null), 2200); };
  const closeMenu = () => setMenu((m) => ({ ...m, visible: false }));
  const openDrawer = (type: DrawerType) => setDrawer((d) => ({ open: !(d.open && d.type === type), type }));
  const addCtx = (name: string) => { setCtxTables((p) => p.includes(name) ? p : [...p, name]); notify(`已将 ${name} 加入问数上下文`); };
  const openTable = (name: string, sub: TableSubTab = "preview") => { const id = `table:${name}`; setTabs((p) => p.some((t) => t.id === id) ? p : [...p, { id, title: name, type: "table", tableName: name }]); setSubtabs((p) => ({ ...p, [name]: sub })); setSelected([name]); setActive(id); };
  const openSql = (sql = DEFAULT_SQL) => { const id = `sql:${Date.now()}`; setTabs((p) => [...p, { id, title: "SQL 控制台", type: "sql", sql }]); setSqlDrafts((p) => ({ ...p, [id]: sql })); setActive(id); notify("已打开 SQL 控制台"); };
  const openMulti = (names: string[]) => { if (!names.length) return; const id = `multi:${Date.now()}`; setTabs((p) => [...p, { id, title: `联合 Workspace (${names.length})`, type: "multi", tables: names }]); setActive(id); notify("已创建联合 Workspace"); };
  const openResult = (query: string) => { if (!query.trim()) return; const id = `result:${Date.now()}`; setTabs((p) => [...p, { id, title: "问数结果", type: "result", query }]); setActive(id); setAsk(""); };
  const closeTab = (e: MouseEvent, id: string) => { e.stopPropagation(); if (id === "ask") return; const next = tabs.filter((t) => t.id !== id); setTabs(next); if (active === id) setActive(next[next.length - 1]?.id ?? "ask"); };
  const rightClick = (e: MouseEvent, type: MenuType, target: string) => { e.preventDefault(); e.stopPropagation(); if (type === "table" && selected.length > 1 && selected.includes(target)) setMenu({ visible: true, x: e.clientX, y: e.clientY, type: "multi-table", target }); else { if (type === "table") setSelected([target]); setMenu({ visible: true, x: e.clientX, y: e.clientY, type, target }); } };
  const selectTable = (e: MouseEvent, name: string) => { if (e.ctrlKey || e.metaKey) setSelected((p) => p.includes(name) ? p.filter((x) => x !== name) : [...p, name]); else openTable(name); };
  const askKey = (e: KeyboardEvent<HTMLTextAreaElement>) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); openResult(ask); } };

  return <div className="databox-app" onClick={closeMenu}>
    <header className="app-header"><div><b>数据库可视化 + 智能问数</b><span>DataBox Workspace-first Prototype</span></div><nav><button className="active">工作台</button><button>数据库</button><button>智能问数</button><button>数据源管理</button></nav><div className="header-actions"><button><Search size={17} /></button><button><RefreshCw size={17} /></button><i>A</i></div></header>
    <main className="app-body">
      <aside className="sidebar"><div className="side-title"><b>数据源</b><button onClick={() => notify("数据源树已刷新")}><RefreshCw size={14} /></button></div><div className="source" onContextMenu={(e) => rightClick(e, "database", SOURCE.name)}><Database size={18} /><div><b>{SOURCE.name}</b><span>{SOURCE.version}</span></div><ChevronDown size={15} /></div><label className="tree-search"><Search size={14} /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="搜索表或字段" /></label><div className="tree"><div className="node muted"><ChevronRight size={13} /><Database size={14} />information_schema</div><div className="node schema" onContextMenu={(e) => rightClick(e, "schema", SOURCE.schema)}><ChevronDown size={13} /><Database size={14} />{SOURCE.schema}</div>{filtered.map((m) => <div key={m.name}><div className="node module"><ChevronDown size={12} />{m.name}</div>{m.tables.map((t) => <div key={t.name} className={`node table ${selected.includes(t.name) ? "selected" : ""}`} draggable title={t.comment} onClick={(e) => selectTable(e, t.name)} onDoubleClick={() => openTable(t.name)} onDragStart={(e) => e.dataTransfer.setData("text/plain", t.name)} onContextMenu={(e) => rightClick(e, "table", t.name)}><FileText size={13} /><span>{t.name}</span></div>)}</div>)}</div></aside>
      <section className="workspace"><div className="tabbar"><div className="tabs">{tabs.map((t) => <button key={t.id} className={`tab ${t.id === active ? "active" : ""}`} onClick={() => setActive(t.id)}><TabIcon type={t.type} /><span>{t.title}</span>{t.id !== "ask" && <em onClick={(e) => closeTab(e, t.id)}><X size={12} /></em>}</button>)}<button className="new-tab" onClick={() => openSql()}><Plus size={15} /></button></div><div className="drawer-actions"><button className={drawer.open && drawer.type === "props" ? "active" : ""} onClick={() => openDrawer("props")}><Info size={14} />属性</button><button className={drawer.open && drawer.type === "ai" ? "active" : ""} onClick={() => openDrawer("ai")}><Sparkles size={14} />AI 建议</button></div></div><div className="pane">{tab.type === "ask" && <Ask ask={ask} setAsk={setAsk} ctxTables={ctxTables} setCtxTables={setCtxTables} openResult={openResult} openTable={openTable} addCtx={addCtx} askKey={askKey} />}{tab.type === "table" && tab.tableName && <TablePane name={tab.tableName} sub={subtabs[tab.tableName] ?? "preview"} setSub={(s) => setSubtabs((p) => ({ ...p, [tab.tableName!]: s }))} openSql={openSql} notify={notify} />}{tab.type === "sql" && <SqlPane sql={sqlDrafts[tab.id] ?? tab.sql ?? DEFAULT_SQL} setSql={(s) => setSqlDrafts((p) => ({ ...p, [tab.id]: s }))} ran={Boolean(ran[tab.id])} run={() => { setRan((p) => ({ ...p, [tab.id]: true })); notify("SQL 执行成功，返回 3 行"); }} />}{tab.type === "multi" && <MultiPane tables={tab.tables ?? []} openResult={openResult} openSql={openSql} />}{tab.type === "result" && <ResultPane query={tab.query ?? ""} openSql={openSql} />}</div></section>
      {drawer.open && <Drawer type={drawer.type} tab={tab} ctxTables={ctxTables} close={() => setDrawer((d) => ({ ...d, open: false }))} />}
    </main>
    {menu.visible && <Menu state={menu} selected={selected} openTable={openTable} openSql={openSql} openMulti={openMulti} addCtx={addCtx} setCtxTables={setCtxTables} hide={closeMenu} notify={notify} />}
    {toast && <div className="toast"><Sparkles size={15} />{toast}</div>}
  </div>;
}

function Ask({ ask, setAsk, ctxTables, setCtxTables, openResult, openTable, addCtx, askKey }: { ask: string; setAsk: (s: string) => void; ctxTables: string[]; setCtxTables: (s: string[]) => void; openResult: (q: string) => void; openTable: (n: string) => void; addCtx: (n: string) => void; askKey: (e: KeyboardEvent<HTMLTextAreaElement>) => void }) {
  const rec = ["分析近 7 天评论数据趋势", "查询活跃用户 Top 10", "统计本月新增笔记数量", "检查 comment_infos 是否有异常数据"];
  return <div className="ask-page"><section className="hero"><h1>你好，开始你的<span>智能问数之旅</span></h1><p>左侧选择数据对象，中间打开表、SQL、问数结果；右侧只在需要时作为上下文抽屉。</p><div className="drop" onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); const t = e.dataTransfer.getData("text/plain"); if (t) addCtx(t); }}><GitMerge size={15} /><b>问数上下文</b>{ctxTables.length ? <div className="chips">{ctxTables.map((t) => <button key={t} onClick={() => setCtxTables(ctxTables.filter((x) => x !== t))}>{t}<X size={11} /></button>)}<button className="clear" onClick={() => setCtxTables([])}>清空</button></div> : <span>拖拽左侧表到这里，或右键表选择“作为问数上下文”</span>}</div><div className="askbox"><textarea value={ask} onChange={(e) => setAsk(e.target.value)} onKeyDown={askKey} /><button onClick={() => openResult(ask)}><Send size={18} /></button></div><small>Ctrl / Cmd + Enter 发送</small></section><Block title="推荐提问"><div className="cards four">{rec.map((r) => <button key={r} onClick={() => setAsk(r)}><Sparkles size={18} /><b>{r}</b><em>数据分析</em></button>)}</div></Block><Block title="最近访问"><div className="cards five">{["id_users", "comment_infos", "video_watch_records", "note_infos", "id_organizations"].map((t) => <button key={t} onClick={() => openTable(t)}><b>{t}</b><span>{meta(t)?.module}</span></button>)}</div></Block></div>;
}
function Block({ title, children }: { title: string; children: React.ReactNode }) { return <section className="block"><div><h2>{title}</h2><button>查看更多</button></div>{children}</section>; }
function TablePane({ name, sub, setSub, openSql, notify }: { name: string; sub: TableSubTab; setSub: (s: TableSubTab) => void; openSql: (s?: string) => void; notify: (s: string) => void }) {
  return <div className="table-page"><header><small>{SOURCE.name} / {SOURCE.schema} / {meta(name)?.module}</small><h2>{name}</h2><p>{meta(name)?.comment ?? "表数据预览与结构分析"}</p><div><button onClick={() => openSql(`SELECT * FROM ${name} LIMIT 100;`)}><Terminal size={15} />SQL 查询</button><button onClick={() => notify("表元数据已刷新")}><RefreshCw size={15} />刷新</button></div></header><nav>{(["preview", "schema", "relations", "queries", "history"] as TableSubTab[]).map((s) => <button key={s} className={sub === s ? "active" : ""} onClick={() => setSub(s)}>{{ preview: "数据预览", schema: "字段结构", relations: "关系图", queries: "样例查询", history: "使用记录" }[s]}</button>)}</nav><main>{sub === "preview" && <Preview name={name} openSql={openSql} notify={notify} />}{sub === "schema" && <Schema />}{sub === "relations" && <Relations name={name} />}{sub === "queries" && <Samples name={name} openSql={openSql} />}{sub === "history" && <div className="history">{["今天 14:12 预览表数据", "今天 13:58 生成字段结构", "昨天 18:20 作为问数上下文"].map((x) => <p key={x}><FileText size={14} /><b>{name}</b><span>{x}</span></p>)}</div>}</main></div>;
}
function Preview({ name, openSql, notify }: { name: string; openSql: (s?: string) => void; notify: (s: string) => void }) { const columns = cols(name); return <div className="data-panel"><div className="toolbar"><span><button onClick={() => notify("数据预览已刷新")}><RefreshCw size={14} />刷新</button><button><Filter size={14} />筛选</button><button><ArrowUpDown size={14} />排序</button><button><Download size={14} />导出</button></span><button onClick={() => openSql(`SELECT * FROM ${name} LIMIT 100;`)}><Code size={14} />在 SQL 控制台打开</button></div><div className="table-scroll"><table><thead><tr>{columns.map((c) => <th key={c}>{c}</th>)}</tr></thead><tbody>{rows(name).map((r, i) => <tr key={i}>{columns.map((c) => <td key={c}><Status value={r[c] ?? "NULL"} /></td>)}</tr>)}</tbody></table></div><footer><span>共 12,345 条</span><span>1 / 1235</span><select defaultValue="10"><option>10 条/页</option><option>20 条/页</option></select></footer></div>; }
function Schema() { return <div className="data-panel pad"><table><thead><tr><th>字段名</th><th>类型</th><th>约束</th><th>可空</th><th>默认值</th><th>注释</th></tr></thead><tbody>{SCHEMA_ROWS.map((r) => <tr key={r[0]}>{r.map((x, i) => <td key={i}>{i === 2 && x !== "—" ? <em className="constraint">{x}</em> : x}</td>)}</tr>)}</tbody></table></div>; }
function Relations({ name }: { name: string }) { return <div className="relations"><div className="er primary" style={{ left: 80, top: 70 }}><b>{name}</b><span>id PK</span><span>user_id FK</span><span>created_at</span></div><div className="er" style={{ left: 360, top: 70 }}><b>id_users</b><span>id PK</span><span>tenant_id</span><span>account</span></div><div className="er" style={{ left: 360, top: 250 }}><b>id_organizations</b><span>id PK</span><span>tenant_id</span><span>name</span></div><svg><path d="M220 125 C280 125 300 125 360 125" /><path d="M440 170 C440 215 440 220 440 250" /></svg></div>; }
function Samples({ name, openSql }: { name: string; openSql: (s?: string) => void }) { return <div className="samples">{[`SELECT * FROM ${name} LIMIT 100;`, `SELECT DATE(created_at), COUNT(*) FROM ${name} GROUP BY DATE(created_at);`, `SELECT status, COUNT(*) FROM ${name} GROUP BY status;`].map((sql) => <button key={sql} onClick={() => openSql(sql)}><b>样例查询</b><pre>{sql}</pre></button>)}</div>; }
function SqlPane({ sql, setSql, ran, run }: { sql: string; setSql: (s: string) => void; ran: boolean; run: () => void }) { return <div className="sql-page"><div className="sqlbar"><span>SQL Console / {SOURCE.name}</span><button onClick={run}><Play size={15} />运行 F9</button></div><textarea value={sql} onChange={(e) => setSql(e.target.value)} spellCheck={false} /><section><nav><button className="active">查询结果 {ran ? "(3行)" : ""}</button><button>消息日志</button><button>AI 解释</button></nav>{ran ? <table><thead><tr><th>name</th><th>comment_count</th></tr></thead><tbody><tr><td>张三</td><td>1,432</td></tr><tr><td>李四</td><td>980</td></tr><tr><td>王五</td><td>412</td></tr></tbody></table> : <div className="empty">点击“运行”执行上方 SQL 并查看输出结果。</div>}</section></div>; }
function MultiPane({ tables, openResult, openSql }: { tables: string[]; openResult: (q: string) => void; openSql: (s?: string) => void }) { return <div className="multi-page"><div className="multi-head"><GitMerge size={22} /><div><b>联合 Workspace</b><span>已绑定 {tables.length} 张表：{tables.join("，")}</span></div></div><div className="multi-cards"><button onClick={() => openResult(`分析 ${tables.join("、")} 的关联关系`)}><Layers size={18} /><b>分析表关联拓扑</b><span>识别主外键、逻辑外键和常见 Join 路径。</span></button><button onClick={() => openResult(`统计 ${tables.join("、")} 最近一个月的联合活动数据量`)}><Sparkles size={18} /><b>联合趋势统计</b><span>生成多表统计 SQL、图表与结论。</span></button><button onClick={() => openSql(`SELECT *\nFROM ${tables[0] ?? "id_users"} t1\nLEFT JOIN ${tables[1] ?? "comment_infos"} t2 ON t1.id = t2.user_id\nLIMIT 100;`)}><Terminal size={18} /><b>打开联合 SQL</b><span>生成 SQL 草稿。</span></button></div></div>; }
function ResultPane({ query, openSql }: { query: string; openSql: (s?: string) => void }) { return <div className="result-page"><header><span>智能问数分析结果</span><h2>“{query}”</h2></header><article><h3>关键结论</h3><p>最近 7 天新增用户整体呈上升趋势，11-15 达到阶段峰值。建议继续按组织、用户状态进行拆分分析。</p></article><article><h3>近 7 天新增用户趋势</h3><svg viewBox="0 0 640 220"><path className="grid" d="M40 40H600M40 90H600M40 140H600M40 190H600" /><path className="area" d="M40 170 C110 130 150 80 220 105 C290 135 330 60 400 92 C480 120 520 35 600 70 L600 190 L40 190 Z" /><path className="line" d="M40 170 C110 130 150 80 220 105 C290 135 330 60 400 92 C480 120 520 35 600 70" /></svg></article><article className="sql-card"><div><h3>生成的 SQL</h3><button onClick={() => openSql(RESULT_SQL)}><Terminal size={14} />在 SQL 控制台打开</button></div><pre>{RESULT_SQL}</pre></article></div>; }
function Drawer({ type, tab, ctxTables, close }: { type: DrawerType; tab: Tab; ctxTables: string[]; close: () => void }) { return <aside className="drawer"><header><b>{type === "props" ? "对象属性" : "AI 建议"}</b><button onClick={close}><X size={15} /></button></header>{type === "props" ? <main><p><span>当前 Tab</span><b>{tab.title}</b></p><p><span>类型</span><b>{tab.type}</b></p><p><span>数据源</span><b>{SOURCE.name}</b></p><p><span>上下文表</span><b>{ctxTables.length} 张</b></p></main> : <main className="suggestions"><button>解释当前表字段含义</button><button>生成常用分析 SQL</button><button>检查数据质量问题</button><button>根据结果生成图表</button></main>}</aside>; }
function Menu({ state, selected, openTable, openSql, openMulti, addCtx, setCtxTables, hide, notify }: { state: MenuState; selected: string[]; openTable: (n: string, s?: TableSubTab) => void; openSql: (s?: string) => void; openMulti: (n: string[]) => void; addCtx: (n: string) => void; setCtxTables: (t: string[]) => void; hide: () => void; notify: (s: string) => void }) { const run = (f: () => void) => { f(); hide(); }; return <div className="menu" style={{ left: state.x, top: state.y }} onClick={(e) => e.stopPropagation()}>{state.type === "database" && <><button onClick={() => run(() => openSql())}><Terminal size={14} />打开 SQL 控制台</button><button onClick={() => run(() => notify("连接测试成功"))}><Info size={14} />测试连接</button><button onClick={() => run(() => notify("数据源已刷新"))}><RefreshCw size={14} />刷新</button></>}{state.type === "schema" && <><button onClick={() => run(() => openSql())}><Terminal size={14} />新建 SQL Console</button><button onClick={() => run(() => openTable("id_users", "schema"))}><Columns3 size={14} />查看表结构</button><button onClick={() => run(() => openTable("id_users", "relations"))}><GitMerge size={14} />生成 ER 图</button></>}{state.type === "table" && <><button onClick={() => run(() => openTable(state.target, "preview"))}><Table2 size={14} />预览表数据</button><button onClick={() => run(() => openTable(state.target, "schema"))}><Columns3 size={14} />查看字段结构</button><button onClick={() => run(() => openSql(`SELECT * FROM ${state.target} LIMIT 100;`))}><Terminal size={14} />打开 SQL 控制台</button><button onClick={() => run(() => addCtx(state.target))}><Sparkles size={14} />作为问数上下文</button><button onClick={() => run(() => openTable(state.target, "relations"))}><GitMerge size={14} />生成表级 ER 图</button><hr /><button onClick={() => run(() => navigator.clipboard.writeText(state.target))}><Copy size={14} />复制物理表名</button><button className="danger" onClick={() => run(() => window.confirm(`确认删除 ${state.target}？`) && notify(`已删除 ${state.target}`))}><Trash2 size={14} />删除表</button></>}{state.type === "multi-table" && <><button onClick={() => run(() => openMulti(selected))}><GitMerge size={14} />作为联合 Workspace 打开</button><button onClick={() => run(() => setCtxTables(selected))}><Sparkles size={14} />基于多表智能问数</button><button onClick={() => run(() => openTable(selected[0], "relations"))}><Layers size={14} />生成联合 ER 图</button></>}</div>; }
