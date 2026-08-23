const DLC_ID = "dbfox.data";

let host;
let React;
let dialogProjectId = null;
const groupsByProject = new Map();
const loadedProjects = new Set();
const expandedProfiles = new Set();
const focusedDatabaseByProject = new Map();
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
  const ref = { kind: "dbfox.data.database", id: database.id };
  const selected = host.contextSelection.isSelected(ref);
  const focused = focusedDatabaseByProject.get(projectId) === database.id;

  async function toggleContext(event) {
    event.stopPropagation();
    if (selected) await host.contextSelection.remove(ref);
    else await host.contextSelection.add(ref);
    emit();
  }

  return React.createElement("div", {
    className: `dbfox-data__database-row ${focused ? "is-focused" : ""}`,
    role: "treeitem",
    "aria-selected": focused,
  },
  React.createElement("button", {
    type: "button",
    className: "dbfox-data__database-focus",
    onClick: () => {
      focusedDatabaseByProject.set(projectId, database.id);
      emit();
    },
    title: database.database_name,
  },
  React.createElement("span", { className: "dbfox-data__database-icon", "aria-hidden": true }, "◉"),
  React.createElement("span", { className: "dbfox-data__label" }, database.display_name)),
  React.createElement("button", {
    type: "button",
    className: `dbfox-data__context ${selected ? "is-selected" : ""}`,
    onClick: (event) => void toggleContext(event),
    title: selected ? "移出对话上下文" : "加入对话上下文",
    "aria-label": `${selected ? "移出" : "加入"}对话上下文：${database.display_name}`,
  }, selected ? "✓" : "+"));
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
}
