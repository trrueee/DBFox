const DLC_ID = "dbfox.data";
const TABLE_VIEW_TYPE = "dbfox.data.catalog-table";
const SQL_VIEW_TYPE = "dbfox.data.sql-console";

let host;
let React;
let dialogProjectId = null;
const groupsByProject = new Map();
const loadedProjects = new Set();
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
  const stateKey = `${host.workbench.currentScopeId()}:${projectId}:${database.id}`;
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
    target: {
      type: "object",
      object: { kind: "dbfox.data.database", id: database.id },
      authority: { kind: "dbfox.data.database", id: database.id },
    },
    stateKey,
  });
}

function openTable(projectId, database, table) {
  const stateKey = `${host.workbench.currentScopeId()}:${projectId}:${database.id}:${table.table_id}`;
  tableStateByKey.set(stateKey, { projectId, database, table });
  host.dockViews.open({
    viewKey: `data-table:${stateKey}`,
    viewType: TABLE_VIEW_TYPE,
    title: table.qualified_name,
    closeable: true,
    projectId,
    target: {
      type: "object",
      object: { kind: "dbfox.data.table", id: table.table_id },
      authority: { kind: "dbfox.data.database", id: database.id },
      locator: table.qualified_name,
    },
    stateKey,
  });
}

function ConnectionDialog({ projectId }) {
  const dialogRef = React.useRef(null);
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

  React.useEffect(() => {
    const element = dialogRef.current;
    if (element && !element.open) element.showModal();
    return () => {
      if (element?.open) element.close();
    };
  }, []);

  function syncClosed() {
    if (dialogProjectId !== projectId) return;
    dialogProjectId = null;
    emit();
  }

  function close() {
    if (saving) return;
    if (dialogRef.current?.open) dialogRef.current.close();
    syncClosed();
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
      if (dialogRef.current?.open) dialogRef.current.close();
      syncClosed();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "保存连接失败。");
    } finally {
      setSaving(false);
    }
  }

  const field = (label, input) => React.createElement("label", { className: "dbfox-data-dialog__field" },
    React.createElement("span", null, label), input);
  const input = (props) => React.createElement("input", { className: "dbfox-data-dialog__input", ...props });

  return React.createElement("dialog", {
    ref: dialogRef,
    className: "dbfox-data-dialog",
    closedby: "any",
    "aria-labelledby": "dbfox-data-dialog-title",
    "aria-describedby": "dbfox-data-dialog-description",
    onCancel: (event) => {
      event.preventDefault();
      close();
    },
    onClose: syncClosed,
  },
    React.createElement("form", { className: "dbfox-data-dialog__form", onSubmit: (event) => void save(event) },
      React.createElement("header", { className: "dbfox-data-dialog__header" },
        React.createElement("div", null,
          React.createElement("h2", { id: "dbfox-data-dialog-title" }, "新建数据库连接"),
          React.createElement("p", { id: "dbfox-data-dialog-description" }, "连接配置保存在当前 Project；密码只进入系统凭据库。")),
        React.createElement("button", { type: "button", className: "dbfox-data-dialog__close", onClick: close, "aria-label": "关闭" }, "×")),
      React.createElement("div", { className: "dbfox-data-dialog__body" },
        React.createElement("fieldset", { className: "dbfox-data-dialog__providers" },
          React.createElement("legend", { className: "dbfox-data-dialog__sr-only" }, "数据库类型"),
          ["mysql", "postgresql", "sqlite"].map((value) => React.createElement("label", { key: value },
            React.createElement("input", {
              type: "radio",
              name: `dbfox-data-provider-${projectId}`,
              value,
              checked: provider === value,
              onChange: () => selectProvider(value),
            }),
            React.createElement("span", null, providerLabel(value))))),
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
  const stateKey = view.stateKey || "";
  let state = sqlStateByKey.get(stateKey);
  if (!state && view.target?.type === "object" && view.target.object.kind === "dbfox.data.database" && view.projectId) {
    state = {
      projectId: view.projectId,
      database: { id: view.target.object.id, display_name: view.title.replace(/ · SQL$/, "") },
      sql: "",
      sessionId: null,
      result: null,
    };
    sqlStateByKey.set(stateKey, state);
  }
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
        sql: block.sql,
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
    React.createElement("div", { className: "dbfox-data-console__toolbar-row", role: "group", "aria-label": "SQL 操作" },
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
        }, "清空控制台")),
      React.createElement("small", null, state.database.database_name)),

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

function CatalogTableDock({ view, context }) {
  const stateKey = view.stateKey || "";
  let state = tableStateByKey.get(stateKey);
  if (
    !state
    && view.target?.type === "object"
    && view.target.object.kind === "dbfox.data.table"
    && view.target.authority?.kind === "dbfox.data.database"
    && view.target.locator
    && view.projectId
  ) {
    state = {
      projectId: view.projectId,
      database: { id: view.target.authority.id, display_name: view.target.authority.id },
      table: {
        table_id: view.target.object.id,
        qualified_name: view.target.locator,
      },
    };
    tableStateByKey.set(stateKey, state);
  }
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
      React.createElement("div", { className: "dbfox-data-table__header-actions" },
        React.createElement("span", null, `${columns.length} 个字段`),
        React.createElement("button", {
          type: "button",
          onClick: () => context.onAsk({
            label: `${state.database.display_name} · ${state.table.qualified_name}`,
            authority: { kind: "dbfox.data.database", id: state.database.id },
            object: {
              kind: "dbfox.data.table",
              id: state.table.table_id || state.table.qualified_name,
              version: detail.catalog_revision,
            },
            locator: `table:${state.table.qualified_name}`,
          }),
        }, "询问 DBFox"))),
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

function isProfileGroup(item) {
  return Boolean(item?.profile && Array.isArray(item.databases));
}

function isCatalogTable(item) {
  return typeof item?.table_id === "string";
}

function isDatabase(item) {
  return !isProfileGroup(item) && !isCatalogTable(item)
    && typeof item?.id === "string" && typeof item?.display_name === "string";
}

function DataResourceTree({ projectId, groups }) {
  const root = { groups };
  const itemId = (item) => {
    if (item === root) return `data-root:${projectId}`;
    if (isProfileGroup(item)) return `profile:${item.profile.id}`;
    if (isCatalogTable(item)) return `table:${item.table_id}`;
    return `database:${item.id}`;
  };
  const itemLabel = (item) => {
    if (item === root) return "数据库资源";
    if (isProfileGroup(item)) return item.profile.name;
    if (isCatalogTable(item)) return item.qualified_name;
    return item.display_name;
  };
  const itemChildren = (item) => {
    if (item === root) return groups;
    if (isProfileGroup(item)) return item.databases;
    if (isDatabase(item)) {
      const catalog = catalogByDatabase.get(databaseKey(projectId, item.id));
      return Array.isArray(catalog?.tables) ? catalog.tables : [];
    }
    return [];
  };

  function databaseForTable(tableId) {
    for (const group of groups) {
      for (const database of Array.isArray(group.databases) ? group.databases : []) {
        const tables = itemChildren(database);
        if (tables.some((table) => table.table_id === tableId)) return database;
      }
    }
    return null;
  }

  return React.createElement(host.ui.Tree, {
    rootItem: root,
    ariaLabel: "数据库资源",
    getItemId: itemId,
    getItemLabel: itemLabel,
    getItemChildren: itemChildren,
    getItemChildrenCount: (item) => {
      if (item === root) return groups.length;
      if (isProfileGroup(item)) return item.databases.length;
      if (isDatabase(item)) return itemChildren(item).length;
      return undefined;
    },
    loadItemChildren: async (item, signal) => {
      if (!isDatabase(item)) return itemChildren(item);
      if (signal.aborted) throw new DOMException("Catalog load cancelled", "AbortError");
      const key = databaseKey(projectId, item.id);
      if (!catalogByDatabase.has(key)) await loadCatalog(projectId, item.id);
      if (signal.aborted) throw new DOMException("Catalog load cancelled", "AbortError");
      return itemChildren(item);
    },
    defaultExpandedIds: groups.map((group) => `profile:${group.profile.id}`),
    renderItemIcon: (item) => {
      if (isProfileGroup(item)) {
        return React.createElement("span", { className: `dbfox-data__provider is-${item.profile.provider}`, "aria-hidden": true }, "●");
      }
      if (isDatabase(item)) return React.createElement("span", { className: "dbfox-data__database-icon", "aria-hidden": true }, "◉");
      return React.createElement("span", { className: "dbfox-data__table-icon", "aria-hidden": true }, "▦");
    },
    renderItemMeta: (item, state) => {
      if (isProfileGroup(item)) return item.databases.length;
      if (isCatalogTable(item)) return item.columns_count;
      if (!isDatabase(item)) return null;
      if (state.loading || catalogLoading.has(databaseKey(projectId, item.id))) return "读取中…";
      if (state.loadError || catalogErrors.has(databaseKey(projectId, item.id))) return "读取失败，点击重试";
      return null;
    },
    renderItemActions: (item) => {
      if (!isDatabase(item)) return null;
      const key = databaseKey(projectId, item.id);
      const loading = catalogLoading.has(key);
      return React.createElement(React.Fragment, null,
        React.createElement("button", {
          type: "button",
          className: "dbfox-data__sql",
          onClick: () => openSqlConsole(projectId, item),
          title: "打开 SQL Console",
          "aria-label": `打开 SQL Console：${item.display_name}`,
        }, ">_"),
        React.createElement("button", {
          type: "button",
          className: "dbfox-data__refresh",
          onClick: () => void loadCatalog(projectId, item.id, { refresh: true }).catch(() => undefined),
          disabled: loading,
          title: "刷新数据库目录",
          "aria-label": `刷新数据库目录：${item.display_name}`,
        }, "↻"));
    },
    renderBranchFooter: (item, state) => {
      if (isProfileGroup(item)) {
        return item.databases.length === 0
          ? React.createElement("p", { className: "dbfox-data__status" }, "这个连接还没有数据库。")
          : null;
      }
      if (!isDatabase(item)) return null;
      const key = databaseKey(projectId, item.id);
      const catalog = catalogByDatabase.get(key);
      const tables = Array.isArray(catalog?.tables) ? catalog.tables : [];
      const loading = state.loading || catalogLoading.has(key);
      const error = state.loadError || catalogErrors.get(key);
      if (loading) return React.createElement("p", { className: "dbfox-data__status", role: "status" }, "正在读取目录…");
      if (error) return React.createElement("p", { className: "dbfox-data__catalog-error", role: "alert" }, "数据库目录暂时不可用。收起后重新展开即可重试。");
      if (catalog?.catalog_status === "uninitialized") {
        return React.createElement("div", { className: "dbfox-data__catalog-empty" },
          React.createElement("span", null, "目录尚未刷新。"),
          React.createElement("button", {
            type: "button",
            onClick: () => void loadCatalog(projectId, item.id, { refresh: true }).catch(() => undefined),
          }, "刷新目录"));
      }
      if (catalog?.catalog_status === "ready" && tables.length === 0) {
        return React.createElement("p", { className: "dbfox-data__status" }, "这个数据库没有可浏览的数据表。");
      }
      if (catalog?.has_more && catalog?.next_cursor) {
        return React.createElement("button", {
          type: "button",
          className: "dbfox-data__load-more",
          onClick: () => void loadCatalog(projectId, item.id, {
            cursor: catalog.next_cursor,
            append: true,
          }).catch(() => undefined),
        }, "加载更多");
      }
      return null;
    },
    onItemSelect: (item) => {
      if (!isCatalogTable(item)) return;
      const database = databaseForTable(item.table_id);
      if (database) openTable(projectId, database, item);
    },
  });
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
  async function retryProfiles() {
    setLoading(true);
    setError("");
    try {
      await loadProfiles(projectId);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
    }
  }
  if (loading && groups.length === 0) {
    return React.createElement(React.Fragment, null,
      React.createElement("p", { className: "dbfox-data__status" }, "正在读取数据库资源…"),
      dialog);
  }
  if (error) {
    return React.createElement(React.Fragment, null,
      React.createElement("div", { className: "dbfox-data__empty" },
        React.createElement("p", { role: "alert" }, "数据库资源暂时不可用。"),
        React.createElement("button", { type: "button", onClick: () => void retryProfiles() }, "重试")),
      dialog);
  }
  if (groups.length === 0) {
    return React.createElement(React.Fragment, null,
      React.createElement("p", { className: "dbfox-data__status" }, "这个 Project 还没有数据库连接。"),
      dialog,
    );
  }
  return React.createElement("div", { className: "dbfox-data" },
    React.createElement(DataResourceTree, { projectId, groups }),
    dialog,
  );
}

function parseSqlArtifact(payload) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new TypeError("SQL Artifact payload must be an object");
  }
  if (typeof payload.sql !== "string" || !payload.sql.trim()) {
    throw new TypeError("SQL Artifact payload is missing sql");
  }
  return {
    sql: payload.sql,
    dialect: typeof payload.dialect === "string" ? payload.dialect : undefined,
    metadata: Array.isArray(payload.metadata)
      ? payload.metadata.filter((item) => typeof item === "string")
      : [
          typeof payload.purpose === "string" ? payload.purpose : "",
          typeof payload.validationStatus === "string" ? `校验 ${payload.validationStatus}` : "",
          typeof payload.executionStatus === "string" ? `执行 ${payload.executionStatus}` : "",
          Number.isFinite(payload.rowCount) ? `${payload.rowCount} 行` : "",
          Number.isFinite(payload.latencyMs) ? `${payload.latencyMs}ms` : "",
        ].filter(Boolean),
  };
}

function renderSqlArtifact(artifact, payload, context) {
  const sql = parseSqlArtifact(payload);
  return React.createElement(host.ui.CodeArtifact, {
    title: artifact.title,
    code: sql.sql,
    language: "sql",
    badge: sql.dialect ? `SQL · ${sql.dialect}` : "SQL",
    description: artifact.summary || undefined,
    metadata: sql.metadata,
    fileName: `${artifact.id}.sql`,
    mimeType: "text/sql;charset=utf-8",
    ariaLabel: `${artifact.title} SQL`,
    onToast: context.onToast,
  });
}

function renderSourceSqlArtifact(artifact, _payload, context) {
  const sourceId = typeof artifact.payload?.sourceSqlArtifactId === "string"
    ? artifact.payload.sourceSqlArtifactId
    : "";
  const source = sourceId && context.resolveArtifact ? context.resolveArtifact(sourceId) : null;
  if (!source || source.type !== "dbfox.data.sql") {
    throw new Error("The source SQL Artifact is unavailable");
  }
  return renderSqlArtifact(source, source.payload, context);
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
    listResources: async ({ projectId }) => {
      const groups = await loadProfiles(projectId);
      const resources = [];
      for (const group of groups) {
        const profile = group.profile || {};
        if (profile.status !== "active") continue;
        for (const database of group.databases || []) {
          if (database.status !== "active") continue;
          resources.push({
            kind: "dbfox.data.database",
            id: database.id,
            name: database.display_name,
            detail: `${providerLabel(profile.provider)} · ${database.database_name} · ${profile.name}`,
          });
        }
      }
      return resources;
    },
    removeResource: async ({ projectId }, resource) => {
      await host.operations.invoke("databases.delete", { database_id: resource.id }, { projectId });
      await loadProfiles(projectId);
    },
    render: ({ projectId }) => React.createElement(DataConnector, { projectId }),
  });
  host.dockViews.register({
    viewType: TABLE_VIEW_TYPE,
    icon: () => React.createElement("span", { "aria-hidden": true }, "▦"),
    resolveTitle: (view) => tableStateByKey.get(view.stateKey || "")?.table.qualified_name || view.title,
    isVisible: (view, context) => !view.projectId || view.projectId === context.activeProjectId,
    render: (view, context) => React.createElement(CatalogTableDock, { view, context }),
  });
  host.dockViews.register({
    viewType: SQL_VIEW_TYPE,
    icon: () => React.createElement("span", { "aria-hidden": true }, ">_"),
    resolveTitle: (view) => `${sqlStateByKey.get(view.stateKey || "")?.database.display_name || view.title} · SQL`,
    isVisible: (view, context) => !view.projectId || view.projectId === context.activeProjectId,
    render: (view) => React.createElement(SqlConsoleDock, { view }),
  });
  host.artifactViews.register({
    id: "dbfox.data.sql",
    title: "SQL",
    priority: 70,
    surfaces: ["inline", "workspace"],
    artifactTypes: [{ type: "dbfox.data.sql", schemaVersions: [1] }],
    parsePayload: parseSqlArtifact,
    render: renderSqlArtifact,
  });
  host.artifactViews.register({
    id: "dbfox.data.source-sql",
    title: "来源 SQL",
    priority: 50,
    surfaces: ["workspace"],
    artifactTypes: [
      { type: "dbfox.data.result_view", schemaVersions: [1, 2] },
      { type: "dbfox.data.snapshot", schemaVersions: [1] },
    ],
    parsePayload: (payload) => payload,
    render: renderSourceSqlArtifact,
  });
}

export function deactivate() {
  dialogProjectId = null;
  groupsByProject.clear();
  loadedProjects.clear();
  catalogByDatabase.clear();
  catalogLoading.clear();
  catalogErrors.clear();
  tableStateByKey.clear();
  sqlStateByKey.clear();
  listeners.clear();
  if (typeof document !== "undefined") document.querySelectorAll(`link[data-dbfox-dlc="${DLC_ID}"]`).forEach((link) => link.remove());
  host = undefined;
  React = undefined;
}

export const __testing = Object.freeze({ DLC_ID, TABLE_VIEW_TYPE, SQL_VIEW_TYPE });
