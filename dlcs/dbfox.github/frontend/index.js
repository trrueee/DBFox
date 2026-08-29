const DLC_ID = "dbfox.github";
const FILE_VIEW_TYPE = "dbfox.github.file";
const FILE_ARTIFACT_TYPE = "dbfox.github.file_snapshot";

let extensionHost;
let React;
const bindingsByProject = new Map();
const selectedBindingByProject = new Map();
const loadedProjects = new Set();
const fileStateByKey = new Map();
const addFormProjects = new Set();
const listeners = new Set();

function emitChange() {
  for (const listener of listeners) listener();
}

function useModuleVersion() {
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
  const current = document.querySelectorAll(`link[data-dbfox-dlc="${DLC_ID}"]`);
  for (const link of current) {
    if (link.getAttribute("href") === href) return;
    link.remove();
  }
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = href;
  link.dataset.dbfoxDlc = DLC_ID;
  document.head.appendChild(link);
}

async function invoke(operation, input, projectId) {
  return extensionHost.operations.invoke(operation, input, { projectId });
}

async function loadBindings(projectId) {
  const result = await invoke("bindings.list", {}, projectId);
  const bindings = Array.isArray(result?.bindings) ? result.bindings : [];
  bindingsByProject.set(projectId, bindings);
  loadedProjects.add(projectId);
  const selected = selectedBindingByProject.get(projectId);
  if (!selected || !bindings.some((binding) => binding.id === selected)) {
    if (bindings[0]) selectedBindingByProject.set(projectId, bindings[0].id);
    else selectedBindingByProject.delete(projectId);
  }
  emitChange();
  return bindings;
}

function openFile(projectId, binding, path) {
  const stateKey = `${extensionHost.workbench.currentScopeId()}:${projectId}:${binding.id}:${path}`;
  fileStateByKey.set(stateKey, {
    projectId,
    bindingId: binding.id,
    owner: binding.owner,
    repository: binding.repository,
    revision: binding.resolved_revision,
    path,
  });
  extensionHost.dockViews.open({
    viewKey: `github-file:${stateKey}`,
    viewType: FILE_VIEW_TYPE,
    title: path.split("/").pop() || path,
    closeable: true,
    projectId,
    stateKey,
    target: {
      type: "object",
      object: { kind: "dbfox.github.file", id: path, version: binding.resolved_revision },
      authority: { kind: "dbfox.github.repository", id: binding.id },
      locator: path,
    },
  });
}

function GithubConnector({ projectId }) {
  useModuleVersion();
  const [loading, setLoading] = React.useState(!loadedProjects.has(projectId));
  const [error, setError] = React.useState("");
  const [repository, setRepository] = React.useState("");
  const [refName, setRefName] = React.useState("");

  React.useEffect(() => {
    let active = true;
    setLoading(true);
    loadBindings(projectId)
      .catch((reason) => active && setError(reason instanceof Error ? reason.message : String(reason)))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [projectId]);

  const bindings = bindingsByProject.get(projectId) || [];
  const selectedId = selectedBindingByProject.get(projectId);
  const selected = bindings.find((binding) => binding.id === selectedId) || bindings[0];

  async function submit(event) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      await invoke("bindings.create", { repository: repository.trim(), ref_name: refName.trim() }, projectId);
      setRepository("");
      setRefName("");
      addFormProjects.delete(projectId);
      await loadBindings(projectId);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
    }
  }

  async function removeBinding(binding) {
    if (!globalThis.confirm?.(`Remove ${binding.owner}/${binding.repository}?`)) return;
    setLoading(true);
    try {
      await invoke("bindings.delete", { binding_id: binding.id }, projectId);
      await loadBindings(projectId);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
    }
  }

  return React.createElement("section", { className: "dbfox-github" },
    React.createElement("div", { className: "dbfox-github__bindings" },
      bindings.map((binding) => React.createElement("div", {
        key: binding.id,
        className: "dbfox-github__binding-row",
      },
        React.createElement("button", {
          type: "button",
          className: `dbfox-github__binding ${binding.id === selected?.id ? "is-active" : ""}`,
          onClick: () => { selectedBindingByProject.set(projectId, binding.id); emitChange(); },
        },
        React.createElement("span", null, `${binding.owner}/${binding.repository}`),
        React.createElement("small", null, `${binding.ref_name} · ${binding.resolved_revision.slice(0, 7)}`)),
        React.createElement("button", {
          type: "button",
          className: "dbfox-github__remove",
          onClick: () => void removeBinding(binding),
          "aria-label": `移除 ${binding.owner}/${binding.repository}`,
          title: "移除仓库",
        }, "×"))),
    ),
    addFormProjects.has(projectId) || bindings.length === 0
      ? React.createElement("form", { className: "dbfox-github__form", onSubmit: submit },
          React.createElement("input", {
            value: repository,
            required: true,
            placeholder: "owner/repository",
            "aria-label": "GitHub repository",
            onChange: (event) => setRepository(event.target.value),
          }),
          React.createElement("input", {
            value: refName,
            placeholder: "branch or tag (optional)",
            "aria-label": "GitHub revision",
            onChange: (event) => setRefName(event.target.value),
          }),
          React.createElement("button", { type: "submit", disabled: loading }, loading ? "Adding…" : "Add repository"),
        )
      : null,
    error ? React.createElement("p", { className: "dbfox-github__error", role: "alert" }, error) : null,
    loading && bindings.length === 0 ? React.createElement("p", null, "Loading GitHub repositories…") : null,
    selected ? React.createElement(GithubFileBrowser, { projectId, binding: selected }) : null,
  );
}

function GithubFileBrowser({ projectId, binding }) {
  const [path, setPath] = React.useState("");
  const [entries, setEntries] = React.useState([]);
  const [status, setStatus] = React.useState("loading");
  const [reloadKey, setReloadKey] = React.useState(0);

  React.useEffect(() => {
    let active = true;
    setStatus("loading");
    invoke("files.list", { binding_id: binding.id, path, limit: 100 }, projectId)
      .then((result) => {
        if (active) { setEntries(Array.isArray(result?.entries) ? result.entries : []); setStatus("ready"); }
      })
      .catch(() => active && setStatus("error"));
    return () => { active = false; };
  }, [projectId, binding.id, binding.resolved_revision, path, reloadKey]);

  const rootItem = { path: `__root__:${path}`, name: "", type: "dir", children: entries };
  return React.createElement("div", { className: "dbfox-github__files" },
    path ? React.createElement("button", {
      type: "button",
      className: "dbfox-github__up",
      onClick: () => setPath(path.includes("/") ? path.slice(0, path.lastIndexOf("/")) : ""),
    }, "← Up") : null,
    status === "loading" ? React.createElement("p", { role: "status" }, "Loading files…") : null,
    status === "error" ? React.createElement("div", { className: "dbfox-github__error", role: "alert" },
      React.createElement("span", null, "Unable to list this directory."),
      React.createElement("button", { type: "button", onClick: () => setReloadKey((value) => value + 1) }, "Retry")) : null,
    status === "ready" && entries.length === 0 ? React.createElement("p", null, "This directory is empty.") : null,
    status === "ready" && entries.length > 0
      ? React.createElement(host.ui.Tree, {
          key: path,
          rootItem,
          ariaLabel: path ? `GitHub directory ${path}` : "GitHub repository files",
          getItemId: (entry) => entry.path,
          getItemLabel: (entry) => entry.path.split("/").pop() || entry.path,
          getItemChildren: (entry) => entry.children,
          onItemSelect: (entry) => entry.type === "dir"
            ? setPath(entry.path)
            : openFile(projectId, binding, entry.path),
        }) : null,
  );
}

function GithubFileDock({ view }) {
  const stateKey = view.stateKey || "";
  let state = fileStateByKey.get(stateKey);
  if (
    !state
    && view.target?.type === "object"
    && view.target.object.kind === "dbfox.github.file"
    && view.target.authority?.kind === "dbfox.github.repository"
    && view.target.locator
    && view.projectId
  ) {
    state = {
      projectId: view.projectId,
      bindingId: view.target.authority.id,
      owner: "GitHub",
      repository: view.target.authority.id,
      revision: view.target.object.version,
      path: view.target.locator,
    };
    fileStateByKey.set(stateKey, state);
  }
  const [result, setResult] = React.useState(null);
  const [error, setError] = React.useState("");
  React.useEffect(() => {
    if (!state) return;
    let active = true;
    invoke("files.read", { binding_id: state.bindingId, path: state.path }, state.projectId)
      .then((value) => active && setResult(value))
      .catch((reason) => active && setError(reason instanceof Error ? reason.message : String(reason)));
    return () => { active = false; };
  }, [state?.projectId, state?.bindingId, state?.path]);
  if (!state) return React.createElement("p", { className: "dbfox-github__error" }, "GitHub file state is unavailable.");
  if (error) return React.createElement("p", { className: "dbfox-github__error" }, error);
  if (!result) return React.createElement("p", null, "Loading GitHub file…");
  return React.createElement("article", { className: "dbfox-github-file" },
    React.createElement("header", null,
      React.createElement("strong", null, state.path),
      React.createElement("span", null, `${state.owner}/${state.repository} @ ${result.revision.slice(0, 7)}`),
    ),
    React.createElement("pre", null, React.createElement("code", null, result.content)),
  );
}

function parseArtifactPayload(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Invalid GitHub file snapshot payload");
  for (const field of ["repositoryBindingId", "owner", "repository", "revision", "relativePath", "blobSha", "contentSha256"]) {
    if (typeof value[field] !== "string" || !value[field]) throw new Error(`GitHub file snapshot requires ${field}`);
  }
  return value;
}

function GithubArtifact({ artifact, payload }) {
  return React.createElement("article", { className: "dbfox-github-artifact" },
    React.createElement("strong", null, artifact.title || payload.relativePath),
    React.createElement("code", null, payload.relativePath),
    React.createElement("small", null, `${payload.owner}/${payload.repository} @ ${payload.revision.slice(0, 7)} · ${payload.sizeBytes || 0} bytes`),
  );
}

export function register(host) {
  extensionHost = host;
  React = globalThis.__DBFOX_EXTENSION_HOST__?.React;
  if (!React) throw new Error("DBFox React host is unavailable");
  ensureStylesheet();

  host.connectors.register({
    id: DLC_ID,
    title: "GitHub",
    icon: React.createElement("span", { "aria-hidden": true }, "GH"),
    addLabel: "Add GitHub repository",
    listResources: async ({ projectId }) => {
      const bindings = await loadBindings(projectId);
      return bindings.map((binding) => ({
        kind: "dbfox.github.binding",
        id: binding.id,
        name: binding.repository,
        detail: binding.ref_name ? `ref ${binding.ref_name}` : undefined,
      }));
    },
    removeResource: async ({ projectId }, resource) => {
      await invoke("bindings.delete", { binding_id: resource.id }, projectId);
      await loadBindings(projectId);
    },
    onAdd: ({ projectId }) => { addFormProjects.add(projectId); emitChange(); },
    render: ({ projectId }) => React.createElement(GithubConnector, { projectId }),
  });
  host.dockViews.register({
    viewType: FILE_VIEW_TYPE,
    icon: () => React.createElement("span", { "aria-hidden": true }, "GH"),
    resolveTitle: (view) => fileStateByKey.get(view.stateKey || "")?.path.split("/").pop() || view.title,
    isVisible: (view, context) => !view.projectId || view.projectId === context.activeProjectId,
    render: (view) => React.createElement(GithubFileDock, { view }),
  });
  host.artifactViews.register({
    id: "dbfox.github.file",
    title: "文件",
    priority: 60,
    surfaces: ["inline", "workspace"],
    artifactTypes: [{ type: FILE_ARTIFACT_TYPE, schemaVersions: [1] }],
    parsePayload: parseArtifactPayload,
    render: (artifact, payload) => React.createElement(GithubArtifact, { artifact, payload }),
  });
}

export function deactivate() {
  bindingsByProject.clear();
  selectedBindingByProject.clear();
  loadedProjects.clear();
  fileStateByKey.clear();
  addFormProjects.clear();
  listeners.clear();
  if (typeof document !== "undefined") document.querySelectorAll(`link[data-dbfox-dlc="${DLC_ID}"]`).forEach((link) => link.remove());
  extensionHost = undefined;
  React = undefined;
}

export const __testing = Object.freeze({
  DLC_ID,
  FILE_VIEW_TYPE,
  FILE_ARTIFACT_TYPE,
  parseArtifactPayload,
});
