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

function DatabaseRow({ projectId, database }) {
  useVersion();
  const key = databaseKey(projectId, database.id);
  const ref = { kind: "dbfox.data.database", id: database.id };
  const selected = host.contextSelection.isSelected(ref);
  const focused = focusedDatabaseByProject.get(projectId) === database.id;
  const expanded = expandedDatabases.has(key);
  const catalog = catalogByDatabase.get(key);
  const tables = Array.isArray(catalog?.tables) ? catalog.tables : [];
  const loading = catalogLoading.has(key);
  const error = catalogErrors.get(key);

  async function toggleContext(event) {
    event.stopPropagation();
    if (selected) await host.contextSelection.remove(ref);
    else await host.contextSelection.add(ref);
    emit();
  }

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
      }, "↻"),
      React.createElement("button", {
        type: "button",
        className: `dbfox-data__context ${selected ? "is-selected" : ""}`,
        onClick: (event) => void toggleContext(event),
        title: selected ? "移出对话上下文" : "加入对话上下文",
        "aria-label": `${selected ? "移出" : "加入"}对话上下文：${database.display_name}`,
      }, selected ? "✓" : "+")),
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

function ResultGrid({ columns, rows, emptyLabel = "没有返回数据。" }) {
  if (!Array.isArray(rows) || rows.length === 0) {
    return React.createElement("p", { className: "dbfox-data-result__empty" }, emptyLabel);
  }
  return React.createElement("div", { className: "dbfox-data-result__scroll" },
    React.createElement("table", null,
      React.createElement("thead", null, React.createElement("tr", null,
        columns.map((column) => React.createElement("th", { key: column }, column)))),
      React.createElement("tbody", null, rows.map((row, index) => React.createElement("tr", { key: index },
        columns.map((column) => React.createElement("td", { key: column }, String(row?.[column] ?? ""))))))));
}

function SqlConsoleDock({ view }) {
  const state = sqlStateByKey.get(view.stateKey || "");
  const [sql, setSql] = React.useState(state?.sql || "");
  const [result, setResult] = React.useState(state?.result || null);
  const [running, setRunning] = React.useState(false);
  const [error, setError] = React.useState("");
  if (!state) return React.createElement("p", { className: "dbfox-data-table__status" }, "SQL Console 状态不可用。");

  async function execute() {
    const statement = sql.trim();
    if (!statement || running) return;
    state.sql = sql;
    setRunning(true);
    setError("");
    try {
      const value = await host.operations.invoke("console.execute", {
        database_id: state.database.id,
        sql: statement,
        question: "SQL Console",
        session_id: state.sessionId,
        execution_id: globalThis.crypto?.randomUUID?.() || `console-${Date.now()}`,
      }, { projectId: state.projectId });
      state.sessionId = value.session_id;
      state.result = value;
      setResult(value);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "SQL 执行失败。");
    } finally {
      setRunning(false);
    }
  }

  const columns = Array.isArray(result?.columns) ? result.columns : [];
  const rows = Array.isArray(result?.rows) ? result.rows : [];
  return React.createElement("section", { className: "dbfox-data-console" },
    React.createElement("header", { className: "dbfox-data-console__header" },
      React.createElement("div", null,
        React.createElement("strong", null, state.database.display_name),
        React.createElement("small", null, state.database.database_name)),
      React.createElement("span", null, "只读")),
    React.createElement("div", { className: "dbfox-data-console__editor" },
      React.createElement("textarea", {
        value: sql,
        spellCheck: false,
        autoCapitalize: "off",
        placeholder: "输入只读 SELECT 查询…",
        "aria-label": "SQL 查询",
        onChange: (event) => {
          setSql(event.target.value);
          state.sql = event.target.value;
        },
        onKeyDown: (event) => {
          if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
            event.preventDefault();
            void execute();
          }
        },
      }),
      React.createElement("div", { className: "dbfox-data-console__actions" },
        React.createElement("span", null, "Ctrl/⌘ + Enter"),
        React.createElement("button", {
          type: "button",
          disabled: running || !sql.trim(),
          onClick: () => void execute(),
        }, running ? "正在执行…" : "运行查询"))),
    error ? React.createElement("p", { className: "dbfox-data-console__error", role: "alert" }, error) : null,
    result ? React.createElement("div", { className: "dbfox-data-console__result" },
      React.createElement("div", { className: "dbfox-data-console__result-meta" },
        React.createElement("strong", null, result.status === "blocked" ? "查询未执行" : "查询结果"),
        React.createElement("span", null, result.status === "blocked"
          ? "安全检查未通过"
          : `${result.returned_rows} / ${result.row_count} 行${result.truncated ? " · 已截断" : ""}`)),
      result.status === "blocked"
        ? React.createElement("ul", { className: "dbfox-data-console__messages" },
            (result.messages || []).map((message) => React.createElement("li", { key: message }, message)))
        : React.createElement(ResultGrid, { columns, rows }))
      : React.createElement("div", { className: "dbfox-data-console__placeholder" },
          React.createElement("strong", null, "运行一个查询"),
          React.createElement("span", null, "结果会作为耐久 Artifact 保存，并保持当前 Database authority。")));
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
