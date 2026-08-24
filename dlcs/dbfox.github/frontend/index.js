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
  const stateKey = `${projectId}:${binding.id}:${path}`;
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
    target: { type: "resource", kind: "dbfox.github.repository", id: binding.id, version: binding.resolved_revision },
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
      bindings.map((binding) => React.createElement("button", {
        key: binding.id,
        type: "button",
        className: `dbfox-github__binding ${binding.id === selected?.id ? "is-active" : ""}`,
        onClick: () => { selectedBindingByProject.set(projectId, binding.id); emitChange(); },
      },
      React.createElement("span", null, `${binding.owner}/${binding.repository}`),
      React.createElement("small", null, `${binding.ref_name} · ${binding.resolved_revision.slice(0, 7)}`),
      React.createElement("span", {
        role: "button",
        tabIndex: 0,
        className: "dbfox-github__remove",
        onClick: (event) => { event.stopPropagation(); void removeBinding(binding); },
        onKeyDown: (event) => { if (event.key === "Enter") void removeBinding(binding); },
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

  React.useEffect(() => {
    let active = true;
    setStatus("loading");
    invoke("files.list", { binding_id: binding.id, path, limit: 100 }, projectId)
      .then((result) => {
        if (active) { setEntries(Array.isArray(result?.entries) ? result.entries : []); setStatus("ready"); }
      })
      .catch(() => active && setStatus("error"));
    return () => { active = false; };
  }, [projectId, binding.id, binding.resolved_revision, path]);

  return React.createElement("div", { className: "dbfox-github__files" },
    path ? React.createElement("button", {
      type: "button",
      className: "dbfox-github__up",
      onClick: () => setPath(path.includes("/") ? path.slice(0, path.lastIndexOf("/")) : ""),
    }, "← Up") : null,
    status === "loading" ? React.createElement("p", null, "Loading files…") : null,
    status === "error" ? React.createElement("p", { className: "dbfox-github__error" }, "Unable to list this directory.") : null,
    entries.map((entry) => React.createElement("button", {
      key: entry.path,
      type: "button",
      className: "dbfox-github__file",
      onClick: () => entry.type === "dir" ? setPath(entry.path) : openFile(projectId, binding, entry.path),
    }, React.createElement("span", null, entry.type === "dir" ? "▸" : "·"), entry.path.split("/").pop() || entry.path)),
  );
}

function GithubFileDock({ view }) {
  const state = fileStateByKey.get(view.stateKey || "");
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

function GithubArtifact({ artifact }) {
  const payload = parseArtifactPayload(artifact.payload);
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
  host.artifactRenderers.register({
    type: FILE_ARTIFACT_TYPE,
    supportedSchemaVersions: [1],
    parsePayload: parseArtifactPayload,
    render: (artifact) => React.createElement(GithubArtifact, { artifact }),
  });
}

export const __testing = Object.freeze({
  DLC_ID,
  FILE_VIEW_TYPE,
  FILE_ARTIFACT_TYPE,
  parseArtifactPayload,
});
