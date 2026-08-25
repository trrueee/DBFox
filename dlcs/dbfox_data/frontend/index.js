const DLC_ID = "dbfox.data";
const TABLE_VIEW_TYPE = "dbfox.data.catalog-table";
const SQL_VIEW_TYPE = "dbfox.data.sql-console";

let host;
let React;
let dialogProjectId = null;
const groupsByProject = new Map();
const loadedProjects = new Set();
const expandedProfiles = new Set();
const expandedDatabases = new Set();
const focusedDatabaseByProject = new Map();
const catalogByDatabase = new Map();
const catalogLoading = new Set();
const catalogErrors = new Map();
const tableStateByKey = new Map();
const sqlStateByKey = new Map();
const listeners = new Set();

function emit() {
  for (const listener of listeners) listener();
}

function useVersion() {
  const [, setVersion] = React.useState(0);
  React.useEffect(() => {
    const listener = () => setVersion((value) => value + 1);
    listeners.add(listener);
    return () => listeners.delete(listener);
  }, []);
}

function ensureStylesheet() {
  if (typeof document === "undefined") return;
  const href = new URL("./index.css", import.meta.url).href;
  if (document.querySelector(`link[data-dbfox-dlc="${DLC_ID}"][href="${href}"]`)) return;
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = href;
  link.dataset.dbfoxDlc = DLC_ID;
  document.head.appendChild(link);
}

async function loadProfiles(projectId) {
  const result = await host.operations.invoke("profiles.list", {}, { projectId });
  const groups = Array.isArray(result?.profiles) ? result.profiles : [];
  groupsByProject.set(projectId, groups);
  loadedProjects.add(projectId);
  for (const group of groups) {
    if (!expandedProfiles.has(`${projectId}:${group.profile.id}`)) {
      expandedProfiles.add(`${projectId}:${group.profile.id}`);
    }
  }
  emit();
  return groups;
}

function providerLabel(provider) {
  if (provider === "postgresql") return "PostgreSQL";
  if (provider === "sqlite") return "SQLite";
  return "MySQL";
}

function databaseKey(projectId, databaseId) {
  return `${projectId}:${databaseId}`;
}

async function loadCatalog(projectId, databaseId, options = {}) {
  const { refresh = false, cursor = null, append = false } = options;
  const key = databaseKey(projectId, databaseId);
  catalogLoading.add(key);
  catalogErrors.delete(key);
  emit();
  try {
    if (refresh) {
      await host.operations.invoke("catalog.refresh", { database_id: databaseId }, { projectId });
    }
    const result = await host.operations.invoke("catalog.tables", {
      database_id: databaseId,
      limit: 100,
      cursor,
    }, { projectId });
    if (append) {
      const previous = catalogByDatabase.get(key);
      const previousTables = Array.isArray(previous?.tables) ? previous.tables : [];
      catalogByDatabase.set(key, {
        ...result,
        tables: [...previousTables, ...(Array.isArray(result?.tables) ? result.tables : [])],
      });
    } else {
      catalogByDatabase.set(key, result);
    }
  } catch (reason) {
    catalogErrors.set(key, reason instanceof Error ? reason.message : "读取数据库目录失败。");
    throw reason;
  } finally {
    catalogLoading.delete(key);
    emit();
  }
}

function openSqlConsole(projectId, database) {
  const stateKey = `${projectId}:${database.id}`;
  if (!sqlStateByKey.has(stateKey)) {
    sqlStateByKey.set(stateKey, {
      projectId,
      database,
      sql: "",
      sessionId: null,
      result: null,
    });
  }
  host.dockViews.open({
    viewKey: `data-sql:${stateKey}`,
    viewType: SQL_VIEW_TYPE,
    title: `${database.display_name} · SQL`,
    closeable: true,
    projectId,
    target: { type: "resource", kind: "dbfox.data.database", id: database.id },
    stateKey,
  });
}

function openTable(projectId, database, table) {
  const stateKey = `${projectId}:${database.id}:${table.table_id}`;
  tableStateByKey.set(stateKey, { projectId, database, table });
  host.dockViews.open({
    viewKey: `data-table:${stateKey}`,
    viewType: TABLE_VIEW_TYPE,
    title: table.qualified_name,
    closeable: true,
    projectId,
    target: { type: "resource", kind: "dbfox.data.database", id: database.id },
    stateKey,
  });
}

function ConnectionDialog({ projectId }) {
  const [provider, setProvider] = React.useState("mysql");
  const [name, setName] = React.useState("");
  const [hostName, setHostName] = React.useState("");
  const [port, setPort] = React.useState("3306");
  const [database, setDatabase] = React.useState("");
  const [username, setUsername] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [environment, setEnvironment] = React.useState("dev");
  const [readOnly, setReadOnly] = React.useState(false);
  const [advanced, setAdvanced] = React.useState(false);
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState("");

  function close() {
    if (saving) return;
    dialogProjectId = null;
    emit();
  }

  function selectProvider(value) {
    setProvider(value);
    setPort(value === "postgresql" ? "5432" : value === "mysql" ? "3306" : "");
    setError("");
  }

  async function save(event) {
    event.preventDefault();
    const profileName = name.trim();
    const databaseName = database.trim();
    if (!profileName || !databaseName) {
      setError("请填写连接名称和数据库。");
      return;
    }
    if (provider !== "sqlite" && (!hostName.trim() || !username.trim() || !password)) {
      setError("网络数据库需要 Host、用户名和密码。");
      return;
    }
    setSaving(true);
    setError("");
    try {
      let passwordRef = null;
      let leaseId;
      if (provider !== "sqlite") {
        const enrollment = await host.credentials.enrollBatch([
          { kind: "datasource_password", secret: password },
        ]);
        passwordRef = enrollment.credentials[0]?.id || null;
        leaseId = enrollment.lease_id;
      }
      await host.operations.invoke("profiles.create", {
        name: profileName,
        provider,
        host: provider === "sqlite" ? null : hostName.trim(),
        port: provider === "sqlite" ? null : Number(port),
        username: provider === "sqlite" ? null : username.trim(),
        password_credential_ref: passwordRef,
        is_read_only: readOnly,
        environment,
        initial_database_name: databaseName,
        initial_database_display_name: databaseName.split(/[\\/]/).pop() || databaseName,
      }, { projectId, credentialLeaseId: leaseId });
      await loadProfiles(projectId);
      dialogProjectId = null;
      emit();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "保存连接失败。");
    } finally {
      setSaving(false);
    }
  }

  const field = (label, input) => React.createElement("label", { className: "dbfox-data-dialog__field" },
    React.createElement("span", null, label), input);
  const input = (props) => React.createElement("input", { className: "dbfox-data-dialog__input", ...props });

  return React.createElement("div", { className: "dbfox-data-dialog__backdrop", role: "presentation", onMouseDown: (event) => event.target === event.currentTarget && close() },
    React.createElement("form", { className: "dbfox-data-dialog", role: "dialog", "aria-modal": true, "aria-labelledby": "dbfox-data-dialog-title", onSubmit: (event) => void save(event) },
      React.createElement("header", { className: "dbfox-data-dialog__header" },
        React.createElement("div", null,
          React.createElement("h2", { id: "dbfox-data-dialog-title" }, "新建数据库连接"),
          React.createElement("p", null, "连接配置保存在当前 Project；密码只进入系统凭据库。")),
        React.createElement("button", { type: "button", className: "dbfox-data-dialog__close", onClick: close, "aria-label": "关闭" }, "×")),
      React.createElement("div", { className: "dbfox-data-dialog__body" },
        React.createElement("div", { className: "dbfox-data-dialog__providers", role: "radiogroup", "aria-label": "数据库类型" },
          ["mysql", "postgresql", "sqlite"].map((value) => React.createElement("button", {
            key: value, type: "button", role: "radio", "aria-checked": provider === value,
            className: provider === value ? "is-selected" : "", onClick: () => selectProvider(value),
          }, providerLabel(value)))),
        field("连接名称", input({ value: name, onChange: (event) => setName(event.target.value), placeholder: "Production MySQL", autoFocus: true })),
        provider === "sqlite"
          ? field("SQLite 文件", input({ value: database, onChange: (event) => setDatabase(event.target.value), placeholder: "D:\\data\\app.sqlite3" }))
          : React.createElement(React.Fragment, null,
              React.createElement("div", { className: "dbfox-data-dialog__grid dbfox-data-dialog__grid--host" },
                field("主机地址", input({ value: hostName, onChange: (event) => setHostName(event.target.value), placeholder: "db.example.com" })),
                field("端口", input({ value: port, onChange: (event) => setPort(event.target.value), inputMode: "numeric" }))),
              React.createElement("div", { className: "dbfox-data-dialog__grid" },
                field("数据库", input({ value: database, onChange: (event) => setDatabase(event.target.value), placeholder: "billing" })),
                field("用户名", input({ value: username, onChange: (event) => setUsername(event.target.value), placeholder: "analyst" }))),
              field("密码", input({ value: password, onChange: (event) => setPassword(event.target.value), type: "password", autoComplete: "new-password" }))),
        React.createElement("button", { type: "button", className: "dbfox-data-dialog__disclosure", "aria-expanded": advanced, onClick: () => setAdvanced((value) => !value) }, `${advanced ? "⌄" : "›"} 连接选项`),
        advanced ? React.createElement("div", { className: "dbfox-data-dialog__advanced" },
          field("环境", React.createElement("select", { className: "dbfox-data-dialog__input", value: environment, onChange: (event) => setEnvironment(event.target.value) },
            [["dev", "开发"], ["test", "测试"], ["staging", "预发布"], ["prod", "生产"]].map(([value, label]) => React.createElement("option", { key: value, value }, label)))),
          React.createElement("label", { className: "dbfox-data-dialog__check" }, input({ type: "checkbox", checked: readOnly, onChange: (event) => setReadOnly(event.target.checked) }), "只读模式")) : null,
        error ? React.createElement("p", { className: "dbfox-data-dialog__error", role: "alert" }, error) : null),
      React.createElement("footer", { className: "dbfox-data-dialog__footer" },
        React.createElement("button", { type: "button", className: "dbfox-data-dialog__button", onClick: close }, "取消"),
        React.createElement("button", { type: "submit", className: "dbfox-data-dialog__button is-primary", disabled: saving }, saving ? "正在保存…" : "保存连接")))
  );
}

function formatSql(raw) {
  if (!raw || !raw.trim()) return raw;
  const keywords = ["SELECT", "FROM", "WHERE", "GROUP BY", "ORDER BY", "HAVING", "LIMIT", "LEFT JOIN", "RIGHT JOIN", "INNER JOIN", "JOIN", "UNION", "VALUES", "SET", "INSERT INTO", "UPDATE", "DELETE FROM"];
  let formatted = raw.trim();
  for (const kw of keywords) {
    const regex = new RegExp(`\\b${kw}\\b`, "gi");
    formatted = formatted.replace(regex, (match) => `\n${match.toUpperCase()}`);
  }
  return formatted.split("\n").map((line) => line.trim()).filter(Boolean).join("\n  ").replace(/^  /, "");
}

function DatabaseRow({ projectId, database }) {
  useVersion();
  const key = databaseKey(projectId, database.id);
  const focused = focusedDatabaseByProject.get(projectId) === database.id;
  const expanded = expandedDatabases.has(key);
  const catalog = catalogByDatabase.get(key);
  const tables = Array.isArray(catalog?.tables) ? catalog.tables : [];
  const loading = catalogLoading.has(key);
  const error = catalogErrors.get(key);

  async function toggleDatabase() {
    focusedDatabaseByProject.set(projectId, database.id);
    if (expanded) {
      expandedDatabases.delete(key);
      emit();
      return;
    }
    expandedDatabases.add(key);
    emit();
    if (!catalog && !loading) await loadCatalog(projectId, database.id).catch(() => undefined);
  }

  return React.createElement("div", {
    className: "dbfox-data__database",
    role: "treeitem",
    "aria-selected": focused,
    "aria-expanded": expanded,
  },
    React.createElement("div", { className: `dbfox-data__database-row ${focused ? "is-focused" : ""}` },
      React.createElement("button", {
        type: "button",
        className: "dbfox-data__sql",
        onClick: (event) => {
          event.stopPropagation();
          openSqlConsole(projectId, database);
        },
        title: "打开 SQL Console",
        "aria-label": `打开 SQL Console：${database.display_name}`,
      }, ">_"),
      React.createElement("button", {
        type: "button",
        className: "dbfox-data__database-focus",
        onClick: () => void toggleDatabase(),
        title: database.database_name,
      },
      React.createElement("span", { className: `dbfox-data__chevron ${expanded ? "is-expanded" : ""}`, "aria-hidden": true }, "›"),
      React.createElement("span", { className: "dbfox-data__database-icon", "aria-hidden": true }, "◉"),
      React.createElement("span", { className: "dbfox-data__label" }, database.display_name)),
      React.createElement("button", {
        type: "button",
        className: "dbfox-data__refresh",
        onClick: (event) => {
          event.stopPropagation();
          expandedDatabases.add(key);
          void loadCatalog(projectId, database.id, { refresh: true }).catch(() => undefined);
        },
        disabled: loading,
        title: "刷新数据库目录",
        "aria-label": `刷新数据库目录：${database.display_name}`,
      }, "↻")),
    expanded ? React.createElement("div", { className: "dbfox-data__tables", role: "group" },
      loading ? React.createElement("p", { className: "dbfox-data__status" }, "正在读取目录…") : null,
      error ? React.createElement("p", { className: "dbfox-data__catalog-error", role: "alert" }, "数据库目录暂时不可用。") : null,
      !loading && !error && catalog?.catalog_status === "uninitialized"
        ? React.createElement("div", { className: "dbfox-data__catalog-empty" },
            React.createElement("span", null, "目录尚未刷新。"),
            React.createElement("button", {
              type: "button",
              onClick: () => void loadCatalog(projectId, database.id, { refresh: true }).catch(() => undefined),
            }, "刷新目录")) : null,
      !loading && !error ? tables.map((table) => React.createElement("button", {
        key: table.table_id,
        type: "button",
        className: "dbfox-data__table-row",
        onClick: () => openTable(projectId, database, table),
        title: table.qualified_name,
      },
      React.createElement("span", { className: "dbfox-data__table-icon", "aria-hidden": true }, "▦"),
      React.createElement("span", { className: "dbfox-data__label" }, table.qualified_name),
      React.createElement("span", { className: "dbfox-data__count" }, table.columns_count))) : null,
      !loading && !error && catalog?.catalog_status === "ready" && tables.length === 0
        ? React.createElement("p", { className: "dbfox-data__status" }, "这个数据库没有可浏览的数据表。") : null,
      !loading && !error && catalog?.has_more && catalog?.next_cursor
        ? React.createElement("button", {
            type: "button",
            className: "dbfox-data__load-more",
            onClick: () => void loadCatalog(projectId, database.id, {
              cursor: catalog.next_cursor,
              append: true,
            }).catch(() => undefined),
          }, "加载更多") : null,
    ) : null);
}

function ResultGrid({ columns, rows, emptyLabel = "没有返回数据。", onCellSelect }) {
  const [selectedCell, setSelectedCell] = React.useState(null);
  const [sortColumn, setSortColumn] = React.useState(null);
  const [sortAsc, setSortAsc] = React.useState(true);

  const sortedRows = React.useMemo(() => {
    if (!Array.isArray(rows) || rows.length === 0) return [];
    if (!sortColumn) return rows;
    return [...rows].sort((a, b) => {
      const valA = a?.[sortColumn];
      const valB = b?.[sortColumn];
      if (valA === valB) return 0;
      if (valA == null) return 1;
      if (valB == null) return -1;
      const comp = valA < valB ? -1 : 1;
      return sortAsc ? comp : -comp;
    });
  }, [rows, sortColumn, sortAsc]);

  if (!Array.isArray(rows) || rows.length === 0) {
    return React.createElement("p", { className: "dbfox-data-result__empty" }, emptyLabel);
  }

  function handleHeaderClick(col) {
    if (sortColumn === col) {
      setSortAsc((prev) => !prev);
    } else {
      setSortColumn(col);
      setSortAsc(true);
    }
  }

  return React.createElement("div", { className: "dbfox-data-result__scroll" },
    React.createElement("table", null,
      React.createElement("thead", null, React.createElement("tr", null,
        React.createElement("th", { className: "dbfox-data-result__row-num" }, "#"),
        columns.map((column) => React.createElement("th", {
          key: column,
          onClick: () => handleHeaderClick(column),
          className: sortColumn === column ? "is-sorted" : "",
          title: `按 ${column} ${sortColumn === column && sortAsc ? "降序" : "升序"} 排列`,
        }, column, sortColumn === column ? (sortAsc ? " ↑" : " ↓") : "")))),
      React.createElement("tbody", null, sortedRows.map((row, index) => React.createElement("tr", { key: index },
        React.createElement("td", { className: "dbfox-data-result__row-num" }, index + 1),
        columns.map((column) => {
          const isSelected = selectedCell?.row === index && selectedCell?.col === column;
          const val = row?.[column];
          const displayVal = val === null ? "NULL" : String(val ?? "");
          return React.createElement("td", {
            key: column,
            className: `${isSelected ? "is-selected" : ""} ${val === null ? "is-null" : ""}`,
            onClick: () => {
              setSelectedCell({ row: index, col: column, value: val });
              onCellSelect?.({ column, value: val, row });
            },
          }, displayVal);
        }))))));
}

function SqlBlock({
  block,
  index,
  total,
  projectId,
  database,
  sessionId,
  onUpdate,
  onExecute,
  onDelete,
}) {
  const textareaRef = React.useRef(null);
  const lines = (block.sql || "").split("\n");
  const lineCount = Math.max(lines.length, 1);

  function handleExplain() {
    const statement = (block.sql || "").trim();
    if (!statement) return;
    const explainSql = statement.toUpperCase().startsWith("EXPLAIN") ? statement : `EXPLAIN ${statement}`;
    onUpdate({ ...block, sql: explainSql });
    onExecute(block.id, explainSql);
  }

  const columns = Array.isArray(block.result?.columns) ? block.result.columns : [];
  const rows = Array.isArray(block.result?.rows) ? block.result.rows : [];

  return React.createElement("div", { className: "dbfox-data-block", key: block.id },
    React.createElement("div", { className: "dbfox-data-block__header" },
      React.createElement("div", { className: "dbfox-data-block__badge-group" },
        React.createElement("span", { className: "dbfox-data-block__badge" }, `SQL #${index + 1}`),
        React.createElement("span", { className: "dbfox-data-block__hint-text" }, "查询语句")),
      React.createElement("div", { className: "dbfox-data-block__toolbar" },
        React.createElement("button", {
          type: "button",
          className: "dbfox-data-block__btn is-primary",
          disabled: block.running || !(block.sql || "").trim(),
          onClick: () => onExecute(block.id),
          title: "运行此语句 (Ctrl/⌘ + Enter)",
        }, block.running ? "执行中…" : "▶ 运行"),
        React.createElement("button", {
          type: "button",
          className: "dbfox-data-block__btn",
          disabled: block.running || !(block.sql || "").trim(),
          onClick: handleExplain,
          title: "分析执行计划 (EXPLAIN)",
        }, "Explain"),
        total > 1 ? React.createElement("button", {
          type: "button",
          className: "dbfox-data-block__btn is-danger",
          onClick: () => onDelete(block.id),
          title: "移除此查询",
        }, "✕") : null)),

    React.createElement("div", { className: "dbfox-data-block__editor-row" },
      React.createElement("div", { className: "dbfox-data-block__gutter", "aria-hidden": true },
        Array.from({ length: lineCount }, (_, i) => React.createElement("span", { key: i + 1 }, i + 1))),
      React.createElement("textarea", {
        ref: textareaRef,
        value: block.sql,
        rows: Math.max(Math.min(lineCount, 16), 2),
        spellCheck: false,
        autoCapitalize: "off",
        placeholder: "输入只读 SELECT 查询，按 Ctrl/⌘ + Enter 运行…",
        "aria-label": `查询语句 #${index + 1}`,
        onChange: (event) => onUpdate({ ...block, sql: event.target.value }),
        onKeyDown: (event) => {
          if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
            event.preventDefault();
            onExecute(block.id);
          }
        },
      })),

    block.running ? React.createElement("div", { className: "dbfox-data-block__running" },
      React.createElement("span", { className: "dbfox-data-block__spinner" }),
      React.createElement("span", null, "正在执行查询…")) : null,

    block.error ? React.createElement("div", { className: "dbfox-data-block__error", role: "alert" },
      React.createElement("strong", null, "执行失败："),
      React.createElement("span", null, block.error)) : null,

    block.result ? React.createElement("div", { className: "dbfox-data-block__result" },
      React.createElement("div", { className: "dbfox-data-block__meta" },
        React.createElement("div", { className: "dbfox-data-block__meta-left" },
          React.createElement("strong", null, block.result.status === "blocked" ? "安全拦截" : "查询结果"),
          block.result.status !== "blocked" && React.createElement("span", null, `${block.result.returned_rows ?? rows.length} / ${block.result.row_count ?? rows.length} 行${block.result.truncated ? " · 已截断" : ""}`),
          block.execDurationMs !== null && React.createElement("span", null, `耗时 ${block.execDurationMs} ms`)),
        React.createElement("div", { className: "dbfox-data-block__meta-right" },
          React.createElement("span", { className: "dbfox-data-block__artifact-badge" }, "已持久化 Artifact"))),
      block.result.status === "blocked"
        ? React.createElement("ul", { className: "dbfox-data-block__messages" },
            (block.result.messages || []).map((message) => React.createElement("li", { key: message }, message)))
        : React.createElement(ResultGrid, { columns, rows })) : null,

    !block.result && !block.running && !block.error ? React.createElement("div", { className: "dbfox-data-block__empty-hint" },
      React.createElement("span", null, "按 Ctrl/⌘ + Enter 或点击上方 ▶ 运行，查询结果将直接呈现在下方。")) : null);
}

function SqlConsoleDock({ view }) {
  const state = sqlStateByKey.get(view.stateKey || "");
  useVersion();

  if (!state) return React.createElement("p", { className: "dbfox-data-table__status" }, "SQL 控制台状态不可用。");

  if (!Array.isArray(state.blocks) || state.blocks.length === 0) {
    state.blocks = [{
      id: `b-${Date.now()}`,
      sql: state.sql || "",
      result: state.result || null,
      error: "",
      running: false,
      execDurationMs: null,
    }];
  }

  const [blocks, setBlocks] = React.useState(state.blocks);

  React.useEffect(() => {
    state.blocks = blocks;
  }, [blocks, state]);

  function updateBlock(updated) {
    setBlocks((prev) => prev.map((b) => (b.id === updated.id ? updated : b)));
  }

  function addBlock() {
    const newBlock = {
      id: `b-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      sql: "",
      result: null,
      error: "",
      running: false,
      execDurationMs: null,
    };
    setBlocks((prev) => [...prev, newBlock]);
  }

  function deleteBlock(id) {
    setBlocks((prev) => prev.filter((b) => b.id !== id));
  }

  function clearConsole() {
    setBlocks([{
      id: `b-${Date.now()}`,
      sql: "",
      result: null,
      error: "",
      running: false,
      execDurationMs: null,
    }]);
  }

  async function executeBlock(blockId, targetSql) {
    const block = blocks.find((b) => b.id === blockId);
    if (!block) return;
    const statement = (targetSql || block.sql).trim();
    if (!statement || block.running) return;

    updateBlock({ ...block, running: true, error: "" });
    const startTime = Date.now();
    try {
      const value = await host.operations.invoke("console.execute", {
        database_id: state.database.id,
        sql: statement,
        question: "SQL Console",
        session_id: state.sessionId,
        execution_id: globalThis.crypto?.randomUUID?.() || `console-${Date.now()}`,
      }, { projectId: state.projectId });
      state.sessionId = value.session_id;
      updateBlock({
        ...block,
        sql: targetSql || block.sql,
        running: false,
        error: "",
        result: value,
        execDurationMs: Date.now() - startTime,
      });
    } catch (reason) {
      updateBlock({
        ...block,
        running: false,
        error: reason instanceof Error ? reason.message : "SQL 执行失败。",
        result: null,
        execDurationMs: null,
      });
    }
  }

  async function executeAll() {
    for (const block of blocks) {
      if ((block.sql || "").trim()) {
        await executeBlock(block.id);
      }
    }
  }

  return React.createElement("section", { className: "dbfox-data-console" },
    React.createElement("header", { className: "dbfox-data-console__header" },
      React.createElement("div", { className: "dbfox-data-console__identity" },
        React.createElement("span", { className: "dbfox-data-console__badge" }, ">_"),
        React.createElement("strong", null, state.database.display_name),
        React.createElement("small", null, state.database.database_name),
        React.createElement("span", { className: "dbfox-data-console__mode-badge" }, "SQL 控制台")),
      React.createElement("div", { className: "dbfox-data-console__toolbar" },
        React.createElement("button", {
          type: "button",
          className: "dbfox-data-console__btn is-primary",
          onClick: addBlock,
          title: "新建查询 (Append Query Entry)",
        }, "+ 新建查询"),
        React.createElement("button", {
          type: "button",
          className: "dbfox-data-console__btn",
          onClick: () => void executeAll(),
          title: "顺序执行控制台中的所有查询",
        }, "▶ 全部运行"),
        React.createElement("button", {
          type: "button",
          className: "dbfox-data-console__btn",
          onClick: clearConsole,
          title: "清空控制台记录",
        }, "清空控制台"))),

    React.createElement("div", { className: "dbfox-data-console__canvas" },
      blocks.map((block, idx) => React.createElement(SqlBlock, {
        key: block.id,
        block,
        index: idx,
        total: blocks.length,
        projectId: state.projectId,
        database: state.database,
        sessionId: state.sessionId,
        onUpdate: updateBlock,
        onExecute: executeBlock,
        onDelete: deleteBlock,
      })),
      React.createElement("div", { className: "dbfox-data-console__footer-action" },
        React.createElement("button", {
          type: "button",
          className: "dbfox-data-console__add-card-btn",
          onClick: addBlock,
        }, "+ 添加新查询"))));
}

function CatalogTableDock({ view }) {
  const state = tableStateByKey.get(view.stateKey || "");
  const [detail, setDetail] = React.useState(null);
  const [error, setError] = React.useState("");
  const [tab, setTab] = React.useState("schema");
  const [preview, setPreview] = React.useState(null);
  const [previewError, setPreviewError] = React.useState("");
  const [previewLoading, setPreviewLoading] = React.useState(false);
  React.useEffect(() => {
    if (!state) return;
    let active = true;
    setDetail(null);
    setError("");
    host.operations.invoke("catalog.table", {
      database_id: state.database.id,
      table: state.table.qualified_name,
    }, { projectId: state.projectId })
      .then((value) => active && setDetail(value))
      .catch((reason) => active && setError(reason instanceof Error ? reason.message : "读取表结构失败。"));
    return () => { active = false; };
  }, [state?.projectId, state?.database?.id, state?.table?.qualified_name]);

  async function loadPreview() {
    if (!state || previewLoading) return;
    setTab("data");
    if (preview) return;
    setPreviewLoading(true);
    setPreviewError("");
    try {
      const value = await host.operations.invoke("table.preview", {
        database_id: state.database.id,
        table: state.table.qualified_name,
        limit: 20,
      }, { projectId: state.projectId });
      setPreview(value);
    } catch (reason) {
      setPreviewError(reason instanceof Error ? reason.message : "读取数据样例失败。");
    } finally {
      setPreviewLoading(false);
    }
  }
  if (!state) return React.createElement("p", { className: "dbfox-data-table__status" }, "表视图状态不可用。");
  if (error) return React.createElement("p", { className: "dbfox-data-table__status is-error", role: "alert" }, error);
  if (!detail) return React.createElement("p", { className: "dbfox-data-table__status" }, "正在读取表结构…");
  const columns = Array.isArray(detail.columns) ? detail.columns : [];
  return React.createElement("article", { className: "dbfox-data-table" },
    React.createElement("header", { className: "dbfox-data-table__header" },
      React.createElement("div", null,
        React.createElement("strong", null, state.table.qualified_name),
        React.createElement("small", null, `${state.database.display_name} · Catalog r${detail.catalog_revision}`)),
      React.createElement("span", null, `${columns.length} 个字段`)),
    React.createElement("nav", { className: "dbfox-data-table__tabs", "aria-label": "表视图" },
      React.createElement("button", { type: "button", className: tab === "schema" ? "is-active" : "", onClick: () => setTab("schema") }, "结构"),
      React.createElement("button", { type: "button", className: tab === "data" ? "is-active" : "", onClick: () => void loadPreview() }, "数据样例")),
    tab === "schema" ? React.createElement("div", { className: "dbfox-data-table__scroll" },
      React.createElement("table", null,
        React.createElement("thead", null, React.createElement("tr", null,
          React.createElement("th", null, "字段"),
          React.createElement("th", null, "类型"),
          React.createElement("th", null, "约束"),
          React.createElement("th", null, "默认值"))),
        React.createElement("tbody", null, columns.map((column) => React.createElement("tr", { key: column.column_name },
          React.createElement("td", null, React.createElement("code", null, column.column_name)),
          React.createElement("td", null, column.column_type || column.data_type || "—"),
          React.createElement("td", null, [column.is_primary_key ? "PK" : "", column.is_foreign_key ? "FK" : "", column.is_nullable ? "NULL" : "NOT NULL"].filter(Boolean).join(" · ")),
          React.createElement("td", null, column.column_default ?? "—"))))))
      : React.createElement("div", { className: "dbfox-data-table__preview" },
          previewLoading ? React.createElement("p", { className: "dbfox-data-table__status" }, "正在读取数据样例…") : null,
          previewError ? React.createElement("p", { className: "dbfox-data-table__status is-error", role: "alert" }, previewError) : null,
          preview ? React.createElement(React.Fragment, null,
            preview.warnings?.length ? React.createElement("p", { className: "dbfox-data-table__notice" }, preview.warnings.join(" · ")) : null,
            React.createElement(ResultGrid, { columns: preview.columns || [], rows: preview.rows || [] })) : null));
}

function ProfileGroup({ projectId, group }) {
  useVersion();
  const key = `${projectId}:${group.profile.id}`;
  const expanded = expandedProfiles.has(key);
  const databases = Array.isArray(group.databases) ? group.databases : [];
  return React.createElement("div", { className: "dbfox-data__profile" },
    React.createElement("button", {
      type: "button",
      className: "dbfox-data__profile-row",
      onClick: () => {
        if (expanded) expandedProfiles.delete(key);
        else expandedProfiles.add(key);
        emit();
      },
      "aria-expanded": expanded,
    },
    React.createElement("span", {
      className: `dbfox-data__chevron ${expanded ? "is-expanded" : ""}`,
      "aria-hidden": true,
    }, "›"),
    React.createElement("span", { className: `dbfox-data__provider is-${group.profile.provider}`, "aria-hidden": true }, "●"),
    React.createElement("span", { className: "dbfox-data__label" }, group.profile.name),
    React.createElement("span", { className: "dbfox-data__count" }, databases.length)),
    expanded ? React.createElement("div", { className: "dbfox-data__databases", role: "group" },
      databases.length > 0
        ? databases.map((database) => React.createElement(DatabaseRow, { key: database.id, projectId, database }))
        : React.createElement("p", { className: "dbfox-data__status" }, "这个连接还没有数据库。"),
    ) : null,
  );
}

function DataConnector({ projectId }) {
  useVersion();
  const [loading, setLoading] = React.useState(!loadedProjects.has(projectId));
  const [error, setError] = React.useState("");
  React.useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    loadProfiles(projectId)
      .catch((reason) => active && setError(reason instanceof Error ? reason.message : String(reason)))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [projectId]);

  const groups = groupsByProject.get(projectId) || [];
  const dialog = dialogProjectId === projectId
    ? React.createElement(ConnectionDialog, { projectId })
    : null;
  if (loading && groups.length === 0) {
    return React.createElement(React.Fragment, null,
      React.createElement("p", { className: "dbfox-data__status" }, "正在读取数据库资源…"),
      dialog);
  }
  if (error) {
    return React.createElement(React.Fragment, null,
      React.createElement("div", { className: "dbfox-data__empty" },
        React.createElement("p", { role: "alert" }, "数据库资源暂时不可用。"),
        React.createElement("button", { type: "button", onClick: () => void loadProfiles(projectId) }, "重试")),
      dialog);
  }
  if (groups.length === 0) {
    return React.createElement(React.Fragment, null,
      React.createElement("p", { className: "dbfox-data__status" }, "这个 Project 还没有数据库连接。"),
      dialog,
    );
  }
  return React.createElement("div", { className: "dbfox-data", role: "tree", "aria-label": "数据库资源" },
    groups.map((group) => React.createElement(ProfileGroup, { key: group.profile.id, projectId, group })),
    dialog,
  );
}

export function register(extensionHost) {
  host = extensionHost;
  React = globalThis.__DBFOX_EXTENSION_HOST__?.React;
  if (!React) throw new Error("DBFox React host is unavailable");
  ensureStylesheet();
  host.connectors.register({
    id: DLC_ID,
    title: "数据",
    icon: React.createElement("span", { "aria-hidden": true }, "◉"),
    addLabel: "新建数据库连接",
    onAdd: ({ projectId }) => {
      dialogProjectId = projectId;
      emit();
    },
    render: ({ projectId }) => React.createElement(DataConnector, { projectId }),
  });
  host.dockViews.register({
    viewType: TABLE_VIEW_TYPE,
    icon: () => React.createElement("span", { "aria-hidden": true }, "▦"),
    resolveTitle: (view) => tableStateByKey.get(view.stateKey || "")?.table.qualified_name || view.title,
    isVisible: (view, context) => !view.projectId || view.projectId === context.activeProjectId,
    render: (view) => React.createElement(CatalogTableDock, { view }),
  });
  host.dockViews.register({
    viewType: SQL_VIEW_TYPE,
    icon: () => React.createElement("span", { "aria-hidden": true }, ">_"),
    resolveTitle: (view) => `${sqlStateByKey.get(view.stateKey || "")?.database.display_name || view.title} · SQL`,
    isVisible: (view, context) => !view.projectId || view.projectId === context.activeProjectId,
    render: (view) => React.createElement(SqlConsoleDock, { view }),
  });
}

export const __testing = Object.freeze({ DLC_ID, TABLE_VIEW_TYPE, SQL_VIEW_TYPE });
