import { useEffect, useState } from "react";
import {
  Search,
  Bell,
  ChevronDown,
  ChevronRight,
  Database,
  Sparkles,
  TrendingUp,
  User,
  FileText,
  RefreshCw,
  Maximize2,
  X,
  Plus,
  ArrowUpDown,
  Filter,
  Download,
  Code,
  ZoomIn,
  ZoomOut,
  Send,
  Layers,
  HelpCircle,
  Play,
  Settings,
  Copy,
  Trash2,
  Terminal,
  Info,
  GitMerge
} from "lucide-react";
import "./App.css";

export default function App() {
  const [scale, setScale] = useState(1);
  const [treeSearch, setTreeSearch] = useState("");
  const [askInputValue, setAskInputValue] = useState(
    "帮我查一下“市场运营部”上个月发布了多少资产？"
  );
  
  // Workspace tabs management
  interface Tab {
    id: string; // e.g. 'smart-query', 'table-id_users', 'sql-console', 'multi-table', 'query-result'
    title: string;
    type: 'smart-query' | 'table' | 'sql' | 'multi-table' | 'query-result';
    tableId?: string;
    selectedTables?: string[];
    queryText?: string;
    chatMessages?: { id: number; sender: 'user' | 'ai'; text: string }[];
  }

  const [tabs, setTabs] = useState<Tab[]>([
    { id: 'smart-query', title: '问数工作台', type: 'smart-query' }
  ]);
  const [activeTabId, setActiveTabId] = useState<string>('smart-query');

  // Sidebar table multi-selection (Ctrl/Cmd click)
  const [selectedTables, setSelectedTables] = useState<string[]>([]);
  
  // Drag and drop context tables for smart-query workspace
  const [contextTables, setContextTables] = useState<string[]>([]);

  // Sub-tabs active states for each table tab (remembering sub-tab per table)
  const [tableSubTabs, setTableSubTabs] = useState<Record<string, string>>({});

  // Right Drawer collapsible state
  const [rightDrawerOpen, setRightDrawerOpen] = useState(true); // default open to show specs
  const [rightDrawerType, setRightDrawerType] = useState<'specs' | 'ai-suggest' | 'props'>('specs');

  // Right click Context Menu state
  interface ContextMenu {
    visible: boolean;
    x: number;
    y: number;
    type: 'database' | 'schema' | 'table' | 'multi-table';
    targetNode: string;
  }
  const [contextMenu, setContextMenu] = useState<ContextMenu>({
    visible: false,
    x: 0,
    y: 0,
    type: 'database',
    targetNode: ''
  });

  // Global toast alerts
  const [toastMsg, setToastMsg] = useState<string | null>(null);
  const showToast = (msg: string) => {
    setToastMsg(msg);
    setTimeout(() => setToastMsg(null), 2500);
  };

  // Mock SQL execution state
  const [sqlQuery, setSqlQuery] = useState(`SELECT 
  u.name, 
  count(c.id) as comment_count 
FROM id_users u 
LEFT JOIN comment_infos c ON u.id = c.user_id 
GROUP BY u.id 
ORDER BY comment_count DESC;`);
  const [sqlResultsRun, setSqlResultsRun] = useState(false);
  const [sqlConsoleTab, setSqlConsoleTab] = useState<'results' | 'history' | 'ai-explain'>('results');

  // Interactive UI state values
  const [recentTab, setRecentTab] = useState("tables");
  const [activeHeaderTab, setActiveHeaderTab] = useState("workbench");

  // Autoscale responsive logic
  useEffect(() => {
    const handleResize = () => {
      const targetWidth = 1598;
      const targetHeight = 1066;
      const winWidth = window.innerWidth;
      const winHeight = window.innerHeight;
      const scaleX = winWidth / targetWidth;
      const scaleY = winHeight / targetHeight;
      setScale(Math.min(scaleX, scaleY));
    };

    window.addEventListener("resize", handleResize);
    handleResize();
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  // Close context menu on any document click
  useEffect(() => {
    const handleDocumentClick = () => {
      setContextMenu(prev => ({ ...prev, visible: false }));
    };
    window.addEventListener('click', handleDocumentClick);
    return () => window.removeEventListener('click', handleDocumentClick);
  }, []);

  // Tab control helpers
  const openTableTab = (tableName: string, initialSubtab = 'preview') => {
    const tabId = `table-${tableName}`;
    setTabs(prev => {
      if (prev.some(t => t.id === tabId)) return prev;
      return [...prev, { id: tabId, title: tableName, type: 'table', tableId: tableName }];
    });
    setActiveTabId(tabId);
    if (initialSubtab) {
      setTableSubTabs(prev => ({ ...prev, [tableName]: initialSubtab }));
    }
  };

  const closeTab = (tabId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    const nextTabs = tabs.filter(t => t.id !== tabId);
    if (nextTabs.length === 0) {
      setTabs([{ id: 'smart-query', title: '问数工作台', type: 'smart-query' }]);
      setActiveTabId('smart-query');
      return;
    }
    setTabs(nextTabs);
    if (activeTabId === tabId) {
      setActiveTabId(nextTabs[nextTabs.length - 1].id);
    }
  };

  const openSqlConsole = () => {
    const tabId = `sql-${Date.now()}`;
    setTabs(prev => [...prev, { id: tabId, title: 'SQL 控制台', type: 'sql' }]);
    setActiveTabId(tabId);
    showToast("已打开 SQL 控制台");
  };

  const openMultiTableWorkspace = (tables: string[]) => {
    if (tables.length === 0) return;
    const tabId = `multi-table-${Date.now()}`;
    const title = `Workspace: ${tables.slice(0, 2).join(' & ')}${tables.length > 2 ? '...' : ''}`;
    setTabs(prev => [...prev, { id: tabId, title, type: 'multi-table', selectedTables: tables }]);
    setActiveTabId(tabId);
    showToast(`已创建多表联合 Workspace (${tables.length} 张表)`);
  };

  const openQueryResultTab = (queryText: string) => {
    const tabId = `query-result-${Date.now()}`;
    const initialMsgs = [
      { id: 1, sender: 'ai', text: "你好！我是你的智能问数助理。针对您的查询，已为您生成以下的可视化分析图表与 SQL。" }
    ];
    setTabs(prev => [...prev, { 
      id: tabId, 
      title: '问数结果', 
      type: 'query-result', 
      queryText,
      chatMessages: initialMsgs
    }]);
    setActiveTabId(tabId);
  };

  // Sidebar table interactions
  const handleTableClick = (tableName: string, event: React.MouseEvent) => {
    if (event.ctrlKey || event.metaKey) {
      setSelectedTables(prev => {
        if (prev.includes(tableName)) {
          return prev.filter(t => t !== tableName);
        } else {
          return [...prev, tableName];
        }
      });
    } else {
      setSelectedTables([tableName]);
      openTableTab(tableName);
    }
  };

  const handleTableDoubleClick = (tableName: string) => {
    setSelectedTables([tableName]);
    openTableTab(tableName);
  };

  const addContextTable = (tableName: string) => {
    setContextTables(prev => {
      if (prev.includes(tableName)) return prev;
      return [...prev, tableName];
    });
    showToast(`已添加表 ${tableName} 到问数上下文`);
  };

  const handleNodeContextMenu = (e: React.MouseEvent, type: 'database' | 'schema' | 'table', nodeName: string) => {
    e.preventDefault();
    e.stopPropagation();
    
    if (type === 'table' && selectedTables.length > 1 && selectedTables.includes(nodeName)) {
      setContextMenu({
        visible: true,
        x: e.clientX,
        y: e.clientY,
        type: 'multi-table',
        targetNode: nodeName
      });
    } else {
      if (type === 'table') {
        setSelectedTables([nodeName]);
      }
      setContextMenu({
        visible: true,
        x: e.clientX,
        y: e.clientY,
        type,
        targetNode: nodeName
      });
    }
  };

  // Database Tree Nodes Structure
  const treeModules = [
    {
      name: "账号模块",
      tables: [
        { name: "id_users", comment: "用户基本信息" },
        { name: "id_organizations", comment: "组织架构信息" },
        { name: "id_departments", comment: "部门信息" }
      ]
    },
    {
      name: "账号模块", // Repeated block as shown in mockup: Note/Video
      tables: [
        { name: "note_infos", comment: "笔记信息" },
        { name: "video_infos", comment: "视频信息" }
      ]
    },
    {
      name: "互动模块",
      tables: [
        { name: "comment_infos", comment: "评论数据" },
        { name: "like_infos", comment: "点赞数据" },
        { name: "favorite_infos", comment: "收藏数据" }
      ]
    },
    {
      name: "流量模块",
      tables: [
        { name: "video_watch_records", comment: "视频观看记录" }
      ]
    },
    {
      name: "配置表",
      tables: [
        { name: "config_system", comment: "系统配置" },
        { name: "config_dict", comment: "数据字典" }
      ]
    },
    {
      name: "系统类",
      tables: [
        { name: "data_migrations", comment: "数据迁移记录" }
      ]
    }
  ];

  // Filtering Tree tables based on Search
  const filteredTreeModules = treeModules.map(mod => {
    const filteredTables = mod.tables.filter(t => 
      t.name.toLowerCase().includes(treeSearch.toLowerCase()) ||
      t.comment.toLowerCase().includes(treeSearch.toLowerCase())
    );
    return { ...mod, tables: filteredTables };
  }).filter(mod => mod.tables.length > 0);

  // Recommendations click handler
  const handleRecommendClick = (text: string) => {
    setAskInputValue(text);
  };

  // Ask prompt submit logic
  const handleAskSubmit = () => {
    if (!askInputValue.trim()) return;
    openQueryResultTab(askInputValue);
    setAskInputValue("");
  };

  // Chat send message inside query result tab
  const handleQueryResultChatSend = (tabId: string, text: string) => {
    if (!text.trim()) return;
    setTabs(prev => prev.map(t => {
      if (t.id === tabId) {
        return {
          ...t,
          chatMessages: [
            ...(t.chatMessages || []),
            { id: Date.now(), sender: 'user', text },
            { id: Date.now() + 1, sender: 'ai', text: "正在根据上下文查询与分析，请稍候..." }
          ]
        };
      }
      return t;
    }));
  };

  const toggleRightDrawer = (type: 'specs' | 'ai-suggest' | 'props') => {
    if (rightDrawerOpen && rightDrawerType === type) {
      setRightDrawerOpen(false);
    } else {
      setRightDrawerOpen(true);
      setRightDrawerType(type);
    }
  };

  return (
    <div className="hifi-viewport-wrapper">
      <div 
        className="hifi-canvas-board"
        style={{ "--scale": scale } as React.CSSProperties}
      >
        {/* TOP NAVIGATION HEADER */}
        <header className="hifi-header">
          <div className="hifi-header-left">
            <h1 className="hifi-header-title">数据库可视化 + 智能问数</h1>
            <span className="hifi-header-subtitle">全新界面设计方案</span>
          </div>

          <div className="hifi-header-tabs">
            <div 
              className={`hifi-header-tab ${activeHeaderTab === "workbench" ? "active" : ""}`}
              onClick={() => setActiveHeaderTab("workbench")}
            >
              工作台
            </div>
            <div 
              className={`hifi-header-tab ${activeHeaderTab === "database" ? "active" : ""}`}
              onClick={() => setActiveHeaderTab("database")}
            >
              数据库
            </div>
            <div 
              className={`hifi-header-tab ${activeHeaderTab === "ask" ? "active" : ""}`}
              onClick={() => setActiveHeaderTab("ask")}
            >
              智能问数
            </div>
            <div 
              className={`hifi-header-tab ${activeHeaderTab === "datasource" ? "active" : ""}`}
              onClick={() => setActiveHeaderTab("datasource")}
            >
              数据源管理
            </div>
          </div>

          <div className="hifi-header-right">
            <div className="hifi-icon-btn">
              <Search size={16} />
            </div>
            <div className="hifi-icon-btn">
              <Bell size={16} />
            </div>
            <div className="hifi-avatar">A</div>
          </div>
        </header>

        {/* FOUR-COLUMN WORKSPACE GRID */}
        <main className="hifi-workspace">
          {/* COLUMN 1: LEFT SIDEBAR (DATABASE STRUCTURE TREE) */}
          <section className="hifi-col">
            <div className="hifi-sidebar-panel">
              <div className="hifi-sidebar-header">
                <span className="hifi-sidebar-title">数据源</span>
                <RefreshCw size={12} className="text-gray-400 cursor-pointer" onClick={() => showToast("已刷新数据源树")} />
              </div>

              {/* Data Source Selector */}
              <div 
                className="hifi-db-select"
                onContextMenu={(e) => handleNodeContextMenu(e, 'database', 'prod-mysql')}
              >
                <Database size={16} className="text-blue-600" />
                <div className="hifi-db-info">
                  <span className="hifi-db-name">prod-mysql</span>
                  <span className="hifi-db-version">MySQL 8.0</span>
                </div>
                <ChevronDown size={14} className="text-gray-400" />
              </div>

              {/* Tree Search Box */}
              <div className="hifi-search-box">
                <Search size={12} className="hifi-search-icon" />
                <input
                  type="text"
                  className="hifi-search-input"
                  placeholder="搜索表或字段"
                  value={treeSearch}
                  onChange={(e) => setTreeSearch(e.target.value)}
                />
              </div>

              {/* Tree Navigation Container */}
              <div className="hifi-tree-container">
                {/* Fixed items */}
                <div className="hifi-tree-node opacity-60">
                  <ChevronRight size={12} className="mr-1 text-gray-400" />
                  <Database size={12} className="mr-1 text-gray-500" />
                  <span>information_schema</span>
                </div>
                <div className="hifi-tree-node opacity-60">
                  <ChevronRight size={12} className="mr-1 text-gray-400" />
                  <Database size={12} className="mr-1 text-gray-500" />
                  <span>lindorm</span>
                </div>
                
                {/* Main Expanded Connection */}
                <div 
                  className="hifi-tree-node font-semibold text-gray-900 cursor-pointer"
                  onContextMenu={(e) => handleNodeContextMenu(e, 'schema', '小红书数据')}
                >
                  <ChevronDown size={12} className="mr-1 text-slate-500" />
                  <Database size={12} className="mr-1 text-blue-600" />
                  <span>小红书数据</span>
                </div>

                {/* Modules list */}
                {filteredTreeModules.map((mod, modIdx) => (
                  <div key={modIdx} style={{ marginLeft: "12px" }}>
                    <div className="hifi-tree-node">
                      <ChevronDown size={10} className="mr-1 text-gray-400" />
                      <span className="text-gray-500 font-medium">{mod.name}</span>
                    </div>

                    {/* Tables list */}
                    {mod.tables.map((table, tIdx) => {
                      const isSelected = selectedTables.includes(table.name);
                      return (
                        <div
                          key={tIdx}
                          className={`hifi-tree-node ${isSelected ? "active" : ""}`}
                          style={{ marginLeft: "12px", cursor: 'grab' }}
                          draggable={true}
                          onDragStart={(e) => {
                            e.dataTransfer.setData('text/plain', table.name);
                            e.dataTransfer.effectAllowed = 'copy';
                          }}
                          onClick={(e) => handleTableClick(table.name, e)}
                          onDoubleClick={() => handleTableDoubleClick(table.name)}
                          onContextMenu={(e) => handleNodeContextMenu(e, 'table', table.name)}
                        >
                          <span className="hifi-tree-indent"></span>
                          <FileText size={11} className="mr-1.5 opacity-70" />
                          <span className="truncate" title={table.comment}>{table.name}</span>
                        </div>
                      );
                    })}
                  </div>
                ))}
              </div>

            </div>
          </section>

          {/* COLUMN 2: TABBED MAIN WORKSPACE */}
          <section className="hifi-col hifi-main-workspace-col">
            {/* Tab Header Bar */}
            <div className="hifi-workspace-tab-bar">
              <div className="hifi-workspace-tabs-scroll">
                {tabs.map(tab => {
                  const isActive = tab.id === activeTabId;
                  return (
                    <div
                      key={tab.id}
                      className={`hifi-workspace-tab ${isActive ? 'active' : ''}`}
                      onClick={() => {
                        setActiveTabId(tab.id);
                        if (tab.type === 'table' && tab.tableId) {
                          setSelectedTables([tab.tableId]);
                        }
                      }}
                    >
                      {tab.type === 'smart-query' && <Sparkles size={11} className="text-purple-500" />}
                      {tab.type === 'table' && <FileText size={11} className="text-blue-500" />}
                      {tab.type === 'sql' && <Terminal size={11} className="text-green-500" />}
                      {tab.type === 'multi-table' && <GitMerge size={11} className="text-orange-500" />}
                      {tab.type === 'query-result' && <TrendingUp size={11} className="text-purple-500" />}
                      
                      <span className="truncate max-w-[100px]">{tab.title}</span>
                      <X 
                        size={10} 
                        className="hifi-tab-close ml-1.5 opacity-60 hover:opacity-100" 
                        onClick={(e) => closeTab(tab.id, e)} 
                      />
                    </div>
                  );
                })}
                <button className="hifi-tab-add-btn" onClick={openSqlConsole} title="新建 SQL 查询">
                  <Plus size={11} />
                </button>
              </div>

              {/* Right-side Toggle Actions */}
              <div className="hifi-workspace-tab-actions">
                <button 
                  className={`hifi-right-drawer-toggle-btn ${rightDrawerOpen && rightDrawerType === 'specs' ? 'active' : ''}`}
                  onClick={() => toggleRightDrawer('specs')}
                >
                  <Layers size={11} />
                  <span>设计规范</span>
                </button>
                <button 
                  className={`hifi-right-drawer-toggle-btn ${rightDrawerOpen && rightDrawerType === 'ai-suggest' ? 'active' : ''}`}
                  onClick={() => toggleRightDrawer('ai-suggest')}
                >
                  <Sparkles size={11} />
                  <span>AI 建议</span>
                </button>
                <button 
                  className={`hifi-right-drawer-toggle-btn ${rightDrawerOpen && rightDrawerType === 'props' ? 'active' : ''}`}
                  onClick={() => toggleRightDrawer('props')}
                >
                  <Info size={11} />
                  <span>属性</span>
                </button>
              </div>
            </div>

            {/* Render Active Tab Pane */}
            {(() => {
              const activeTab = tabs.find(t => t.id === activeTabId) || tabs[0];
              
              if (activeTab.type === 'smart-query') {
                return (
                  <div className="hifi-query-home hifi-tab-pane">
                    <div className="hifi-hero">
                      <h2 className="hifi-hero-title">
                        你好，开始你的<span className="hifi-gradient-text">智能问数之旅</span>
                      </h2>
                      <p className="hifi-hero-subtitle">用自然语言提问，AI 帮你从数据中找到答案</p>
                      <div className="hifi-hero-pattern"></div>
                    </div>

                    {/* Drag & Drop Context Table Area */}
                    <div 
                      className="hifi-drop-zone"
                      onDragOver={(e) => e.preventDefault()}
                      onDrop={(e) => {
                        e.preventDefault();
                        const tableName = e.dataTransfer.getData('text/plain');
                        if (tableName) addContextTable(tableName);
                      }}
                    >
                      <GitMerge size={12} className="text-indigo-500 flex-shrink-0" />
                      <span className="text-[10px] text-slate-500 font-semibold mr-1">问数上下文:</span>
                      {contextTables.length === 0 ? (
                        <span className="text-[10px] text-slate-400 italic">拖拽左侧的表到这里以加载问数上下文</span>
                      ) : (
                        <div className="flex gap-1.5 flex-wrap items-center">
                          {contextTables.map(tbl => (
                            <span key={tbl} className="hifi-context-chip flex items-center gap-1 bg-indigo-50 border border-indigo-200 text-indigo-700 px-1.5 py-0.5 rounded text-[9px] font-mono">
                              <span>{tbl}</span>
                              <X size={8} className="cursor-pointer hover:bg-indigo-200 rounded-full p-0.5" onClick={() => setContextTables(prev => prev.filter(x => x !== tbl))} />
                            </span>
                          ))}
                          <button className="text-[9px] text-red-500 hover:underline ml-1" onClick={() => setContextTables([])}>清除</button>
                        </div>
                      )}
                    </div>

                    {/* Question Input Box */}
                    <div className="hifi-ask-input-container">
                      <textarea
                        className="hifi-ask-input"
                        value={askInputValue}
                        onChange={(e) => setAskInputValue(e.target.value)}
                        placeholder="用自然语言提问，例如：帮我查一下“市场运营部”上个月发布了多少资产？"
                      />
                      <button className="hifi-ask-send-btn animate-pulse" onClick={handleAskSubmit}>
                        <Send size={14} />
                      </button>
                    </div>

                    {/* Recommended Questions */}
                    <div className="hifi-recommend-section">
                      <div className="hifi-section-header">
                        <span className="hifi-section-title">推荐提问</span>
                        <button className="hifi-text-btn" onClick={() => showToast("已随机刷新推荐提问")}>
                          <RefreshCw size={11} />
                          换一换
                        </button>
                      </div>

                      <div className="hifi-recommend-grid">
                        <div 
                          className="hifi-recommend-card"
                          onClick={() => handleRecommendClick("分析近 7 天评论数据趋势")}
                        >
                          <div className="hifi-recommend-icon">
                            <TrendingUp size={13} />
                          </div>
                          <span className="hifi-recommend-text">分析近 7 天评论数据趋势</span>
                          <span className="hifi-tag">数据分析</span>
                        </div>

                        <div 
                          className="hifi-recommend-card"
                          onClick={() => handleRecommendClick("查询活跃用户 Top 10")}
                        >
                          <div className="hifi-recommend-icon">
                            <User size={13} />
                          </div>
                          <span className="hifi-recommend-text">查询活跃用户 Top 10</span>
                          <span className="hifi-tag">用户分析</span>
                        </div>

                        <div 
                          className="hifi-recommend-card"
                          onClick={() => handleRecommendClick("统计本月新增笔记数量")}
                        >
                          <div className="hifi-recommend-icon">
                            <FileText size={13} />
                          </div>
                          <span className="hifi-recommend-text">统计本月新增笔记数量</span>
                          <span className="hifi-tag">内容分析</span>
                        </div>

                        <div 
                          className="hifi-recommend-card"
                          onClick={() => handleRecommendClick("检查 comment_infos 是否有异常数据")}
                        >
                          <div className="hifi-recommend-icon">
                            <Search size={13} />
                          </div>
                          <span className="hifi-recommend-text">检查 comment_infos 是否有异常数据</span>
                          <span className="hifi-tag">数据治理</span>
                        </div>
                      </div>
                    </div>

                    {/* Recently Visited */}
                    <div className="hifi-recent-section">
                      <div className="hifi-section-header">
                        <div className="hifi-recent-tabs">
                          <span 
                            className={`hifi-recent-tab ${recentTab === "tables" ? "active" : ""}`}
                            onClick={() => setRecentTab("tables")}
                          >
                            最近表
                          </span>
                          <span 
                            className={`hifi-recent-tab ${recentTab === "queries" ? "active" : ""}`}
                            onClick={() => setRecentTab("queries")}
                          >
                            最近查询
                          </span>
                          <span 
                            className={`hifi-recent-tab ${recentTab === "chat" ? "active" : ""}`}
                            onClick={() => setRecentTab("chat")}
                          >
                            最近问答
                          </span>
                        </div>
                        <button className="hifi-text-btn" onClick={() => showToast("打开历史访问中心")}>查看更多 &gt;</button>
                      </div>

                      <div className="hifi-recent-grid">
                        <div className="hifi-recent-card" onClick={() => openTableTab("id_users")}>
                          <span className="hifi-recent-name">id_users</span>
                          <p className="hifi-recent-desc">小红书数据</p>
                        </div>
                        <div className="hifi-recent-card" onClick={() => openTableTab("comment_infos")}>
                          <span className="hifi-recent-name">comment_infos</span>
                          <p className="hifi-recent-desc">互动模块</p>
                        </div>
                        <div className="hifi-recent-card" onClick={() => openTableTab("video_watch_records")}>
                          <span className="hifi-recent-name">video_watch_records</span>
                          <p className="hifi-recent-desc">流量模块</p>
                        </div>
                        <div className="hifi-recent-card" onClick={() => openTableTab("note_infos")}>
                          <span className="hifi-recent-name">note_infos</span>
                          <p className="hifi-recent-desc">内容模块</p>
                        </div>
                        <div className="hifi-recent-card" onClick={() => openTableTab("id_organizations")}>
                          <span className="hifi-recent-name">id_organizations</span>
                          <p className="hifi-recent-desc">账号模块</p>
                        </div>
                      </div>
                    </div>
                  </div>
                );
              }

              if (activeTab.type === 'table') {
                const tableId = activeTab.tableId || 'id_users';
                const currentSubTab = tableSubTabs[tableId] || 'preview';

                return (
                  <div className="hifi-table-workspace hifi-tab-pane">
                    <div className="hifi-workspace-subtabs">
                      <div 
                        className={`hifi-workspace-subtab ${currentSubTab === 'preview' ? 'active' : ''}`}
                        onClick={() => setTableSubTabs(prev => ({ ...prev, [tableId]: 'preview' }))}
                      >
                        数据预览
                      </div>
                      <div 
                        className={`hifi-workspace-subtab ${currentSubTab === 'schema' ? 'active' : ''}`}
                        onClick={() => setTableSubTabs(prev => ({ ...prev, [tableId]: 'schema' }))}
                      >
                        字段结构
                      </div>
                      <div 
                        className={`hifi-workspace-subtab ${currentSubTab === 'er' ? 'active' : ''}`}
                        onClick={() => setTableSubTabs(prev => ({ ...prev, [tableId]: 'er' }))}
                      >
                        关系图
                      </div>
                      <div 
                        className={`hifi-workspace-subtab ${currentSubTab === 'queries' ? 'active' : ''}`}
                        onClick={() => setTableSubTabs(prev => ({ ...prev, [tableId]: 'queries' }))}
                      >
                        样例查询
                      </div>
                      <div 
                        className={`hifi-workspace-subtab ${currentSubTab === 'history' ? 'active' : ''}`}
                        onClick={() => setTableSubTabs(prev => ({ ...prev, [tableId]: 'history' }))}
                      >
                        使用记录
                      </div>
                    </div>

                    <div className="hifi-subtab-content flex-1 overflow-auto">
                      {currentSubTab === 'preview' && (
                        <div className="flex flex-col h-full overflow-hidden">
                          {/* Preview toolbar */}
                          <div className="hifi-panel-toolbar">
                            <div className="hifi-toolbar-left">
                              <button className="hifi-toolbar-btn" onClick={() => showToast("数据预览已刷新")}>
                                <RefreshCw size={10} /> 刷新
                              </button>
                              <button className="hifi-toolbar-btn" onClick={() => showToast("打开过滤器")}>
                                <Filter size={10} /> 筛选
                              </button>
                              <button className="hifi-toolbar-btn" onClick={() => showToast("打开排序规则")}>
                                <ArrowUpDown size={10} /> 排序
                              </button>
                              <button className="hifi-toolbar-btn" onClick={() => showToast("已导出数据预览")}>
                                <Download size={10} /> 导出
                              </button>
                              <button className="hifi-toolbar-btn" onClick={() => showToast("测试数据已生成并写入")}>
                                <Sparkles size={10} className="text-yellow-600" /> 生成测试数据
                              </button>
                            </div>
                            <div className="hifi-toolbar-right">
                              <Search size={12} className="text-gray-400 cursor-pointer" />
                              <button className="hifi-text-btn flex items-center gap-1" onClick={openSqlConsole}>
                                <Code size={11} /> 在 SQL 运行
                              </button>
                            </div>
                          </div>

                          {/* Data Table */}
                          <div className="hifi-table-container flex-1 overflow-auto">
                            <table className="hifi-table">
                              <thead>
                                {tableId === 'comment_infos' ? (
                                  <tr>
                                    <th>id</th>
                                    <th>note_id</th>
                                    <th>user_id</th>
                                    <th>content</th>
                                    <th>status</th>
                                    <th>created_at</th>
                                  </tr>
                                ) : tableId === 'video_infos' ? (
                                  <tr>
                                    <th>id</th>
                                    <th>title</th>
                                    <th>url</th>
                                    <th>duration</th>
                                    <th>play_count</th>
                                    <th>status</th>
                                  </tr>
                                ) : (
                                  <tr>
                                    <th>id</th>
                                    <th>tenant_id</th>
                                    <th>name</th>
                                    <th>account</th>
                                    <th>status</th>
                                    <th>created_at</th>
                                  </tr>
                                )}
                              </thead>
                              <tbody>
                                {tableId === 'comment_infos' ? (
                                  <>
                                    <tr>
                                      <td>101</td>
                                      <td>20001</td>
                                      <td>1</td>
                                      <td className="max-w-[200px] truncate" title="这个系统界面太漂亮了！">这个系统界面太漂亮了！</td>
                                      <td><span className="hifi-status-tag active"><span className="hifi-dot active"></span>active</span></td>
                                      <td>2024-11-17 08:32:00</td>
                                    </tr>
                                    <tr>
                                      <td>102</td>
                                      <td>20002</td>
                                      <td>2</td>
                                      <td className="max-w-[200px] truncate" title="同意！设计细节直接拉满。">同意！设计细节直接拉满。</td>
                                      <td><span className="hifi-status-tag active"><span className="hifi-dot active"></span>active</span></td>
                                      <td>2024-11-17 08:45:10</td>
                                    </tr>
                                    <tr>
                                      <td>103</td>
                                      <td>20001</td>
                                      <td>3</td>
                                      <td className="max-w-[200px] truncate" title="数据字典表在哪里配置？">数据字典表在哪里配置？</td>
                                      <td><span className="hifi-status-tag pending"><span className="hifi-dot pending"></span>pending</span></td>
                                      <td>2024-11-17 09:12:05</td>
                                    </tr>
                                  </>
                                ) : tableId === 'video_infos' ? (
                                  <>
                                    <tr>
                                      <td>501</td>
                                      <td>智能问数新手引导</td>
                                      <td>/videos/guide.mp4</td>
                                      <td>03:45</td>
                                      <td>1,240</td>
                                      <td><span className="hifi-status-tag active"><span className="hifi-dot active"></span>active</span></td>
                                    </tr>
                                    <tr>
                                      <td>502</td>
                                      <td>ER图表关联教程</td>
                                      <td>/videos/er_tutorial.mp4</td>
                                      <td>07:20</td>
                                      <td>890</td>
                                      <td><span className="hifi-status-tag active"><span className="hifi-dot active"></span>active</span></td>
                                    </tr>
                                  </>
                                ) : (
                                  <>
                                    <tr>
                                      <td>1</td>
                                      <td>10001</td>
                                      <td>张三</td>
                                      <td>zhangsan</td>
                                      <td><span className="hifi-status-tag active"><span className="hifi-dot active"></span>active</span></td>
                                      <td>2024-11-16 10:23:45</td>
                                    </tr>
                                    <tr>
                                      <td>2</td>
                                      <td>10001</td>
                                      <td>李四</td>
                                      <td>lisi</td>
                                      <td><span className="hifi-status-tag active"><span className="hifi-dot active"></span>active</span></td>
                                      <td>2024-11-16 10:23:45</td>
                                    </tr>
                                    <tr>
                                      <td>3</td>
                                      <td>10002</td>
                                      <td>王五</td>
                                      <td>wangwu</td>
                                      <td><span className="hifi-status-tag inactive"><span className="hifi-dot inactive"></span>inactive</span></td>
                                      <td>2024-11-16 10:23:45</td>
                                    </tr>
                                    <tr>
                                      <td>4</td>
                                      <td>10002</td>
                                      <td>赵六</td>
                                      <td>zhaoliu</td>
                                      <td><span className="hifi-status-tag active"><span className="hifi-dot active"></span>active</span></td>
                                      <td>2024-11-16 10:23:45</td>
                                    </tr>
                                  </>
                                )}
                              </tbody>
                            </table>
                          </div>

                          {/* Pagination Footer */}
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
                      )}

                      {currentSubTab === 'schema' && (
                        <div className="flex flex-col p-3 h-full overflow-auto">
                          <span className="text-[10px] text-gray-400 block mb-1">字段列表 (Schema Structure) &gt; {tableId}</span>
                          <table className="hifi-table">
                            <thead>
                              <tr>
                                <th>字段名</th>
                                <th>类型</th>
                                <th>约束</th>
                                <th>可空</th>
                                <th>默认值</th>
                                <th>注释</th>
                              </tr>
                            </thead>
                            <tbody>
                              {tableId === 'comment_infos' ? (
                                <>
                                  <tr>
                                    <td>id</td>
                                    <td className="text-blue-600 font-mono">bigint(20) unsigned</td>
                                    <td><span className="hifi-constraint-badge pk">PK</span></td>
                                    <td>否</td>
                                    <td>—</td>
                                    <td>主键 ID</td>
                                  </tr>
                                  <tr>
                                    <td>note_id</td>
                                    <td className="text-blue-600 font-mono">bigint(20) unsigned</td>
                                    <td><span className="hifi-constraint-badge index">INDEX</span></td>
                                    <td>否</td>
                                    <td>—</td>
                                    <td>关联笔记 ID</td>
                                  </tr>
                                  <tr>
                                    <td>user_id</td>
                                    <td className="text-blue-600 font-mono">bigint(20) unsigned</td>
                                    <td><span className="hifi-constraint-badge index">INDEX</span></td>
                                    <td>否</td>
                                    <td>—</td>
                                    <td>发布评论用户 ID</td>
                                  </tr>
                                  <tr>
                                    <td>content</td>
                                    <td className="text-blue-600 font-mono">text</td>
                                    <td>—</td>
                                    <td>否</td>
                                    <td>—</td>
                                    <td>评论内容</td>
                                  </tr>
                                  <tr>
                                    <td>status</td>
                                    <td className="text-blue-600 font-mono">enum('active','pending','spam')</td>
                                    <td>—</td>
                                    <td>否</td>
                                    <td>'active'</td>
                                    <td>评论状态</td>
                                  </tr>
                                </>
                              ) : (
                                <>
                                  <tr>
                                    <td>id</td>
                                    <td className="text-blue-600 font-mono">bigint(20) unsigned</td>
                                    <td><span className="hifi-constraint-badge pk">PK</span></td>
                                    <td>否</td>
                                    <td>—</td>
                                    <td>主键 ID</td>
                                  </tr>
                                  <tr>
                                    <td>tenant_id</td>
                                    <td className="text-blue-600 font-mono">bigint(20) unsigned</td>
                                    <td><span className="hifi-constraint-badge index">INDEX</span></td>
                                    <td>否</td>
                                    <td>—</td>
                                    <td>租户 ID</td>
                                  </tr>
                                  <tr>
                                    <td>name</td>
                                    <td className="text-blue-600 font-mono">varchar(100)</td>
                                    <td>—</td>
                                    <td>否</td>
                                    <td>—</td>
                                    <td>名称</td>
                                  </tr>
                                </>
                              )}
                            </tbody>
                          </table>
                        </div>
                      )}

                      {currentSubTab === 'er' && (
                        <div className="h-full w-full bg-slate-50 relative overflow-hidden flex flex-col p-4">
                          <span className="text-[10px] text-gray-400 block mb-2">ER 关系图 &gt; {tableId}</span>
                          <div className="flex-1 relative border border-slate-200 bg-white rounded-xl shadow-inner overflow-hidden">
                            {tableId === 'comment_infos' || tableId === 'like_infos' || tableId === 'favorite_infos' || tableId === 'note_infos' || tableId === 'video_infos' ? (
                              /* Interactive Comment ER Diagram */
                              <div className="absolute inset-0">
                                {/* comment_infos */}
                                <div className="absolute bg-white border border-slate-300 rounded shadow-sm text-[8px] z-10 w-[95px]" style={{ left: "20px", top: "20px" }}>
                                  <div className="bg-[#EEF2FF] border-b border-slate-200 px-1.5 py-0.5 font-bold flex justify-between">
                                    <span>comment_infos</span>
                                    <span className="text-[#3730A3]">Interactive</span>
                                  </div>
                                  <div className="p-1 leading-normal text-slate-600 font-mono">
                                    <div><strong className="text-slate-800">id</strong> (PK)</div>
                                    <div>note_id (FK)</div>
                                    <div>user_id (FK)</div>
                                    <div>content</div>
                                    <div>status</div>
                                    <div>created_at</div>
                                  </div>
                                </div>

                                {/* note_infos */}
                                <div className="absolute bg-white border border-slate-300 rounded shadow-sm text-[8px] z-10 w-[95px]" style={{ left: "180px", top: "20px" }}>
                                  <div className="bg-[#FFF7ED] border-b border-slate-200 px-1.5 py-0.5 font-bold flex justify-between">
                                    <span>note_infos</span>
                                  </div>
                                  <div className="p-1 leading-normal text-slate-600 font-mono">
                                    <div><strong className="text-slate-800">id</strong> (PK)</div>
                                    <div>user_id</div>
                                    <div>title</div>
                                    <div>created_at</div>
                                  </div>
                                </div>

                                {/* video_infos */}
                                <div className="absolute bg-white border border-slate-300 rounded shadow-sm text-[8px] z-10 w-[95px]" style={{ left: "20px", top: "160px" }}>
                                  <div className="bg-[#ECFDF5] border-b border-slate-200 px-1.5 py-0.5 font-bold flex justify-between">
                                    <span>video_infos</span>
                                  </div>
                                  <div className="p-1 leading-normal text-slate-600 font-mono">
                                    <div><strong className="text-slate-800">id</strong> (PK)</div>
                                    <div>title</div>
                                    <div>url</div>
                                    <div>duration</div>
                                  </div>
                                </div>

                                {/* like_infos */}
                                <div className="absolute bg-white border border-slate-300 rounded shadow-sm text-[8px] z-10 w-[95px]" style={{ left: "180px", top: "160px" }}>
                                  <div className="bg-[#FEF2F2] border-b border-slate-200 px-1.5 py-0.5 font-bold flex justify-between">
                                    <span>like_infos</span>
                                  </div>
                                  <div className="p-1 leading-normal text-slate-600 font-mono">
                                    <div><strong className="text-slate-800">id</strong> (PK)</div>
                                    <div>target_id</div>
                                    <div>target_type</div>
                                    <div>user_id</div>
                                  </div>
                                </div>

                                {/* SVG Connections */}
                                <svg className="absolute inset-0 w-full h-full pointer-events-none">
                                  <path d="M 115 50 L 180 50" fill="none" stroke="#94A3B8" strokeWidth="1.2" strokeDasharray="3" />
                                  <path d="M 68 115 L 68 160" fill="none" stroke="#94A3B8" strokeWidth="1.2" />
                                  <path d="M 180 185 C 150 185, 140 50, 115 50" fill="none" stroke="#94A3B8" strokeWidth="1.2" />
                                </svg>
                              </div>
                            ) : (
                              /* Standard User Organization Department module diagram */
                              <div className="absolute inset-0">
                                {/* id_users */}
                                <div className="absolute bg-white border border-slate-300 rounded shadow-sm text-[8px] z-10 w-[95px] overflow-hidden" style={{ left: "20px", top: "20px" }}>
                                  <div className="bg-[#EFF6FF] border-b border-slate-200 px-1.5 py-0.5 font-bold flex justify-between">
                                    <span>id_users</span>
                                    <span className="text-blue-600 font-semibold">PK</span>
                                  </div>
                                  <div className="p-1 leading-normal text-slate-600 font-mono">
                                    <div><strong className="text-slate-800">id</strong> (PK)</div>
                                    <div>tenant_id</div>
                                    <div>name</div>
                                    <div>account</div>
                                    <div>status</div>
                                    <div>created_at</div>
                                  </div>
                                </div>

                                {/* id_organizations */}
                                <div className="absolute bg-white border border-slate-300 rounded shadow-sm text-[8px] z-10 w-[95px] overflow-hidden" style={{ left: "180px", top: "20px" }}>
                                  <div className="bg-[#ECFDF5] border-b border-slate-200 px-1.5 py-0.5 font-bold flex justify-between">
                                    <span>id_organizations</span>
                                  </div>
                                  <div className="p-1 leading-normal text-slate-600 font-mono">
                                    <div><strong className="text-slate-800">id</strong> (PK)</div>
                                    <div>tenant_id</div>
                                    <div>name</div>
                                    <div>type</div>
                                    <div>created_at</div>
                                  </div>
                                </div>

                                {/* id_departments */}
                                <div className="absolute bg-white border border-slate-300 rounded shadow-sm text-[8px] z-10 w-[95px] overflow-hidden" style={{ left: "20px", top: "170px" }}>
                                  <div className="bg-[#FFF7ED] border-b border-slate-200 px-1.5 py-0.5 font-bold flex justify-between">
                                    <span>id_departments</span>
                                  </div>
                                  <div className="p-1 leading-normal text-slate-600 font-mono">
                                    <div><strong className="text-slate-800">id</strong> (PK)</div>
                                    <div>organization_id (FK)</div>
                                    <div>name</div>
                                    <div>created_at</div>
                                  </div>
                                </div>

                                {/* id_users_organizations */}
                                <div className="absolute bg-white border border-slate-300 rounded shadow-sm text-[8px] z-10 w-[95px] overflow-hidden" style={{ left: "180px", top: "170px" }}>
                                  <div className="bg-[#EEF2FF] border-b border-slate-200 px-1.5 py-0.5 font-bold flex justify-between">
                                    <span>id_users_orgs</span>
                                  </div>
                                  <div className="p-1 leading-normal text-slate-600 font-mono">
                                    <div><strong className="text-slate-800">id</strong> (PK)</div>
                                    <div>user_id (FK)</div>
                                    <div>organization_id (FK)</div>
                                    <div>role</div>
                                  </div>
                                </div>

                                {/* SVG Lines */}
                                <svg className="absolute inset-0 w-full h-full pointer-events-none">
                                  <path d="M 68 115 C 68 140, 180 140, 180 170" fill="none" stroke="#94A3B8" strokeWidth="1.2" />
                                  <path d="M 180 110 L 180 170" fill="none" stroke="#94A3B8" strokeWidth="1.2" />
                                  <path d="M 180 110 C 150 130, 68 140, 68 170" fill="none" stroke="#94A3B8" strokeWidth="1.2" />
                                </svg>
                              </div>
                            )}

                            {/* Zooms */}
                            <div className="hifi-er-zoom-controls">
                              <button className="hifi-er-zoom-btn" onClick={() => showToast("放大")}><Plus size={12} /></button>
                              <button className="hifi-er-zoom-btn" onClick={() => showToast("缩小")}><ZoomIn size={12} /></button>
                              <button className="hifi-er-zoom-btn" onClick={() => showToast("自适应窗口")}><ZoomOut size={12} /></button>
                              <button className="hifi-er-zoom-btn" onClick={() => showToast("重新排版")}><Layers size={12} /></button>
                            </div>
                          </div>
                        </div>
                      )}

                      {currentSubTab === 'queries' && (
                        <div className="p-4 h-full overflow-auto flex flex-col gap-3">
                          <span className="text-[10px] text-gray-400 block mb-1">常用 SQL 模板 &gt; {tableId}</span>
                          
                          <div className="border border-slate-200 rounded-lg p-3 bg-white hover:border-indigo-400 transition cursor-pointer" onClick={() => {
                            setSqlQuery(`SELECT * FROM ${tableId} ORDER BY id DESC LIMIT 50;`);
                            openSqlConsole();
                          }}>
                            <div className="flex justify-between items-center mb-1">
                              <span className="font-semibold text-[11px] text-slate-800">查询最近导入的 50 条记录</span>
                              <Play size={10} className="text-emerald-500" />
                            </div>
                            <pre className="text-[10px] text-slate-500 bg-slate-50 p-1.5 rounded font-mono">SELECT * FROM {tableId} ORDER BY id DESC LIMIT 50;</pre>
                          </div>

                          <div className="border border-slate-200 rounded-lg p-3 bg-white hover:border-indigo-400 transition cursor-pointer" onClick={() => {
                            setSqlQuery(`SELECT status, count(*) FROM ${tableId} GROUP BY status;`);
                            openSqlConsole();
                          }}>
                            <div className="flex justify-between items-center mb-1">
                              <span className="font-semibold text-[11px] text-slate-800">按状态统计行数</span>
                              <Play size={10} className="text-emerald-500" />
                            </div>
                            <pre className="text-[10px] text-slate-500 bg-slate-50 p-1.5 rounded font-mono">SELECT status, count(*) FROM {tableId} GROUP BY status;</pre>
                          </div>
                        </div>
                      )}

                      {currentSubTab === 'history' && (
                        <div className="p-4 h-full overflow-auto flex flex-col gap-2">
                          <span className="text-[10px] text-gray-400 block mb-1">表访问记录 &gt; {tableId}</span>
                          <div className="border border-slate-100 rounded overflow-hidden">
                            <div className="bg-slate-50 border-b border-slate-200 px-3 py-1.5 text-[10px] text-slate-500 flex justify-between font-semibold">
                              <span>操作动作</span>
                              <span>执行者 / 时间</span>
                            </div>
                            <div className="p-3 text-[11px] border-b border-slate-100 flex justify-between">
                              <span className="text-slate-800 font-mono">SELECT * FROM {tableId} LIMIT 10;</span>
                              <span className="text-slate-500">Admin_User (12分钟前)</span>
                            </div>
                            <div className="p-3 text-[11px] border-b border-slate-100 flex justify-between">
                              <span className="text-slate-800 font-mono">ALTER TABLE {tableId} ADD INDEX (created_at);</span>
                              <span className="text-slate-500">DBA_Operator (3小时前)</span>
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                );
              }

              if (activeTab.type === 'sql') {
                return (
                  <div className="hifi-sql-workspace hifi-tab-pane">
                    {/* Top Editor */}
                    <div className="hifi-sql-editor-container">
                      <div className="hifi-sql-editor-lines">
                        {Array.from({ length: 8 }).map((_, i) => <div key={i}>{i+1}</div>)}
                      </div>
                      <div className="hifi-sql-textarea-wrapper">
                        <textarea
                          className="hifi-sql-textarea"
                          value={sqlQuery}
                          onChange={(e) => setSqlQuery(e.target.value)}
                        />
                      </div>
                      <div className="hifi-sql-editor-actions">
                        <button className="hifi-sql-console-run-btn" onClick={() => {
                          setSqlResultsRun(true);
                          showToast("已成功执行 SQL 语句！");
                        }}>
                          <Play size={10} />
                          <span>运行 (F9)</span>
                        </button>
                        <button className="hifi-toolbar-btn" style={{ height: "24px" }} onClick={() => showToast("代码格式化完成")}>格式化</button>
                      </div>
                    </div>

                    {/* Bottom Console Panel */}
                    <div className="hifi-sql-output-pane">
                      <div className="hifi-sql-output-tabs">
                        <div 
                          className={`hifi-sql-output-tab ${sqlConsoleTab === 'results' ? 'active' : ''}`}
                          onClick={() => setSqlConsoleTab('results')}
                        >
                          查询结果 {sqlResultsRun && "(5行)"}
                        </div>
                        <div 
                          className={`hifi-sql-output-tab ${sqlConsoleTab === 'history' ? 'active' : ''}`}
                          onClick={() => setSqlConsoleTab('history')}
                        >
                          消息日志
                        </div>
                        <div 
                          className={`hifi-sql-output-tab ${sqlConsoleTab === 'ai-explain' ? 'active' : ''}`}
                          onClick={() => setSqlConsoleTab('ai-explain')}
                        >
                          AI 解释 SQL
                        </div>
                      </div>

                      <div className="hifi-sql-output-content">
                        {sqlConsoleTab === 'results' && (
                          sqlResultsRun ? (
                            <table className="hifi-table">
                              <thead>
                                <tr>
                                  <th>name</th>
                                  <th>comment_count</th>
                                </tr>
                              </thead>
                              <tbody>
                                <tr>
                                  <td>张三</td>
                                  <td>1,432</td>
                                </tr>
                                <tr>
                                  <td>李四</td>
                                  <td>980</td>
                                </tr>
                                <tr>
                                  <td>王五</td>
                                  <td>412</td>
                                </tr>
                              </tbody>
                            </table>
                          ) : (
                            <div className="text-slate-400 italic text-[11px] text-center mt-10">点击“运行”执行上方的查询语句并查看输出结果。</div>
                          )
                        )}

                        {sqlConsoleTab === 'history' && (
                          <div className="flex flex-col gap-1.5 font-mono text-[10px]">
                            <div className="text-emerald-600">[INFO] 14:15:32 - 数据库连接就绪 (prod-mysql)</div>
                            {sqlResultsRun && (
                              <div className="text-slate-800">[INFO] 14:16:05 - 执行成功，受影响行数: 3, 耗时: 12ms</div>
                            )}
                          </div>
                        )}

                        {sqlConsoleTab === 'ai-explain' && (
                          <div className="hifi-sql-ai-explain-card flex gap-2">
                            <Sparkles size={14} className="text-indigo-500 flex-shrink-0 mt-0.5" />
                            <div>
                              <strong className="block text-slate-800 mb-1">SQL 逻辑解释:</strong>
                              <span className="text-[10px] text-slate-600">这段 SQL 以 `id_users` 作为主表，使用 `LEFT JOIN` 关联 `comment_infos`，并对用户 ID 进行分组。通过 `COUNT(c.id)` 计算出每个用户的评论数，最终按照评论数进行降序排序。</span>
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                );
              }

              if (activeTab.type === 'multi-table') {
                const tables = activeTab.selectedTables || [];
                return (
                  <div className="hifi-multi-table-workspace hifi-tab-pane">
                    <div className="bg-[#EFF6FF] border border-[#BFDBFE] rounded-lg p-3 text-blue-800 flex items-center gap-3">
                      <GitMerge size={16} className="text-blue-600" />
                      <div>
                        <span className="font-semibold block text-[11px]">联合 Workspace ({tables.length} 张表)</span>
                        <span className="text-[10px] opacity-90">当前工作区已绑定表: {tables.join('，')}</span>
                      </div>
                    </div>

                    {/* Quick Recommended analysis prompts */}
                    <div className="grid grid-cols-2 gap-3">
                      <div className="border border-slate-200 rounded-lg p-3 bg-white hover:border-indigo-400 cursor-pointer" onClick={() => openQueryResultTab(`查询这 ${tables.length} 张表的关联性，并给出数据字典`)}>
                        <span className="font-semibold text-[11px] block mb-1">分析表关联拓扑图</span>
                        <span className="text-[10px] text-slate-500">计算表与表之间的物理键及逻辑外键联系。</span>
                      </div>
                      <div className="border border-slate-200 rounded-lg p-3 bg-white hover:border-indigo-400 cursor-pointer" onClick={() => openQueryResultTab(`统计所选表在最近一月的联合活动数据量`)}>
                        <span className="font-semibold text-[11px] block mb-1">联合数据趋势统计</span>
                        <span className="text-[10px] text-slate-500">分析用户、评论、流量记录的联合转化率。</span>
                      </div>
                    </div>

                    {/* Ask Area scoped to selected tables */}
                    <div className="border border-slate-200 rounded-xl p-3 mt-4 bg-slate-50">
                      <span className="text-[10px] text-slate-600 font-semibold block mb-2">针对选定的 {tables.length} 张表进行智能提问:</span>
                      <div className="flex gap-2">
                        <input
                          type="text"
                          className="hifi-guide-input flex-1 bg-white"
                          placeholder={`例如：帮我查询在 ${tables.slice(0,2).join('和')} 之间进行内连接关联的数据...`}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') {
                              openQueryResultTab((e.target as HTMLInputElement).value);
                              (e.target as HTMLInputElement).value = '';
                            }
                          }}
                        />
                        <button className="hifi-guide-btn-primary" onClick={() => showToast("智能建议已发送")}>联合分析</button>
                      </div>
                    </div>
                  </div>
                );
              }

              if (activeTab.type === 'query-result') {
                const queryText = activeTab.queryText || '';
                const msgs = activeTab.chatMessages || [];
                
                return (
                  <div className="hifi-query-result-workspace hifi-tab-pane">
                    <div className="hifi-query-result-header">
                      <div className="flex items-center gap-2 text-[10px] text-slate-500 mb-1">
                        <TrendingUp size={11} className="text-purple-500" />
                        <span>智能问数分析结果</span>
                      </div>
                      <h3 className="font-bold text-[12px] text-slate-800">“{queryText}”</h3>
                    </div>

                    <div className="hifi-query-result-messages">
                      {msgs.map(m => (
                        <div key={m.id} className={m.sender === 'user' ? 'hifi-user-bubble' : 'hifi-ai-msg-container'}>
                          {m.sender === 'ai' && (
                            <div className="hifi-ai-avatar">
                              <Sparkles size={11} />
                            </div>
                          )}
                          <div className={m.sender === 'ai' ? 'hifi-ai-msg-bubble' : ''}>
                            {m.text}
                          </div>
                        </div>
                      ))}

                      {/* Interactive Visualizations */}
                      <div className="hifi-ai-card mt-2">
                        <div className="hifi-ai-card-header flex justify-between items-center">
                          <span>数据趋势分析</span>
                          <span className="hifi-guide-chip-prod">LINE CHART</span>
                        </div>
                        <div className="hifi-ai-card-body p-3">
                          <svg viewBox="0 0 400 120" width="100%" height="100">
                            {/* Grid Lines */}
                            <line x1="30" y1="20" x2="380" y2="20" stroke="#F1F5F9" strokeWidth="1" />
                            <line x1="30" y1="50" x2="380" y2="50" stroke="#F1F5F9" strokeWidth="1" />
                            <line x1="30" y1="80" x2="380" y2="80" stroke="#F1F5F9" strokeWidth="1" />
                            <line x1="30" y1="100" x2="380" y2="100" stroke="#E2E8F0" strokeWidth="1.5" />

                            {/* Y-Axis */}
                            <text x="5" y="23" fontSize="8" fill="#64748B">1.5K</text>
                            <text x="10" y="53" fontSize="8" fill="#64748B">1K</text>
                            <text x="10" y="83" fontSize="8" fill="#64748B">500</text>
                            <text x="20" y="103" fontSize="8" fill="#64748B">0</text>

                            <defs>
                              <linearGradient id="glow-grad" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="0%" stopColor="#4F46E5" stopOpacity="0.25" />
                                <stop offset="100%" stopColor="#4F46E5" stopOpacity="0.0" />
                              </linearGradient>
                            </defs>
                            
                            <path 
                              d="M 30 100 Q 60 70 90 85 Q 130 40 160 90 Q 210 50 250 80 Q 300 30 380 60 L 380 100 Z" 
                              fill="url(#glow-grad)" 
                            />
                            <path 
                              d="M 30 100 Q 60 70 90 85 Q 130 40 160 90 Q 210 50 250 80 Q 300 30 380 60" 
                              fill="none" 
                              stroke="#4F46E5" 
                              strokeWidth="2.5" 
                            />

                            <circle cx="90" cy="85" r="3" fill="#FFFFFF" stroke="#4F46E5" strokeWidth="1.5" />
                            <circle cx="160" cy="90" r="3" fill="#FFFFFF" stroke="#4F46E5" strokeWidth="1.5" />
                            <circle cx="250" cy="80" r="3" fill="#FFFFFF" stroke="#4F46E5" strokeWidth="1.5" />
                            <circle cx="380" cy="60" r="3" fill="#FFFFFF" stroke="#4F46E5" strokeWidth="1.5" />
                          </svg>
                        </div>
                      </div>

                      {/* SQL Code Box */}
                      <div className="hifi-ai-card">
                        <div className="hifi-ai-card-header">
                          生成的 SQL 查询
                        </div>
                        <div className="hifi-ai-card-body">
                          <pre className="hifi-sql-card font-mono text-[10px] leading-relaxed p-3 text-slate-800">
{`SELECT 
  DATE(created_at) as date,
  count(id) as total_comments
FROM comment_infos
WHERE created_at >= CURDATE() - INTERVAL 7 DAY
GROUP BY DATE(created_at)
ORDER BY date;`}
                          </pre>
                          <div className="hifi-sql-card-action">
                            <button 
                              className="hifi-guide-btn-secondary flex items-center gap-1" 
                              style={{ height: "24px", fontSize: "10px" }}
                              onClick={() => {
                                setSqlQuery(`SELECT \n  DATE(created_at) as date,\n  count(id) as total_comments\nFROM comment_infos\nWHERE created_at >= CURDATE() - INTERVAL 7 DAY\nGROUP BY DATE(created_at)\nORDER BY date;`);
                                openSqlConsole();
                              }}
                            >
                              <Terminal size={10} />
                              在 SQL 工作台打开
                            </button>
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Sticky Footer Continue Input */}
                    <div className="hifi-query-result-footer">
                      <div className="hifi-chat-input-wrapper">
                        <input
                          type="text"
                          className="hifi-chat-input"
                          placeholder="针对此问数结果继续追问..."
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') {
                              handleQueryResultChatSend(activeTab.id, (e.target as HTMLInputElement).value);
                              (e.target as HTMLInputElement).value = '';
                            }
                          }}
                        />
                        <button className="hifi-chat-send-btn">
                          <Send size={13} />
                        </button>
                      </div>
                    </div>
                  </div>
                );
              }
            })()}
          </section>

          {/* COLUMN 3: COLLAPSIBLE RIGHT DRAWER (AI SUGGEST / SPECT TOKENS / PROPS) */}
          <section className={`hifi-right-drawer ${rightDrawerOpen ? 'open' : 'closed'}`}>
            <div className="h-full flex flex-col overflow-auto">
              
              {/* Header inside drawer */}
              <div className="hifi-assistant-header border-b border-slate-200 p-3 flex-shrink-0 flex justify-between items-center bg-slate-50">
                <span className="hifi-assistant-title flex items-center gap-1.5 font-bold text-[12px]">
                  {rightDrawerType === 'specs' && <><Layers size={13} className="text-indigo-600" /> 设计规范</>}
                  {rightDrawerType === 'ai-suggest' && <><Sparkles size={13} className="text-purple-600" /> AI 建议</>}
                  {rightDrawerType === 'props' && <><Info size={13} className="text-blue-600" /> 对象属性</>}
                </span>
                <X size={12} className="cursor-pointer text-slate-400 hover:text-slate-600" onClick={() => setRightDrawerOpen(false)} />
              </div>

              {/* Drawer Content */}
              <div className="flex-1 overflow-auto p-3.5">
                {rightDrawerType === 'specs' && (
                  <div className="hifi-guide-panel p-0 border-none shadow-none">
                    {/* COLOR SYSTEM */}
                    <div className="hifi-guide-section mb-4">
                      <span className="hifi-guide-subtitle block font-semibold mb-2">色彩体系</span>
                      
                      <div className="hifi-color-row flex justify-between text-[11px] mb-1.5">
                        <div className="hifi-color-info flex items-center gap-2">
                          <div className="hifi-color-dot w-3 h-3 rounded-full" style={{ background: "#4F46E5" }}></div>
                          <span>主色/AI</span>
                        </div>
                        <span className="font-mono text-slate-400">#4F46E5</span>
                      </div>

                      <div className="hifi-color-row flex justify-between text-[11px] mb-1.5">
                        <div className="hifi-color-info flex items-center gap-2">
                          <div className="hifi-color-dot w-3 h-3 rounded-full" style={{ background: "#7C3AED" }}></div>
                          <span>辅助色</span>
                        </div>
                        <span className="font-mono text-slate-400">#7C3AED</span>
                      </div>

                      <div className="hifi-color-row flex justify-between text-[11px] mb-1.5">
                        <div className="hifi-color-info flex items-center gap-2">
                          <div className="hifi-color-dot w-3 h-3 rounded-full" style={{ background: "#2563EB" }}></div>
                          <span>信息色</span>
                        </div>
                        <span className="font-mono text-slate-400">#2563EB</span>
                      </div>

                      <div className="hifi-color-row flex justify-between text-[11px] mb-1.5">
                        <div className="hifi-color-info flex items-center gap-2">
                          <div className="hifi-color-dot w-3 h-3 rounded-full" style={{ background: "#16A34A" }}></div>
                          <span>成功色</span>
                        </div>
                        <span className="font-mono text-slate-400">#16A34A</span>
                      </div>
                    </div>

                    {/* COMPONENT STYLES */}
                    <div className="hifi-guide-section mb-4">
                      <span className="hifi-guide-subtitle block font-semibold mb-2">组件风格</span>
                      <div className="flex flex-col gap-1.5">
                        <button className="hifi-guide-btn-primary py-1 text-[10px] w-full">主按钮</button>
                        <button className="hifi-guide-btn-secondary py-1 text-[10px] w-full">次按钮</button>
                      </div>
                      <div className="flex gap-2 mt-2">
                        <span className="hifi-guide-chip-prod">PROD</span>
                        <span className="hifi-guide-chip-test">TEST</span>
                      </div>
                    </div>

                    {/* HOVER STATUS */}
                    <div className="hifi-guide-section">
                      <span className="hifi-guide-subtitle block font-semibold mb-2">交互状态示例</span>
                      <div className="flex gap-2">
                        <div className="hifi-hover-demo-btn hover text-[10px] flex-1 py-1">悬浮态</div>
                        <div className="hifi-hover-demo-btn default text-[10px] flex-1 py-1">默认态</div>
                      </div>
                    </div>
                  </div>
                )}

                {rightDrawerType === 'ai-suggest' && (
                  <div className="flex flex-col gap-3">
                    <span className="text-[10px] text-slate-400 uppercase block mb-1">数据库诊断建议</span>
                    
                    <div className="border border-purple-200 bg-purple-50/60 rounded-xl p-3 text-purple-900">
                      <div className="flex items-center gap-1.5 font-bold text-[11px] mb-1 text-purple-800">
                        <Sparkles size={12} />
                        <span>性能索引推荐</span>
                      </div>
                      <p className="text-[10px] leading-relaxed mb-2 opacity-90">检测到表 `comment_infos` 的字段 `user_id` 在联合查询中执行了大量全表扫描，建议立即为其创建单列索引。</p>
                      <button 
                        className="bg-purple-600 hover:bg-purple-700 text-white rounded text-[9px] font-semibold px-2 py-0.5"
                        onClick={() => {
                          setSqlQuery(`ALTER TABLE comment_infos ADD INDEX idx_user_id (user_id);`);
                          openSqlConsole();
                        }}
                      >
                        生成并运行 DDL
                      </button>
                    </div>

                    <div className="border border-amber-200 bg-amber-50/60 rounded-xl p-3 text-amber-900">
                      <div className="flex items-center gap-1.5 font-bold text-[11px] mb-1 text-amber-800">
                        <Info size={12} />
                        <span>多租户结构警告</span>
                      </div>
                      <p className="text-[10px] leading-relaxed opacity-90">数据表 `id_users` 与 `id_organizations` 缺少一致的联合主键 `tenant_id`，建议补充主键以确保多租户隔离层级正确。</p>
                    </div>
                  </div>
                )}

                {rightDrawerType === 'props' && (
                  <div className="flex flex-col gap-2 font-mono text-[10px] text-slate-700">
                    <span className="text-[10px] font-sans text-slate-400 uppercase block mb-1.5">当前对象物理属性</span>
                    
                    {(() => {
                      const activeTab = tabs.find(t => t.id === activeTabId) || tabs[0];
                      if (activeTab.type === 'table') {
                        const tableId = activeTab.tableId || 'id_users';
                        return (
                          <div className="flex flex-col gap-2">
                            <div className="flex justify-between border-b border-slate-100 pb-1.5">
                              <span className="text-slate-400">物理表名:</span>
                              <span className="font-semibold text-slate-900">{tableId}</span>
                            </div>
                            <div className="flex justify-between border-b border-slate-100 pb-1.5">
                              <span className="text-slate-400">预估行数:</span>
                              <span className="text-slate-900 font-sans font-semibold">12,345 Rows</span>
                            </div>
                            <div className="flex justify-between border-b border-slate-100 pb-1.5">
                              <span className="text-slate-400">物理大小:</span>
                              <span className="text-slate-900 font-sans font-semibold">2.48 MB</span>
                            </div>
                            <div className="flex justify-between border-b border-slate-100 pb-1.5">
                              <span className="text-slate-400">存储引擎:</span>
                              <span className="text-slate-900">InnoDB</span>
                            </div>
                            <div className="flex justify-between border-b border-slate-100 pb-1.5">
                              <span className="text-slate-400">创建时间:</span>
                              <span className="text-slate-900 font-sans">2024-11-16</span>
                            </div>
                          </div>
                        );
                      } else if (activeTab.type === 'sql') {
                        return (
                          <div className="flex flex-col gap-2">
                            <div className="flex justify-between border-b border-slate-100 pb-1.5">
                              <span className="text-slate-400">连接名称:</span>
                              <span className="text-slate-900">prod-mysql</span>
                            </div>
                            <div className="flex justify-between border-b border-slate-100 pb-1.5">
                              <span className="text-slate-400">会话端口:</span>
                              <span className="text-slate-900 font-sans">3306</span>
                            </div>
                            <div className="flex justify-between border-b border-slate-100 pb-1.5">
                              <span className="text-slate-400">事务模式:</span>
                              <span className="text-slate-900 text-emerald-600 font-sans font-semibold">AUTO-COMMIT</span>
                            </div>
                          </div>
                        );
                      } else {
                        return (
                          <div className="flex flex-col gap-2">
                            <div className="flex justify-between border-b border-slate-100 pb-1.5">
                              <span className="text-slate-400">上下文关联:</span>
                              <span className="text-slate-900 font-sans">{contextTables.length} 张表</span>
                            </div>
                            <div className="flex justify-between border-b border-slate-100 pb-1.5">
                              <span className="text-slate-400">激活大模型:</span>
                              <span className="text-slate-900">DeepSeek-Coder-V2</span>
                            </div>
                            <div className="flex justify-between border-b border-slate-100 pb-1.5">
                              <span className="text-slate-400">会话ID:</span>
                              <span className="text-slate-900 font-sans text-xs">caae-f483-d1e4</span>
                            </div>
                          </div>
                        );
                      }
                    })()}
                  </div>
                )}
              </div>
            </div>
          </section>
        </main>
      </div>

      {/* DYNAMIC RIGHT-CLICK CONTEXT MENU OVERLAY */}
      {contextMenu.visible && (
        <div 
          className="hifi-context-menu"
          style={{ left: `${contextMenu.x}px`, top: `${contextMenu.y}px` }}
          onClick={(e) => e.stopPropagation()}
        >
          {contextMenu.type === 'database' && (
            <>
              <div className="hifi-context-menu-item" onClick={() => { openSqlConsole(); setContextMenu(prev => ({ ...prev, visible: false })); }}>
                <Terminal size={11} className="text-slate-500" />
                <span>打开 SQL 控制台</span>
              </div>
              <div className="hifi-context-menu-item" onClick={() => { showToast("连接刷新中..."); setContextMenu(prev => ({ ...prev, visible: false })); }}>
                <RefreshCw size={11} className="text-slate-500" />
                <span>刷新数据源</span>
              </div>
              <div className="hifi-context-menu-divider"></div>
              <div className="hifi-context-menu-item" onClick={() => { showToast("物理连接测试成功 (MySQL 8.0)"); setContextMenu(prev => ({ ...prev, visible: false })); }}>
                <Check size={11} className="text-emerald-500" />
                <span>测试物理连接</span>
              </div>
              <div className="hifi-context-menu-item" onClick={() => { toggleRightDrawer('props'); setContextMenu(prev => ({ ...prev, visible: false })); }}>
                <Info size={11} className="text-slate-500" />
                <span>查看数据源属性</span>
              </div>
            </>
          )}

          {contextMenu.type === 'schema' && (
            <>
              <div className="hifi-context-menu-item" onClick={() => { openSqlConsole(); setContextMenu(prev => ({ ...prev, visible: false })); }}>
                <Terminal size={11} className="text-slate-500" />
                <span>新建 SQL Console</span>
              </div>
              <div className="hifi-context-menu-item" onClick={() => { openTableTab("id_users", "schema"); setContextMenu(prev => ({ ...prev, visible: false })); }}>
                <FileText size={11} className="text-slate-500" />
                <span>查看所有表结构</span>
              </div>
              <div className="hifi-context-menu-item" onClick={() => { openTableTab("id_users", "er"); setContextMenu(prev => ({ ...prev, visible: false })); }}>
                <GitMerge size={11} className="text-slate-500" />
                <span>生成库级 ER 图</span>
              </div>
              <div className="hifi-context-menu-divider"></div>
              <div className="hifi-context-menu-item" onClick={() => { showToast("架构缓存已刷新"); setContextMenu(prev => ({ ...prev, visible: false })); }}>
                <RefreshCw size={11} className="text-slate-500" />
                <span>刷新 Schema</span>
              </div>
            </>
          )}

          {contextMenu.type === 'table' && (
            <>
              <div className="hifi-context-menu-item" onClick={() => { openTableTab(contextMenu.targetNode, 'preview'); setContextMenu(prev => ({ ...prev, visible: false })); }}>
                <FileText size={11} className="text-slate-500" />
                <span>预览表数据</span>
              </div>
              <div className="hifi-context-menu-item" onClick={() => { openTableTab(contextMenu.targetNode, 'schema'); setContextMenu(prev => ({ ...prev, visible: false })); }}>
                <Info size={11} className="text-slate-500" />
                <span>查看表字段结构</span>
              </div>
              <div className="hifi-context-menu-item" onClick={() => { addContextTable(contextMenu.targetNode); setContextMenu(prev => ({ ...prev, visible: false })); }}>
                <Sparkles size={11} className="text-indigo-500" />
                <span>作为问数上下文</span>
              </div>
              <div className="hifi-context-menu-item" onClick={() => { openTableTab(contextMenu.targetNode, 'er'); setContextMenu(prev => ({ ...prev, visible: false })); }}>
                <GitMerge size={11} className="text-slate-500" />
                <span>生成表级 ER 关系图</span>
              </div>
              <div className="hifi-context-menu-divider"></div>
              <div className="hifi-context-menu-item" onClick={() => {
                navigator.clipboard.writeText(contextMenu.targetNode);
                showToast(`已成功复制表名: ${contextMenu.targetNode}`);
                setContextMenu(prev => ({ ...prev, visible: false }));
              }}>
                <Copy size={11} className="text-slate-500" />
                <span>复制物理表名</span>
              </div>
              <div className="hifi-context-menu-item danger" onClick={() => {
                if (window.confirm(`确认执行 DROP TABLE ${contextMenu.targetNode}？此操作将清除全表物理数据！`)) {
                  showToast(`已成功物理删除表 ${contextMenu.targetNode}`);
                }
                setContextMenu(prev => ({ ...prev, visible: false }));
              }}>
                <Trash2 size={11} />
                <span>物理删除表</span>
              </div>
            </>
          )}

          {contextMenu.type === 'multi-table' && (
            <>
              <div className="hifi-context-menu-item font-semibold text-slate-800" onClick={() => { openMultiTableWorkspace(selectedTables); setContextMenu(prev => ({ ...prev, visible: false })); }}>
                <GitMerge size={11} className="text-orange-500" />
                <span>作为联合 Workspace 打开</span>
              </div>
              <div className="hifi-context-menu-item" onClick={() => {
                setContextTables(selectedTables);
                setTabs(prev => {
                  if (prev.some(t => t.id === 'smart-query')) return prev;
                  return [...prev, { id: 'smart-query', title: '问数工作台', type: 'smart-query' }];
                });
                setActiveTabId('smart-query');
                showToast(`已将 ${selectedTables.length} 张表载入问数上下文`);
                setContextMenu(prev => ({ ...prev, visible: false }));
              }}>
                <Sparkles size={11} className="text-purple-500" />
                <span>基于选择的多表智能问数</span>
              </div>
              <div className="hifi-context-menu-item" onClick={() => {
                openTableTab(selectedTables[0], 'er');
                showToast("已基于多表拓扑关系生成关系图");
                setContextMenu(prev => ({ ...prev, visible: false }));
              }}>
                <Layers size={11} className="text-blue-500" />
                <span>生成选定表联合 ER 图</span>
              </div>
              <div className="hifi-context-menu-divider"></div>
              <div className="hifi-context-menu-item" onClick={() => { setSelectedTables([]); setContextMenu(prev => ({ ...prev, visible: false })); }}>
                <X size={11} className="text-slate-500" />
                <span>取消选择</span>
              </div>
            </>
          )}
        </div>
      )}

      {/* TOAST SYSTEM */}
      {toastMsg && (
        <div className="hifi-toast">
          <Sparkles size={12} className="text-yellow-400" />
          <span>{toastMsg}</span>
        </div>
      )}
    </div>
  );
}

// MOCK CHECK COMPONENT
function Check({ size, className }: { size?: number; className?: string }) {
  return (
    <svg 
      xmlns="http://www.w3.org/2000/svg" 
      viewBox="0 0 24 24" 
      fill="none" 
      stroke="currentColor" 
      strokeWidth="2.5" 
      strokeLinecap="round" 
      strokeLinejoin="round" 
      className={className} 
      style={{ width: size, height: size }}
    >
      <polyline points="20 6 9 17 4 12" />
    </svg>
  );
}
