const DLC_ID = "dbfox.workspace";
const FILE_VIEW_TYPE = "dbfox.workspace.file";
const FILE_SNAPSHOT_TYPE = "dbfox.workspace.file_snapshot";
const CODE_PATCH_TYPE = "dbfox.workspace.code_patch";

let host;
let React;
const bindings = new Map();
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
async function invoke(name, input, projectId, signal) {
  return host.operations.invoke(name, input, { projectId, signal });
}
async function loadBinding(projectId, signal) {
  const result = await invoke("binding.get", {}, projectId, signal);
  if (signal?.aborted) return null;
  bindings.set(projectId, result?.binding || null);
  emit();
  return result?.binding || null;
}
function openFile(projectId, binding, path) {
  const stateKey = `${host.workbench.currentScopeId()}:${projectId}:${path}`;
  host.dockViews.open({
    viewKey: `workspace-file:${stateKey}`,
    viewType: FILE_VIEW_TYPE,
    preferredWidth: 520,
    title: path.split("/").pop() || path,
    closeable: true,
    preview: true,
    projectId,
    stateKey,
    target: {
      type: "object",
      object: { kind: "dbfox.workspace.file", id: path, version: binding.root_digest },
      authority: { kind: "dbfox.workspace.root", id: binding.id },
      locator: path,
    },
  });
}

function WorkspaceConnector({ projectId, view, context }) {
  useVersion();
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState("");
  const [explorerOpen, setExplorerOpen] = React.useState(true);
  const [reloadKey, setReloadKey] = React.useState(0);
  React.useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    loadBinding(projectId, controller.signal)
      .catch((reason) => !controller.signal.aborted && setError(reason instanceof Error ? reason.message : "无法读取项目文件夹。"))
      .finally(() => !controller.signal.aborted && setLoading(false));
    return () => controller.abort();
  }, [projectId, reloadKey]);
  const binding = bindings.get(projectId) || null;

  function refreshFiles() {
    setLoading(true);
    setReloadKey((value) => value + 1);
  }

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
  if (loading && !binding) return React.createElement("p", { className: "dbfox-workspace__status" }, "正在读取工作区…");
  if (!binding) return React.createElement("div", { className: "dbfox-workspace__empty" },
    React.createElement("p", null, error ? "无法读取项目文件夹。" : "关联文件夹后即可浏览项目文件。"),
    React.createElement("button", { type: "button", onClick: error ? refreshFiles : () => void chooseFolder() }, error ? "重试" : "选择文件夹"),
    error ? React.createElement("p", { role: "alert" }, error) : null,
  );
  return React.createElement("section", { className: "dbfox-workspace" },
    React.createElement("header", null,
      React.createElement("button", { type: "button", className: "dbfox-workspace__tree-toggle", "aria-label": explorerOpen ? "收起文件树" : "显示文件树", "aria-expanded": explorerOpen, onClick: () => setExplorerOpen((value) => !value) }, React.createElement(host.ui.ResourceIcon, { kind: "folder", size: 16 })),
      React.createElement("span", { title: binding.root_path }, binding.root_path),
      React.createElement("button", { type: "button", className: "dbfox-workspace__refresh", "aria-label": "刷新文件", disabled: loading,
        onClick: refreshFiles }, loading ? "刷新中…" : "刷新"),
    ),
    React.createElement("div", { className: `dbfox-workspace__panes${explorerOpen ? "" : " dbfox-workspace__panes--collapsed"}` },
      explorerOpen ? React.createElement("aside", { className: "dbfox-workspace__explorer", "aria-label": "文件浏览器" }, React.createElement(FileBrowser, { projectId, binding, path: "", selectedPath: view?.target?.locator, refreshKey: reloadKey })) : null,
      React.createElement("div", { className: "dbfox-workspace__preview" }, view
        ? error ? null : React.createElement(FilePreview, { key: JSON.stringify([projectId, view.target]), view, context, binding, bindingReady: !loading, refreshKey: reloadKey })
        : React.createElement("div", { className: "dbfox-workspace__welcome" }, React.createElement(host.ui.ResourceIcon, { kind: "folder", size: 20 }), React.createElement("p", null, "选择文件查看内容"), React.createElement("small", null, "代码高亮 · Markdown 预览")))),
    error ? React.createElement("p", { className: "dbfox-workspace__error", role: "alert" }, error) : null,
  );
}

function FileBrowser({ projectId, binding, path, selectedPath, refreshKey }) {
  const [entries, setEntries] = React.useState([]);
  const [status, setStatus] = React.useState("loading");
  const [reloadKey, setReloadKey] = React.useState(0);
  const [truncated, setTruncated] = React.useState(false);
  React.useEffect(() => {
    const controller = new AbortController();
    setStatus("loading");
    invoke("files.list", { path }, projectId, controller.signal)
      .then((result) => { if (!controller.signal.aborted) { setEntries(result?.entries || []); setTruncated(Boolean(result?.truncated)); setStatus("ready"); } })
      .catch(() => !controller.signal.aborted && setStatus("error"));
    return () => controller.abort();
  }, [projectId, binding.root_digest, path, reloadKey, refreshKey]);
  const rootItem = React.useMemo(() => ({ path: `__root__:${path}`, name: "", is_dir: true, children: entries }), [path, entries]);
  return React.createElement("div", { className: "dbfox-workspace__files" },
    truncated ? React.createElement("p", { className: "dbfox-workspace__status", role: "status" }, "目录过大，当前仅显示部分条目。") : null,
    status === "loading" ? React.createElement("p", { className: "dbfox-workspace__status", role: "status" }, "正在读取…") : null,
    status === "error" ? React.createElement("div", { className: "dbfox-workspace__error", role: "alert" },
      React.createElement("span", null, "无法读取这个目录。"),
      React.createElement("button", { type: "button", onClick: () => setReloadKey((value) => value + 1) }, "重试")) : null,
    status === "ready" && entries.length === 0
      ? React.createElement("p", { className: "dbfox-workspace__status" }, "这个目录是空的。") : null,
    status === "ready" && entries.length > 0
      ? React.createElement(host.ui.Tree, {
          key: `${binding.root_digest}:${reloadKey}:${refreshKey}`,
          rootItem,
          ariaLabel: path ? `工作区目录 ${path}` : "工作区目录",
          getItemId: (entry) => entry.path,
          getItemLabel: (entry) => entry.name,
          getItemChildren: (entry) => entry.children,
          getItemChildrenCount: (entry) => entry.children?.length ?? (entry.is_dir ? 1 : undefined),
          loadItemChildren: async (entry, signal) => {
            const result = await host.operations.invoke("files.list", { path: entry.path }, { projectId, signal });
            if (result.truncated) throw new Error("目录条目超过浏览上限，请使用文件搜索。");
            return result.entries;
          },
          renderItemIcon: (entry, state) => React.createElement(host.ui.ResourceIcon, { name: entry.name, ...(entry.is_dir ? { kind: "folder", expanded: state.expanded } : {}), size: 16 }),
          selectedIds: selectedPath ? [selectedPath] : [],
          defaultExpandedIds: selectedPath ? selectedPath.split("/").slice(0, -1).map((_, index, parts) => parts.slice(0, index + 1).join("/")) : [],
          onItemSelect: (entry) => { if (!entry.is_dir) openFile(projectId, binding, entry.path); },
        }) : null,
  );
}

function FilePreview({ view, context, binding, bindingReady, refreshKey }) {
  const state = view.target?.type === "object"
    && view.target.object.kind === "dbfox.workspace.file"
    && view.target.authority?.kind === "dbfox.workspace.root"
    && view.target.locator
    && view.projectId
    ? {
      projectId: view.projectId,
      path: view.target.locator,
      binding: {
        id: view.target.authority.id,
        root_digest: view.target.object.version,
      },
    } : null;
  const [result, setResult] = React.useState(null);
  const [error, setError] = React.useState("");
  const [readingMore, setReadingMore] = React.useState(false);
  const [reading, setReading] = React.useState(false);
  const readController = React.useRef(null);
  React.useEffect(() => {
    if (!state || !bindingReady) return;
    setError("");
    setReadingMore(false);
    if (state.binding.id !== binding.id || state.binding.root_digest !== binding.root_digest) {
      setResult(null);
      setError("项目文件夹已变化，请从文件树重新选择文件。");
      return;
    }
    const controller = new AbortController();
    readController.current = controller;
    setReading(true);
    invoke("files.read", { path: state.path }, state.projectId, controller.signal)
      .then((value) => !controller.signal.aborted && setResult(value))
      .catch((reason) => !controller.signal.aborted && setError(reason instanceof Error ? reason.message : "无法读取文件。"))
      .finally(() => !controller.signal.aborted && setReading(false));
    return () => {
      controller.abort();
      if (readController.current === controller) readController.current = null;
    };
  }, [state?.projectId, state?.path, state?.binding?.root_digest, binding.id, binding.root_digest, bindingReady, refreshKey]);
  if (!state) return React.createElement("p", null, "文件状态不可用。");
  if (!result) return React.createElement("p", { className: error ? "dbfox-workspace__error" : "dbfox-workspace__status", role: error ? "alert" : "status" }, error || "正在读取文件…");
  const loadedCharacters = Array.from(result.content).length;
  const refreshing = !bindingReady || reading;
  return React.createElement("article", { className: "dbfox-workspace-file", "aria-busy": refreshing || undefined },
    refreshing ? React.createElement("p", { className: "dbfox-workspace__status", role: "status" }, "正在读取最新内容…") : null,
    React.createElement(host.ui.FileContent, { name: state.path, content: result.content,
      onAsk: context?.onAsk ? () => context.onAsk({ label: state.path.split("/").pop(), authority: { kind: "dbfox.workspace.root", id: state.binding.id }, object: { kind: "dbfox.workspace.file", id: state.path, version: state.binding.root_digest }, locator: state.path }) : undefined }),
    error ? React.createElement("p", { className: "dbfox-workspace__error", role: "alert" }, error) : null,
    result.content_truncated ? React.createElement("div", { className: "dbfox-workspace__read-more" },
      React.createElement("span", null, `已显示 ${loadedCharacters.toLocaleString()} 字符`),
      React.createElement("button", { type: "button", disabled: refreshing || readingMore || Boolean(error), onClick: async () => {
        const controller = readController.current;
        if (refreshing || readingMore || error || !controller || controller.signal.aborted) return;
        setReadingMore(true);
        try {
          const next = await invoke("files.read", { path: state.path, offset: loadedCharacters }, state.projectId, controller.signal);
          if (controller.signal.aborted) return;
          if (next.sha256 !== result.sha256) throw new Error("文件已变更，已显示内容来自上次读取。请点击“刷新”重新读取。");
          setResult({ ...next, content: result.content + next.content });
        } catch (reason) { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "读取失败，请刷新后重试。"); }
        finally { if (readController.current === controller) setReadingMore(false); }
      } }, readingMore ? "读取中…" : "继续读取")) : null,
  );
}

function FileDock({ view, context }) {
  return React.createElement(WorkspaceConnector, { projectId: view.projectId || context.activeProjectId, view, context });
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

function WorkspaceArtifact({ artifact, payload, kind, context }) {
  const digest = kind === "snapshot" ? payload.sha256 : payload.newSha256;
  const [result, setResult] = React.useState(null);
  const [error, setError] = React.useState("");
  const [readingMore, setReadingMore] = React.useState(false);
  React.useEffect(() => {
    if (context.surface !== "workspace") return;
    const controller = new AbortController();
    setResult(null);
    setError("");
    context.representations.read(artifact.id, "dbfox.workspace.file.v1", { operation: "read" }, controller.signal)
      .then((value) => { if (!controller.signal.aborted) setResult(value.payload); })
      .catch((reason) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "无法预览文件。"); });
    return () => controller.abort();
  }, [artifact.id, digest, context.surface, context.representations]);
  const state = kind === "snapshot" ? "文件快照" : payload.created ? "文件已创建" : "文件已更新";
  return React.createElement("article", { className: "dbfox-workspace-artifact" },
    React.createElement("header", null,
      React.createElement("span", { className: "dbfox-workspace-artifact__title" },
        React.createElement(host.ui.ResourceIcon, { name: payload.relativePath, size: 20 }),
        React.createElement("strong", null, artifact.title || payload.relativePath)),
      React.createElement("small", null, state),
    ),
    React.createElement("small", { className: "dbfox-workspace-artifact__metadata", title: digest }, `${payload.sizeBytes || 0} 字节 · ${digest.slice(0, 12)}…`),
    context.surface === "workspace"
      ? error ? React.createElement("p", { className: "dbfox-workspace__error", role: "alert" }, error)
        : result ? React.createElement(React.Fragment, null,
          React.createElement(host.ui.FileContent, { name: payload.relativePath, content: result.content, showIdentity: false }),
          result.content_truncated ? React.createElement("div", { className: "dbfox-workspace__read-more" },
            React.createElement("span", null, `已显示 ${Array.from(result.content).length.toLocaleString()} 字符`),
            React.createElement("button", { type: "button", disabled: readingMore, onClick: async () => {
              if (readingMore) return;
              setReadingMore(true);
              try {
                const next = await context.representations.read(artifact.id, "dbfox.workspace.file.v1", {
                  operation: "read", parameters: { offset: Array.from(result.content).length },
                });
                setResult({ ...next.payload, content: result.content + next.payload.content });
              } catch (reason) { setError(reason instanceof Error ? reason.message : "无法继续读取文件。"); }
              finally { setReadingMore(false); }
            } }, readingMore ? "读取中…" : "继续读取")) : null)
          : React.createElement("p", { className: "dbfox-workspace__status", role: "status" }, "正在读取文件…")
      : null,
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
    icon: React.createElement(host.ui.ResourceIcon, { kind: "folder", size: 16 }),
    listResources: async ({ projectId }) => {
      const result = await invoke("binding.get", {}, projectId);
      const binding = result?.binding;
      if (!binding) return [];
      return [{
        kind: "dbfox.workspace.binding",
        id: binding.id,
        name: binding.root_path,
        detail: `目录绑定 · ${binding.updated_at || ""}`,
      }];
    },
    removeResource: async ({ projectId }) => {
      await invoke("binding.delete", {}, projectId);
    },
    render: ({ projectId }) => React.createElement(WorkspaceConnector, { projectId }),
  });
  host.dockViews.register({
    viewType: FILE_VIEW_TYPE,
    objectKinds: ["dbfox.workspace.file"],
    icon: (view) => React.createElement(host.ui.ResourceIcon, { name: view.title, size: 16 }),
    resolveTitle: (view) => view.target?.locator?.split("/").pop() || view.title,
    isVisible: (view, context) => !view.projectId || view.projectId === context.activeProjectId,
    render: (view, context) => React.createElement(FileDock, { view, context }),
  });
  host.artifactViews.register({
    id: "dbfox.workspace.file-snapshot",
    title: "文件快照",
    priority: 60,
    surfaces: ["inline", "workspace"],
    artifactTypes: [{ type: FILE_SNAPSHOT_TYPE, schemaVersions: [1] }],
    parsePayload: parseFileSnapshot,
    render: (artifact, payload, context) => React.createElement(WorkspaceArtifact, { artifact, payload, kind: "snapshot", context }),
  });
  host.artifactViews.register({
    id: "dbfox.workspace.code-patch",
    title: "代码变更",
    priority: 60,
    surfaces: ["inline", "workspace"],
    artifactTypes: [{ type: CODE_PATCH_TYPE, schemaVersions: [1] }],
    parsePayload: parseCodePatch,
    render: (artifact, payload, context) => React.createElement(WorkspaceArtifact, { artifact, payload, kind: "patch", context }),
  });
}

export function deactivate() {
  bindings.clear();
  listeners.clear();
  if (typeof document !== "undefined") document.querySelectorAll(`link[data-dbfox-dlc="${DLC_ID}"]`).forEach((link) => link.remove());
  host = undefined;
  React = undefined;
}
