import { useMemo, useState, type KeyboardEvent, type MouseEvent } from "react";
import {
  ArrowUpDown,
  ChevronDown,
  ChevronRight,
  Code,
  Columns3,
  Copy,
  Database,
  Download,
  FileText,
  Filter,
  GitMerge,
  Info,
  Layers,
  Play,
  Plus,
  RefreshCw,
  Search,
  Send,
  Sparkles,
  Table2,
  Terminal,
  Trash2,
  X,
} from "lucide-react";
import "./App.css";

type TabType = "ask" | "table" | "sql" | "multi" | "result";
type TableSubTab = "preview" | "schema" | "relations" | "queries" | "history";
type DrawerType = "props" | "ai" | "context";
type ContextMenuType = "database" | "schema" | "table" | "multi-table";

type WorkspaceTab = {
  id: string;
  title: string;
  type: TabType;
  tableName?: string;
  tables?: string[];
  query?: string;
  sql?: string;
};

type TableMeta = {
  name: string;
  comment: string;
  module: string;
};

type ContextMenuState = {
  visible: boolean;
  x: number;
  y: number;
  type: ContextMenuType;
  target: string;
};

const DATA_SOURCE = {
  name: "prod-mysql",
  version: "MySQL 8.0",
  schema: "小红书数据",
};

const MODULES: { name: string; tables: TableMeta[] }[] = [
  {
    name: "账号模块",
    tables: [
      { name: "id_users", comment: "用户基础信息", module: "账号模块" },
      { name: "id_organizations", comment: "组织架构信息", module: "账号模块" },
      { name: "id_departments", comment: "部门信息", module: "账号模块" },
    ],
  },
  {
    name: "内容模块",
    tables: [
      { name: "note_infos", comment: "笔记信息", module: "内容模块" },
      { name: "video_infos", comment: "视频信息", module: "内容模块" },
    ],
  },
  {
    name: "互动模块",
    tables: [
      { name: "comment_infos", comment: "评论数据", module: "互动模块" },
      { name: "like_infos", comment: "点赞数据", module: "互动模块" },
      { name: "favorite_infos", comment: "收藏数据", module: "互动模块" },
    ],
  },
  {
    name: "流量模块",
    tables: [
      { name: "video_watch_records", comment: "视频观看记录", module: "流量模块" },
    ],
  },
  {
    name: "配置表",
    tables: [
      { name: "config_system", comment: "系统配置", module: "配置表" },
      { name: "config_dict", comment: "数据字典", module: "配置表" },
    ],
  },
];

const RECOMMENDED_QUESTIONS = [
  { icon: Sparkles, title: "分析近 7 天评论数据趋势", tag: "数据分析" },
  { icon: Table2, title: "查询活跃用户 Top 10", tag: "用户分析" },
  { icon: FileText, title: "统计本月新增笔记数量", tag: "内容分析" },
  { icon: Search, title: "检查 comment_infos 是否有异常数据", tag: "数据治理" },
];

const TABLE_ROWS: Record<string, Record<string, string | number>[]> = {
  id_users: [
    { id: 1, tenant_id: 10001, name: "张三", account: "zhangsan", status: "active", created_at: "2024-11-16 10:23:45" },
    { id: 2, tenant_id: 10001, name: "李四", account: "lisi", status: "active", created_at: "2024-11-16 10:23:45" },
    { id: 3, tenant_id: 10002, name: "王五", account: "wangwu", status: "inactive", created_at: "2024-11-16 10:23:45" },
    { id: 4, tenant_id: 10002, name: "赵六", account: "zhaoliu", status: "active", created_at: "2024-11-16 10:23:45" },
    { id: 5, tenant_id: 10003, name: "孙七", account: "sunqi", status: "active", created_at: "2024-11-16 10:23:45" },
    { id: 6, tenant_id: 10003, name: "周八", account: "zhouba", status: "pending", created_at: "2024-11-16 10:23:45" },
  ],
  comment_infos: [
    { id: 101, note_id: 20001, user_id: 1, content: "这个系统界面太漂亮了！", status: "active", created_at: "2024-11-17 08:32:00" },
    { id: 102, note_id: 20002, user_id: 2, content: "同意，设计细节直接拉满。", status: "active", created_at: "2024-11-17 08:45:10" },
    { id: 103, note_id: 20001, user_id: 3, content: "数据字典表在哪里配置？", status: "pending", created_at: "2024-11-17 09:12:05" },
  ],
  video_infos: [
    { id: 501, title: "智能问数新手引导", url: "/videos/guide.mp4", duration: "03:45", play_count: 1240, status: "active" },
    { id: 502, title: "ER 图表关联教程", url: "/videos/er_tutorial.mp4", duration: "07:20", play_count: 890, status: "active" },
  ],
};

const DEFAULT_ROWS = TABLE_ROWS.id_users;

const SCHEMA_ROWS: Record<string, { name: string; type: string; constraint: string; nullable: string; defaultValue: string; comment: string }[]> = {
  comment_infos: [
    { name: "id", type: "bigint(20) unsigned", constraint: "PK", nullable: "否", defaultValue: "—", comment: "主键 ID" },
    { name: "note_id", type: "bigint(20) unsigned", constraint: "INDEX", nullable: "否", defaultValue: "—", comment: "关联笔记 ID" },
    { name: "user_id", type: "bigint(20) unsigned", constraint: "INDEX", nullable: "否", defaultValue: "—", comment: "发布评论用户 ID" },
    { name: "content", type: "text", constraint: "—", nullable: "否", defaultValue: "—", comment: "评论内容" },
    { name: "status", type: "enum('active','pending','spam')", constraint: "—", nullable: "否", defaultValue: "'active'", comment: "评论状态" },
  ],
  id_users: [
    { name: "id", type: "bigint(20) unsigned", constraint: "PK", nullable: "否", defaultValue: "—", comment: "主键 ID" },
    { name: "tenant_id", type: "bigint(20) unsigned", constraint: "INDEX", nullable: "否", defaultValue: "—", comment: "租户 ID" },
    { name: "name", type: "varchar(100)", constraint: "—", nullable: "否", defaultValue: "—", comment: "用户姓名" },
    { name: "account", type: "varchar(50)", constraint: "UNIQUE", nullable: "否", defaultValue: "—", comment: "账号" },
    { name: "status", type: "enum('active','inactive','pending')", constraint: "—", nullable: "否", defaultValue: "'active'", comment: "状态" },
    { name: "created_at", type: "datetime", constraint: "—", nullable: "否", defaultValue: "CURRENT_TIMESTAMP", comment: "创建时间" },
  ],
};

const DEFAULT_SQL = `SELECT
  u.name,
  COUNT(c.id) AS comment_count
FROM id_users u
LEFT JOIN comment_infos c ON u.id = c.user_id
GROUP BY u.id, u.name
ORDER BY comment_count DESC;`;

const GENERATED_SQL = `SELECT
  DATE(created_at) AS date,
  COUNT(id) AS total_comments
FROM comment_infos
WHERE created_at >= CURDATE() - INTERVAL 7 DAY
GROUP BY DATE(created_at)
ORDER BY date;`;

function getTableMeta(tableName?: string) {
  return MODULES.flatMap((module) => module.tables).find((table) => table.name === tableName);
}

function getRows(tableName: string) {
  return TABLE_ROWS[tableName] ?? DEFAULT_ROWS;
}

function getColumns(tableName: string) {
  return Object.keys(getRows(tableName)[0] ?? {}).map((key) => ({ key, label: key }));
}

function getSchemaRows(tableName: string) {
  return SCHEMA_ROWS[tableName] ?? SCHEMA_ROWS.id_users;
}

function StatusBadge({ value }: { value: string | number }) {
  const text = String(value);
  if (!["active", "inactive", "pending"].includes(text)) return <>{text}</>;
  return (
    <span className={`db-status ${text}`}>
      <span className="db-status-dot" />
      {text}
    </span>
  );
}

function TabIcon({ type }: { type: TabType }) {
  if (type === "ask") return <Sparkles size={14} />;
  if (type === "table") return <Table2 size={14} />;
  if (type === "sql") return <Terminal size={14} />;
  if (type === "multi") return <GitMerge size={14} />;
  return <Layers size={14} />;
}

export default function App() {
  const [treeSearch, setTreeSearch] = useState("");
  const [askValue, setAskValue] = useState("帮我查一下最近 7 天新增用户数量趋势");
  const [selectedTables, setSelectedTables] = useState<string[]>([]);
  const [contextTables, setContextTables] = useState<string[]>([]);
  const [tabs, setTabs] = useState<WorkspaceTab[]>([{ id: "ask", title: "问数工作台", type: "ask" }]);
  const [activeTabId, setActiveTabId] = useState("ask");
  const [tableSubTabs, setTableSubTabs] = useState<Record<string, TableSubTab>>({});
  const [sqlDrafts, setSqlDrafts] = useState<Record<string, string>>({});
  const [sqlResultVisible, setSqlResultVisible] = useState<Record<string, boolean>>({});
  const [drawer, setDrawer] = useState<{ open: boolean; type: DrawerType }>({ open: false, type: "props" });
  const [contextMenu, setContextMenu] = useState<ContextMenuState>({ visible: false, x: 0, y: 0, type: "table", target: "" });
  const [toast, setToast] = useState<string | null>(null);

  const activeTab = tabs.find((tab) => tab.id === activeTabId) ?? tabs[0];
  const filteredModules = useMemo(() => {
    const keyword = treeSearch.trim().toLowerCase();
    if (!keyword) return MODULES;
    return MODULES.map((module) => ({
      ...module,
      tables: module.tables.filter((table) => `${table.name} ${table.comment}`.toLowerCase().includes(keyword)),
    })).filter((module) => module.tables.length > 0);
  }, [treeSearch]);

  const showToast = (message: string) => {
    setToast(message);
    window.setTimeout(() => setToast(null), 2200);
  };

  const hideContextMenu = () => setContextMenu((prev) => ({ ...prev, visible: false }));

  const openDrawer = (type: DrawerType) => {
    setDrawer((prev) => ({ open: !(prev.open && prev.type === type), type }));
  };

  const openTableTab = (tableName: string, subTab: TableSubTab = "preview") => {
    const tabId = `table:${tableName}`;
    setTabs((prev) => (prev.some((tab) => tab.id === tabId) ? prev : [...prev, { id: tabId, title: tableName, type: "table", tableName }]));
    setTableSubTabs((prev) => ({ ...prev, [tableName]: subTab }));
    setActiveTabId(tabId);
    setSelectedTables([tableName]);
  };

  const openSqlConsole = (sql = DEFAULT_SQL) => {
    const tabId = `sql:${Date.now()}`;
    setTabs((prev) => [...prev, { id: tabId, title: "SQL 控制台", type: "sql", sql }]);
    setSqlDrafts((prev) => ({ ...prev, [tabId]: sql }));
    setActiveTabId(tabId);
    showToast("已打开 SQL 控制台");
  };

  const openMultiWorkspace = (tables: string[]) => {
    if (tables.length === 0) return;
    const tabId = `multi:${Date.now()}`;
    const title = `联合 Workspace (${tables.length})`;
    setTabs((prev) => [...prev, { id: tabId, title, type: "multi", tables }]);
    setActiveTabId(tabId);
    showToast(`已创建 ${tables.length} 张表的联合 Workspace`);
  };

  const openResultTab = (query: string) => {
    const trimmed = query.trim();
    if (!trimmed) return;
    const tabId = `result:${Date.now()}`;
    setTabs((prev) => [...prev, { id: tabId, title: "问数结果", type: "result", query: trimmed }]);
    setActiveTabId(tabId);
    setAskValue("");
  };

  const closeTab = (event: MouseEvent<HTMLButtonElement>, tabId: string) => {
    event.stopPropagation();
    if (tabId === "ask") return;
    setTabs((prev) => {
      const next = prev.filter((tab) => tab.id !== tabId);
      if (activeTabId === tabId) {
        const closedIndex = prev.findIndex((tab) => tab.id === tabId);
        setActiveTabId(next[Math.max(0, closedIndex - 1)]?.id ?? "ask");
      }
      return next;
    });
  };

  const handleTableClick = (event: MouseEvent<HTMLDivElement>, tableName: string) => {
    if (event.ctrlKey || event.metaKey) {
      setSelectedTables((prev) => (prev.includes(tableName) ? prev.filter((item) => item !== tableName) : [...prev, tableName]));
      return;
    }
    openTableTab(tableName);
  };

  const handleContextMenu = (event: MouseEvent, type: ContextMenuType, target: string) => {
    event.preventDefault();
    event.stopPropagation();
    if (type === "table" && selectedTables.length > 1 && selectedTables.includes(target)) {
      setContextMenu({ visible: true, x: event.clientX, y: event.clientY, type: "multi-table", target });
      return;
    }
    if (type === "table") setSelectedTables([target]);
    setContextMenu({ visible: true, x: event.clientX, y: event.clientY, type, target });
  };

  const addTableToAskContext = (tableName: string) => {
    setContextTables((prev) => (prev.includes(tableName) ? prev : [...prev, tableName]));
    showToast(`已将 ${tableName} 加入问数上下文`);
  };

  const submitAskByKeyboard = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      openResultTab(askValue);
    }
  };

  return (
    <div className="databox-app" onClick={hideContextMenu}>
      <header className="app-header">
        <div className="brand-area">
          <div className="brand-title">数据库可视化 + 智能问数</div>
          <div className="brand-subtitle">DataBox Workspace-first Prototype</div>
        </div>
        <nav className="top-tabs">
          <button className="top-tab active">工作台</button>
          <button className="top-tab">数据库</button>
          <button className="top-tab">智能问数</button>
          <button className="top-tab">数据源管理</button>
        </nav>
        <div className="header-actions">
          <button className="icon-button" title="搜索"><Search size={17} /></button>
          <button className="icon-button" title="刷新"><RefreshCw size={17} /></button>
          <div className="avatar">A</div>
        </div>
      </header>

      <main className="app-body">
        <aside className="datasource-sidebar">
          <div className="sidebar-title-row">
            <span className="panel-title">数据源</span>
            <button className="ghost-icon" onClick={() => showToast("数据源树已刷新")}> <RefreshCw size={14} /> </button>
          </div>

          <div className="source-card" onContextMenu={(event) => handleContextMenu(event, "database", DATA_SOURCE.name)}>
            <Database size={18} />
            <div className="source-info">
              <strong>{DATA_SOURCE.name}</strong>
              <span>{DATA_SOURCE.version}</span>
            </div>
            <ChevronDown size={16} />
          </div>

          <label className="tree-search">
            <Search size={14} />
            <input value={treeSearch} onChange={(event) => setTreeSearch(event.target.value)} placeholder="搜索表或字段" />
          </label>

          <div className="tree-scroll">
            <div className="tree-node muted"><ChevronRight size={13} /><Database size={14} /> information_schema</div>
            <div className="tree-node muted"><ChevronRight size={13} /><Database size={14} /> lindorm</div>
            <div className="tree-node schema" onContextMenu={(event) => handleContextMenu(event, "schema", DATA_SOURCE.schema)}>
              <ChevronDown size={13} /><Database size={14} /> {DATA_SOURCE.schema}
            </div>

            {filteredModules.map((module) => (
              <div className="tree-module" key={module.name}>
                <div className="tree-node module"><ChevronDown size={12} /> {module.name}</div>
                {module.tables.map((table) => {
                  const selected = selectedTables.includes(table.name);
                  return (
                    <div
                      key={table.name}
                      className={`tree-node table ${selected ? "selected" : ""}`}
                      draggable
                      title={table.comment}
                      onClick={(event) => handleTableClick(event, table.name)}
                      onDoubleClick={() => openTableTab(table.name)}
                      onDragStart={(event) => event.dataTransfer.setData("text/plain", table.name)}
                      onContextMenu={(event) => handleContextMenu(event, "table", table.name)}
                    >
                      <FileText size={13} />
                      <span>{table.name}</span>
                    </div>
                  );
                })}
              </div>
            ))}
          </div>
        </aside>

        <section className="workspace-shell">
          <div className="workspace-tabbar">
            <div className="workspace-tabs">
              {tabs.map((tab) => (
                <button key={tab.id} className={`workspace-tab ${tab.id === activeTabId ? "active" : ""}`} onClick={() => setActiveTabId(tab.id)}>
                  <TabIcon type={tab.type} />
                  <span>{tab.title}</span>
                  {tab.id !== "ask" && (
                    <span className="tab-close" onClick={(event) => closeTab(event as unknown as MouseEvent<HTMLButtonElement>, tab.id)}>
                      <X size={12} />
                    </span>
                  )}
                </button>
              ))}
              <button className="new-tab-button" onClick={() => openSqlConsole()} title="新建 SQL 控制台"><Plus size={15} /></button>
            </div>

            <div className="workspace-actions">
              <button className={`side-action ${drawer.open && drawer.type === "props" ? "active" : ""}`} onClick={() => openDrawer("props")}><Info size={14} />属性</button>
              <button className={`side-action ${drawer.open && drawer.type === "ai" ? "active" : ""}`} onClick={() => openDrawer("ai")}><Sparkles size={14} />AI建议</button>
            </div>
          </div>

          <div className="workspace-content">
            {activeTab.type === "ask" && (
              <AskWorkspace
                askValue={askValue}
                setAskValue={setAskValue}
                contextTables={contextTables}
                setContextTables={setContextTables}
                openResultTab={openResultTab}
                openTableTab={openTableTab}
                addTableToAskContext={addTableToAskContext}
                submitAskByKeyboard={submitAskByKeyboard}
              />
            )}
            {activeTab.type === "table" && activeTab.tableName && (
              <TableWorkspace
                tableName={activeTab.tableName}
                subTab={tableSubTabs[activeTab.tableName] ?? "preview"}
                setSubTab={(subTab) => setTableSubTabs((prev) => ({ ...prev, [activeTab.tableName!]: subTab }))}
                openSqlConsole={openSqlConsole}
                showToast={showToast}
              />
            )}
            {activeTab.type === "sql" && (
              <SqlWorkspace
                tabId={activeTab.id}
                sql={sqlDrafts[activeTab.id] ?? activeTab.sql ?? DEFAULT_SQL}
                setSql={(sql) => setSqlDrafts((prev) => ({ ...prev, [activeTab.id]: sql }))}
                resultVisible={Boolean(sqlResultVisible[activeTab.id])}
                runSql={() => {
                  setSqlResultVisible((prev) => ({ ...prev, [activeTab.id]: true }));
                  showToast("SQL 执行成功，返回 3 行");
                }}
              />
            )}
            {activeTab.type === "multi" && <MultiWorkspace tables={activeTab.tables ?? []} openResultTab={openResultTab} openSqlConsole={openSqlConsole} />}
            {activeTab.type === "result" && <ResultWorkspace query={activeTab.query ?? ""} openSqlConsole={openSqlConsole} />}
          </div>
        </section>

        {drawer.open && <ContextDrawer type={drawer.type} activeTab={activeTab} contextTables={contextTables} onClose={() => setDrawer((prev) => ({ ...prev, open: false }))} />}
      </main>

      {contextMenu.visible && (
        <ContextMenu
          state={contextMenu}
          selectedTables={selectedTables}
          openTableTab={openTableTab}
          openSqlConsole={openSqlConsole}
          openMultiWorkspace={openMultiWorkspace}
          addTableToAskContext={addTableToAskContext}
          setContextTables={setContextTables}
          hide={hideContextMenu}
          showToast={showToast}
        />
      )}

      {toast && <div className="toast"><Sparkles size={15} />{toast}</div>}
    </div>
  );
}

function AskWorkspace({
  askValue,
  setAskValue,
  contextTables,
  setContextTables,
  openResultTab,
  openTableTab,
  addTableToAskContext,
  submitAskByKeyboard,
}: {
  askValue: string;
  setAskValue: (value: string) => void;
  contextTables: string[];
  setContextTables: (value: string[]) => void;
  openResultTab: (query: string) => void;
  openTableTab: (tableName: string) => void;
  addTableToAskContext: (tableName: string) => void;
  submitAskByKeyboard: (event: KeyboardEvent<HTMLTextAreaElement>) => void;
}) {
  return (
    <div className="ask-workspace">
      <section className="hero-card">
        <div className="hero-pattern" />
        <h1>你好，开始你的<span>智能问数之旅</span></h1>
        <p>左侧选择数据对象，中间打开表、SQL、问数结果；AI 只在当前 Workspace 内辅助你。</p>

        <div
          className="context-dropzone"
          onDragOver={(event) => event.preventDefault()}
          onDrop={(event) => {
            event.preventDefault();
            const tableName = event.dataTransfer.getData("text/plain");
            if (tableName) addTableToAskContext(tableName);
          }}
        >
          <GitMerge size={15} />
          <strong>问数上下文</strong>
          {contextTables.length === 0 ? (
            <span>拖拽左侧表到这里，或右键表选择“作为问数上下文”</span>
          ) : (
            <div className="chip-list">
              {contextTables.map((table) => (
                <button key={table} className="context-chip" onClick={() => setContextTables(contextTables.filter((item) => item !== table))}>{table}<X size={11} /></button>
              ))}
              <button className="clear-chip" onClick={() => setContextTables([])}>清空</button>
            </div>
          )}
        </div>

        <div className="ask-box">
          <textarea
            value={askValue}
            onChange={(event) => setAskValue(event.target.value)}
            onKeyDown={submitAskByKeyboard}
            placeholder="用自然语言提问，例如：帮我查最近 7 天新增用户数量趋势"
          />
          <button onClick={() => openResultTab(askValue)} title="发送"><Send size={18} /></button>
        </div>
        <div className="ask-hint">Ctrl / Cmd + Enter 发送。选择表作为上下文后，AI 会优先基于这些表生成 SQL。</div>
      </section>

      <section className="workspace-section">
        <div className="section-heading"><h2>推荐提问</h2><button>换一换</button></div>
        <div className="recommend-grid">
          {RECOMMENDED_QUESTIONS.map((item) => {
            const Icon = item.icon;
            return (
              <button key={item.title} className="recommend-card" onClick={() => setAskValue(item.title)}>
                <span className="recommend-icon"><Icon size={17} /></span>
                <strong>{item.title}</strong>
                <em>{item.tag}</em>
              </button>
            );
          })}
        </div>
      </section>

      <section className="workspace-section compact">
        <div className="section-heading"><h2>最近访问</h2><button>查看更多 &gt;</button></div>
        <div className="recent-grid">
          {["id_users", "comment_infos", "video_watch_records", "note_infos", "id_organizations"].map((table) => (
            <button key={table} className="recent-card" onClick={() => openTableTab(table)}>
              <strong>{table}</strong>
              <span>{getTableMeta(table)?.module ?? DATA_SOURCE.schema}</span>
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}

function TableWorkspace({ tableName, subTab, setSubTab, openSqlConsole, showToast }: {
  tableName: string;
  subTab: TableSubTab;
  setSubTab: (subTab: TableSubTab) => void;
  openSqlConsole: (sql?: string) => void;
  showToast: (message: string) => void;
}) {
  const meta = getTableMeta(tableName);
  const subTabs: { key: TableSubTab; label: string }[] = [
    { key: "preview", label: "数据预览" },
    { key: "schema", label: "字段结构" },
    { key: "relations", label: "关系图" },
    { key: "queries", label: "样例查询" },
    { key: "history", label: "使用记录" },
  ];

  return (
    <div className="table-workspace">
      <div className="object-header">
        <div>
          <div className="object-kicker">{DATA_SOURCE.name} / {DATA_SOURCE.schema} / {meta?.module ?? "数据表"}</div>
          <h2>{tableName}</h2>
          <p>{meta?.comment ?? "表数据预览与结构分析"}</p>
        </div>
        <div className="object-actions">
          <button onClick={() => openSqlConsole(`SELECT * FROM ${tableName} LIMIT 100;`)}><Terminal size={15} />SQL 查询</button>
          <button onClick={() => showToast("表元数据已刷新")}><RefreshCw size={15} />刷新</button>
        </div>
      </div>

      <div className="subtab-bar">
        {subTabs.map((tab) => <button key={tab.key} className={subTab === tab.key ? "active" : ""} onClick={() => setSubTab(tab.key)}>{tab.label}</button>)}
      </div>

      <div className="subtab-content">
        {subTab === "preview" && <PreviewTable tableName={tableName} openSqlConsole={openSqlConsole} showToast={showToast} />}
        {subTab === "schema" && <SchemaTable tableName={tableName} />}
        {subTab === "relations" && <RelationsView tableName={tableName} />}
        {subTab === "queries" && <SampleQueries tableName={tableName} openSqlConsole={openSqlConsole} />}
        {subTab === "history" && <HistoryView tableName={tableName} />}
      </div>
    </div>
  );
}

function PreviewTable({ tableName, openSqlConsole, showToast }: { tableName: string; openSqlConsole: (sql?: string) => void; showToast: (message: string) => void }) {
  const rows = getRows(tableName);
  const columns = getColumns(tableName);
  return (
    <div className="data-panel">
      <div className="panel-toolbar">
        <div>
          <button onClick={() => showToast("数据预览已刷新")}><RefreshCw size={14} />刷新</button>
          <button><Filter size={14} />筛选</button>
          <button><ArrowUpDown size={14} />排序</button>
          <button><Download size={14} />导出</button>
        </div>
        <button className="primary-soft" onClick={() => openSqlConsole(`SELECT * FROM ${tableName} LIMIT 100;`)}><Code size={14} />在 SQL 控制台打开</button>
      </div>
      <div className="table-scroll">
        <table className="data-table">
          <thead><tr>{columns.map((column) => <th key={column.key}>{column.label}</th>)}</tr></thead>
          <tbody>
            {rows.map((row, rowIndex) => (
              <tr key={rowIndex}>{columns.map((column) => <td key={column.key}><StatusBadge value={row[column.key] ?? "NULL"} /></td>)}</tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="table-footer"><span>共 12,345 条</span><span>1 / 1235</span><select defaultValue="10"><option>10 条/页</option><option>20 条/页</option></select></div>
    </div>
  );
}

function SchemaTable({ tableName }: { tableName: string }) {
  return (
    <div className="data-panel padded">
      <table className="data-table schema-table">
        <thead><tr><th>字段名</th><th>类型</th><th>约束</th><th>可空</th><th>默认值</th><th>注释</th></tr></thead>
        <tbody>
          {getSchemaRows(tableName).map((row) => (
            <tr key={row.name}>
              <td className="mono strong">{row.name}</td>
              <td className="mono type">{row.type}</td>
              <td>{row.constraint === "—" ? "—" : <span className={`constraint ${row.constraint.toLowerCase()}`}>{row.constraint}</span>}</td>
              <td>{row.nullable}</td>
              <td className="mono">{row.defaultValue}</td>
              <td>{row.comment}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RelationsView({ tableName }: { tableName: string }) {
  return (
    <div className="relations-canvas">
      <div className="er-card primary" style={{ left: 80, top: 70 }}><strong>{tableName}</strong><span>id PK</span><span>user_id FK</span><span>created_at</span></div>
      <div className="er-card" style={{ left: 360, top: 70 }}><strong>id_users</strong><span>id PK</span><span>tenant_id</span><span>account</span></div>
      <div className="er-card" style={{ left: 360, top: 250 }}><strong>id_organizations</strong><span>id PK</span><span>tenant_id</span><span>name</span></div>
      <svg className="er-lines"><path d="M220 125 C280 125 300 125 360 125" /><path d="M440 170 C440 215 440 220 440 250" /></svg>
    </div>
  );
}

function SampleQueries({ tableName, openSqlConsole }: { tableName: string; openSqlConsole: (sql?: string) => void }) {
  const samples = [
    { title: "预览前 100 行", sql: `SELECT * FROM ${tableName} LIMIT 100;` },
    { title: "按天统计新增量", sql: `SELECT DATE(created_at) AS date, COUNT(*) AS total FROM ${tableName} GROUP BY DATE(created_at) ORDER BY date;` },
    { title: "检查状态分布", sql: `SELECT status, COUNT(*) AS total FROM ${tableName} GROUP BY status;` },
  ];
  return <div className="sample-query-grid">{samples.map((item) => <button key={item.title} onClick={() => openSqlConsole(item.sql)}><strong>{item.title}</strong><pre>{item.sql}</pre></button>)}</div>;
}

function HistoryView({ tableName }: { tableName: string }) {
  return <div className="history-list">{["今天 14:12 预览表数据", "今天 13:58 生成字段结构", "昨天 18:20 作为问数上下文", "昨天 17:41 执行 SELECT 查询"].map((item) => <div key={item}><FileText size={14} /><span>{tableName}</span><em>{item}</em></div>)}</div>;
}

function SqlWorkspace({ sql, setSql, resultVisible, runSql }: { sql: string; setSql: (sql: string) => void; resultVisible: boolean; runSql: () => void }) {
  return (
    <div className="sql-workspace">
      <div className="sql-toolbar"><span>SQL Console / {DATA_SOURCE.name}</span><button onClick={runSql}><Play size={15} />运行 F9</button></div>
      <textarea className="sql-editor" value={sql} onChange={(event) => setSql(event.target.value)} spellCheck={false} />
      <div className="sql-output">
        <div className="output-tabs"><button className="active">查询结果 {resultVisible ? "(3行)" : ""}</button><button>消息日志</button><button>AI 解释</button></div>
        {resultVisible ? (
          <table className="data-table"><thead><tr><th>name</th><th>comment_count</th></tr></thead><tbody><tr><td>张三</td><td>1,432</td></tr><tr><td>李四</td><td>980</td></tr><tr><td>王五</td><td>412</td></tr></tbody></table>
        ) : <div className="empty-state">点击“运行”执行上方 SQL 并查看输出结果。</div>}
      </div>
    </div>
  );
}

function MultiWorkspace({ tables, openResultTab, openSqlConsole }: { tables: string[]; openResultTab: (query: string) => void; openSqlConsole: (sql?: string) => void }) {
  return (
    <div className="multi-workspace">
      <div className="multi-banner"><GitMerge size={20} /><div><strong>联合 Workspace</strong><span>已绑定 {tables.length} 张表：{tables.join("，")}</span></div></div>
      <div className="multi-actions">
        <button onClick={() => openResultTab(`分析 ${tables.join("、")} 的关联关系，并生成业务解释`)}><Layers size={18} /><strong>分析表关联拓扑</strong><span>识别主外键、逻辑外键和常见 Join 路径。</span></button>
        <button onClick={() => openResultTab(`统计 ${tables.join("、")} 最近一个月的联合活动数据量`)}><Sparkles size={18} /><strong>联合趋势统计</strong><span>生成多表统计 SQL、图表与结论。</span></button>
        <button onClick={() => openSqlConsole(`SELECT *\nFROM ${tables[0] ?? "id_users"} t1\nLEFT JOIN ${tables[1] ?? "comment_infos"} t2 ON t1.id = t2.user_id\nLIMIT 100;`)}><Terminal size={18} /><strong>打开联合 SQL</strong><span>基于当前表集合生成 SQL 草稿。</span></button>
      </div>
    </div>
  );
}

function ResultWorkspace({ query, openSqlConsole }: { query: string; openSqlConsole: (sql?: string) => void }) {
  return (
    <div className="result-workspace">
      <div className="result-header"><span>智能问数分析结果</span><h2>“{query}”</h2></div>
      <div className="analysis-card"><h3>关键结论</h3><p>最近 7 天新增用户整体呈上升趋势，11-15 达到阶段峰值。建议继续按组织、用户状态进行拆分分析。</p></div>
      <div className="chart-card"><h3>近 7 天新增用户趋势</h3><svg viewBox="0 0 640 220"><path className="grid" d="M40 40H600M40 90H600M40 140H600M40 190H600" /><path className="area" d="M40 170 C110 130 150 80 220 105 C290 135 330 60 400 92 C480 120 520 35 600 70 L600 190 L40 190 Z" /><path className="line" d="M40 170 C110 130 150 80 220 105 C290 135 330 60 400 92 C480 120 520 35 600 70" /></svg></div>
      <div className="sql-card"><div><h3>生成的 SQL</h3><button onClick={() => openSqlConsole(GENERATED_SQL)}><Terminal size={14} />在 SQL 控制台打开</button></div><pre>{GENERATED_SQL}</pre></div>
    </div>
  );
}

function ContextDrawer({ type, activeTab, contextTables, onClose }: { type: DrawerType; activeTab: WorkspaceTab; contextTables: string[]; onClose: () => void }) {
  return (
    <aside className="context-drawer">
      <div className="drawer-header"><strong>{type === "props" ? "对象属性" : type === "ai" ? "AI 建议" : "查询上下文"}</strong><button onClick={onClose}><X size={15} /></button></div>
      {type === "props" && <div className="drawer-content"><InfoRow label="当前 Tab" value={activeTab.title} /><InfoRow label="类型" value={activeTab.type} /><InfoRow label="数据源" value={DATA_SOURCE.name} /><InfoRow label="上下文表" value={`${contextTables.length} 张`} /></div>}
      {type === "ai" && <div className="drawer-content"><button className="suggestion">解释当前表字段含义</button><button className="suggestion">生成常用分析 SQL</button><button className="suggestion">检查数据质量问题</button><button className="suggestion">根据结果生成图表</button></div>}
    </aside>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return <div className="info-row"><span>{label}</span><strong>{value}</strong></div>;
}

function ContextMenu({ state, selectedTables, openTableTab, openSqlConsole, openMultiWorkspace, addTableToAskContext, setContextTables, hide, showToast }: {
  state: ContextMenuState;
  selectedTables: string[];
  openTableTab: (tableName: string, subTab?: TableSubTab) => void;
  openSqlConsole: (sql?: string) => void;
  openMultiWorkspace: (tables: string[]) => void;
  addTableToAskContext: (tableName: string) => void;
  setContextTables: (tables: string[]) => void;
  hide: () => void;
  showToast: (message: string) => void;
}) {
  const run = (fn: () => void) => {
    fn();
    hide();
  };

  return (
    <div className="context-menu" style={{ left: state.x, top: state.y }} onClick={(event) => event.stopPropagation()}>
      {state.type === "database" && <><button onClick={() => run(() => openSqlConsole())}><Terminal size={14} />打开 SQL 控制台</button><button onClick={() => run(() => showToast("连接测试成功"))}><Info size={14} />测试连接</button><button onClick={() => run(() => showToast("数据源已刷新"))}><RefreshCw size={14} />刷新</button></>}
      {state.type === "schema" && <><button onClick={() => run(() => openSqlConsole())}><Terminal size={14} />新建 SQL Console</button><button onClick={() => run(() => openTableTab("id_users", "schema"))}><Columns3 size={14} />查看表结构</button><button onClick={() => run(() => openTableTab("id_users", "relations"))}><GitMerge size={14} />生成 ER 图</button></>}
      {state.type === "table" && <><button onClick={() => run(() => openTableTab(state.target, "preview"))}><Table2 size={14} />预览表数据</button><button onClick={() => run(() => openTableTab(state.target, "schema"))}><Columns3 size={14} />查看字段结构</button><button onClick={() => run(() => openSqlConsole(`SELECT * FROM ${state.target} LIMIT 100;`))}><Terminal size={14} />打开 SQL 控制台</button><button onClick={() => run(() => addTableToAskContext(state.target))}><Sparkles size={14} />作为问数上下文</button><button onClick={() => run(() => openTableTab(state.target, "relations"))}><GitMerge size={14} />生成表级 ER 图</button><div className="menu-divider" /><button onClick={() => run(() => navigator.clipboard.writeText(state.target))}><Copy size={14} />复制物理表名</button><button className="danger" onClick={() => run(() => window.confirm(`确认删除 ${state.target}？`) && showToast(`已删除 ${state.target}`))}><Trash2 size={14} />删除表</button></>}
      {state.type === "multi-table" && <><button onClick={() => run(() => openMultiWorkspace(selectedTables))}><GitMerge size={14} />作为联合 Workspace 打开</button><button onClick={() => run(() => setContextTables(selectedTables))}><Sparkles size={14} />基于多表智能问数</button><button onClick={() => run(() => openTableTab(selectedTables[0], "relations"))}><Layers size={14} />生成联合 ER 图</button></>}
    </div>
  );
}
