const DLC_ID = "dbfox.workspace";
const FILE_VIEW_TYPE = "dbfox.workspace.file";
const FILE_SNAPSHOT_TYPE = "dbfox.workspace.file_snapshot";
const CODE_PATCH_TYPE = "dbfox.workspace.code_patch";

let host;
let React;
const bindings = new Map();
const fileState = new Map();
const listeners = new Set();

function emit() { for (const listener of listeners) listener(); }
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
async function invoke(name, input, projectId) {
  return host.operations.invoke(name, input, { projectId });
}
async function loadBinding(projectId) {
  const result = await invoke("binding.get", {}, projectId);
  bindings.set(projectId, result?.binding || null);
  emit();
  return result?.binding || null;
}
function openFile(projectId, binding, path) {
  const stateKey = `${projectId}:${path}`;
  fileState.set(stateKey, { projectId, path, binding });
  host.dockViews.open({
    viewKey: `workspace-file:${stateKey}`,
    viewType: FILE_VIEW_TYPE,
    title: path.split("/").pop() || path,
    closeable: true,
    projectId,
    stateKey,
    target: { type: "resource", kind: "workspace", id: binding.id, version: binding.root_digest },
  });
}

function WorkspaceConnector({ projectId }) {
  useVersion();
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState("");
  React.useEffect(() => {
    let active = true;
    setLoading(true);
    loadBinding(projectId)
      .catch((reason) => active && setError(reason instanceof Error ? reason.message : String(reason)))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [projectId]);
  const binding = bindings.get(projectId) || null;

  async function chooseFolder() {
    setError("");
    try {
      const rootPath = await host.nativeDialogs.pickFolder();
      if (!rootPath) return;
      setLoading(true);
      await invoke("binding.create", { root_path: rootPath }, projectId);
      await loadBinding(projectId);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
    }
  }
  async function removeFolder() {
    setLoading(true);
    try {
      await invoke("binding.delete", {}, projectId);
      await host.contextSelection.remove({ kind: "workspace", id: binding.id });
      await loadBinding(projectId);
    } finally {
      setLoading(false);
    }
  }
  if (loading && !binding) return React.createElement("p", { className: "dbfox-workspace__status" }, "正在读取工作区…");
  if (!binding) return React.createElement("div", { className: "dbfox-workspace__empty" },
    React.createElement("p", null, "这个 Project 还没有本地工作区。"),
    React.createElement("button", { type: "button", onClick: () => void chooseFolder() }, "选择文件夹"),
    error ? React.createElement("p", { role: "alert" }, error) : null,
  );
  const selected = host.contextSelection.isSelected({ kind: "workspace", id: binding.id });
  return React.createElement("section", { className: "dbfox-workspace" },
    React.createElement("header", null,
      React.createElement("span", { title: binding.root_path }, binding.root_path),
      React.createElement("button", {
        type: "button",
        className: selected ? "is-selected" : "",
        onClick: () => void (selected
          ? host.contextSelection.remove({ kind: "workspace", id: binding.id })
          : host.contextSelection.add({ kind: "workspace", id: binding.id })),
      }, selected ? "✓ 已加入" : "+ 对话"),
      React.createElement("button", { type: "button", onClick: () => void removeFolder(), title: "移除工作区" }, "×"),
    ),
    React.createElement(FileBrowser, { projectId, binding, path: "" }),
    error ? React.createElement("p", { className: "dbfox-workspace__error", role: "alert" }, error) : null,
  );
}

function FileBrowser({ projectId, binding, path }) {
  const [current, setCurrent] = React.useState(path);
  const [entries, setEntries] = React.useState([]);
  const [status, setStatus] = React.useState("loading");
  React.useEffect(() => {
    let active = true;
    setStatus("loading");
    invoke("files.list", { path: current }, projectId)
      .then((result) => { if (active) { setEntries(result?.entries || []); setStatus("ready"); } })
      .catch(() => active && setStatus("error"));
    return () => { active = false; };
  }, [projectId, binding.root_digest, current]);
  return React.createElement("div", { className: "dbfox-workspace__files", role: "tree" },
    current ? React.createElement("button", { type: "button", onClick: () => setCurrent(current.includes("/") ? current.slice(0, current.lastIndexOf("/")) : "") }, "← 上一级") : null,
    status === "loading" ? React.createElement("p", null, "正在读取…") : null,
    status === "error" ? React.createElement("p", { className: "dbfox-workspace__error" }, "无法读取这个目录。") : null,
    entries.map((entry) => React.createElement("button", {
      key: entry.path,
      type: "button",
      role: "treeitem",
      onClick: () => entry.is_dir ? setCurrent(entry.path) : openFile(projectId, binding, entry.path),
    }, React.createElement("span", { "aria-hidden": true }, entry.is_dir ? "▸" : "·"), entry.name)),
  );
}

function FileDock({ view }) {
  const state = fileState.get(view.stateKey || "");
  const [result, setResult] = React.useState(null);
  const [error, setError] = React.useState("");
  React.useEffect(() => {
    if (!state) return;
    let active = true;
    invoke("files.read", { path: state.path }, state.projectId)
      .then((value) => active && setResult(value))
      .catch((reason) => active && setError(reason instanceof Error ? reason.message : String(reason)));
    return () => { active = false; };
  }, [state?.projectId, state?.path, state?.binding?.root_digest]);
  if (!state) return React.createElement("p", null, "文件状态不可用。");
  if (error) return React.createElement("p", { className: "dbfox-workspace__error" }, error);
  if (!result) return React.createElement("p", null, "正在读取文件…");
  return React.createElement("article", { className: "dbfox-workspace-file" },
    React.createElement("header", null, React.createElement("strong", null, state.path), React.createElement("small", null, `${result.size_bytes} bytes · ${result.sha256.slice(0, 12)}`)),
    React.createElement("pre", null, React.createElement("code", null, result.content)),
  );
}

function artifactPayload(value, requiredFields, label) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`Invalid ${label} payload`);
  }
  for (const field of requiredFields) {
    if (typeof value[field] !== "string" || !value[field]) {
      throw new Error(`${label} requires ${field}`);
    }
  }
  return value;
}

function parseFileSnapshot(value) {
  return artifactPayload(value, ["relativePath", "sha256"], "Workspace file snapshot");
}

function parseCodePatch(value) {
  return artifactPayload(value, ["relativePath", "newSha256"], "Workspace code patch");
}

function WorkspaceArtifact({ artifact, kind }) {
  const payload = kind === "snapshot"
    ? parseFileSnapshot(artifact.payload)
    : parseCodePatch(artifact.payload);
  const digest = kind === "snapshot" ? payload.sha256 : payload.newSha256;
  const state = kind === "snapshot"
    ? (payload.truncated ? "snapshot · truncated" : "snapshot")
    : (payload.created ? "created" : "replaced");
  return React.createElement("article", { className: "dbfox-workspace-artifact" },
    React.createElement("header", null,
      React.createElement("strong", null, artifact.title || payload.relativePath),
      React.createElement("span", null, kind === "snapshot" ? "File Snapshot" : "Code Patch"),
    ),
    React.createElement("code", null, payload.relativePath),
    React.createElement("small", null, `${state} · ${payload.sizeBytes || 0} bytes · ${digest.slice(0, 12)}…`),
  );
}

export function register(extensionHost) {
  host = extensionHost;
  React = globalThis.__DBFOX_EXTENSION_HOST__?.React;
  if (!React) throw new Error("DBFox React host is unavailable");
  ensureStylesheet();
  host.connectors.register({
    id: DLC_ID,
    title: "文件",
    icon: React.createElement("span", { "aria-hidden": true }, "▱"),
    addLabel: "选择工作区",
    onAdd: ({ projectId }) => {
      void host.nativeDialogs.pickFolder().then(async (rootPath) => {
        if (!rootPath) return;
        await invoke("binding.create", { root_path: rootPath }, projectId);
        await loadBinding(projectId);
      });
    },
    render: ({ projectId }) => React.createElement(WorkspaceConnector, { projectId }),
  });
  host.dockViews.register({
    viewType: FILE_VIEW_TYPE,
    icon: () => React.createElement("span", { "aria-hidden": true }, "·"),
    resolveTitle: (view) => fileState.get(view.stateKey || "")?.path.split("/").pop() || view.title,
    isVisible: (view, context) => !view.projectId || view.projectId === context.activeProjectId,
    render: (view) => React.createElement(FileDock, { view }),
  });
  host.artifactRenderers.register({
    type: FILE_SNAPSHOT_TYPE,
    supportedSchemaVersions: [1],
    parsePayload: parseFileSnapshot,
    render: (artifact) => React.createElement(WorkspaceArtifact, { artifact, kind: "snapshot" }),
  });
  host.artifactRenderers.register({
    type: CODE_PATCH_TYPE,
    supportedSchemaVersions: [1],
    parsePayload: parseCodePatch,
    render: (artifact) => React.createElement(WorkspaceArtifact, { artifact, kind: "patch" }),
  });
}
