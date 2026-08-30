const DLC_ID = "dbfox.story";
const WORKBENCH_VIEW = "dbfox.story.workbench";

let host;
let React;
const listeners = new Set();
const worldByProject = new Map();
const entitiesByProject = new Map();
const edgesByProject = new Map();
const revisionsByProject = new Map();
const loadedProjects = new Set();
const posByProject = new Map();
let selectedEntityByProject = new Map();
let lastError = null;

function emit() {
  for (const listener of listeners) listener();
}

function useDlcState(projectId) {
  const [, force] = React.useState(0);
  React.useEffect(() => {
    const listener = () => force((value) => value + 1);
    listeners.add(listener);
    return () => listeners.delete(listener);
  }, []);
  return {
    world: worldByProject.get(projectId) || null,
    entities: entitiesByProject.get(projectId) || [],
    edges: edgesByProject.get(projectId) || [],
    revisions: revisionsByProject.get(projectId) || [],
    selectedId: selectedEntityByProject.get(projectId) || null,
    error: lastError,
  };
}

async function invoke(operation, input, projectId) {
  return host.operations.invoke(operation, input, { projectId });
}

async function loadAll(projectId) {
  try {
    const world = await invoke("worlds.get", {}, projectId);
    worldByProject.set(projectId, world || null);
    const [entities, edgeList, revisions] = await Promise.all([
      invoke("entities.list", {}, projectId),
      invoke("relations.list", {}, projectId),
      invoke("revisions.list", {}, projectId),
    ]);
    entitiesByProject.set(projectId, entities?.entities || []);
    edgesByProject.set(projectId, edgeList?.edges || []);
    revisionsByProject.set(projectId, revisions?.revisions || []);
    lastError = null;
    loadedProjects.add(projectId);
  } catch (error) {
    lastError = String(error && error.message ? error.message : error);
  }
  emit();
}

function posKey(projectId) {
  return `dbfox.story.pos:${projectId}`;
}

function loadPositions(projectId) {
  let positions = posByProject.get(projectId);
  if (!positions) {
    try {
      positions = JSON.parse(window.localStorage.getItem(posKey(projectId)) || "{}");
    } catch {
      positions = {};
    }
    posByProject.set(projectId, positions);
  }
  return positions;
}

function savePosition(projectId, entityId, x, y) {
  const positions = loadPositions(projectId);
  positions[entityId] = { x: Math.round(x), y: Math.round(y) };
  window.localStorage.setItem(posKey(projectId), JSON.stringify(positions));
}

function defaultPosition(index) {
  const angle = index * 2.399963; // golden-angle spread: deterministic, no LLM
  return { x: 300 + 150 * Math.cos(angle), y: 190 + 110 * Math.sin(angle) };
}

const KIND_LABELS = { character: "人物", scene: "场景", plotline: "情节线" };

function entityLabel(entity) {
  return entity.name;
}

async function addEntity(projectId, kind, name, summary) {
  await invoke("entities.create", { kind, name, summary }, projectId);
  await loadEntitiesOnly(projectId);
}

async function loadEntitiesOnly(projectId) {
  const entities = await invoke("entities.list", {}, projectId);
  entitiesByProject.set(projectId, entities?.entities || []);
  emit();
}

async function deleteEntity(projectId, entityId) {
  await invoke("entities.delete", { entity_id: entityId }, projectId);
  if (selectedEntityByProject.get(projectId) === entityId) {
    selectedEntityByProject.delete(projectId);
  }
  await loadAll(projectId);
}

async function decide(projectId, edgeId, decision) {
  await invoke("relations.decide", { edge_id: edgeId, decision }, projectId);
  await loadAll(projectId);
}

async function decideBatch(projectId, decisions) {
  await invoke("relations.decide_batch", { decisions }, projectId);
  await loadAll(projectId);
}

async function proposeManual(projectId, fromName, toName, kind, reason) {
  await invoke(
    "relations.propose",
    { relations: [{ from_name: fromName, to_name: toName, kind, reason }] },
    projectId,
  );
  await loadAll(projectId);
}

async function commitRevision(projectId, note) {
  const revision = await invoke("revisions.commit", { note }, projectId);
  await loadAll(projectId);
  return revision;
}

function StoryConnector({ projectId }) {
  const state = useDlcState(projectId);
  React.useEffect(() => {
    if (!loadedProjects.has(projectId)) void loadAll(projectId);
  }, [projectId]);
  const pending = state.edges.filter((edge) => edge.status === "pending").length;
  return React.createElement(
    "div",
    { className: "story-connector" },
    React.createElement(
      "p",
      { className: "story-connector__meta" },
      `${state.entities.length} 个实体 · ${state.edges.filter((edge) => edge.status === "confirmed").length} 条既定关系` + (pending ? ` · ${pending} 条待审` : ""),
    ),
    React.createElement(
      "button",
      {
        type: "button",
        className: "story-connector__open",
        onClick: () => openWorkbench(projectId),
      },
      "打开故事工作台",
    ),
  );
}

function openWorkbench(projectId) {
  const world = worldByProject.get(projectId);
  host.dockViews.open({
    viewKey: `${WORKBENCH_VIEW}:${projectId}`,
    viewType: WORKBENCH_VIEW,
    title: `${world?.title || "故事"} · 工作台`,
    closeable: true,
    projectId,
  });
}

function StoryWorkbench({ projectId }) {
  const state = useDlcState(projectId);
  const [form, setForm] = React.useState({ kind: "character", name: "", summary: "" });
  const [edgeForm, setEdgeForm] = React.useState({ from: "", to: "", kind: "", reason: "" });
  const [revisionNote, setRevisionNote] = React.useState("");
  const [busy, setBusy] = React.useState(false);

  React.useEffect(() => {
    if (!loadedProjects.has(projectId)) void loadAll(projectId);
  }, [projectId]);

  const pending = state.edges.filter((edge) => edge.status === "pending");
  const rejected = state.edges.filter((edge) => edge.status === "rejected");
  const confirmed = state.edges.filter((edge) => edge.status === "confirmed");
  const selected = state.entities.find((entity) => entity.id === state.selectedId) || null;

  const positions = loadPositions(projectId);
  state.entities.forEach((entity, index) => {
    if (!positions[entity.id]) {
      positions[entity.id] = defaultPosition(index);
    }
  });

  const nodeAt = (entityId) => positions[entityId] || { x: 40, y: 40 };

  const startDrag = (event, entityId) => {
    event.preventDefault();
    const svg = event.currentTarget.ownerSVGElement;
    if (!svg) return;
    const move = (moveEvent) => {
      const rect = svg.getBoundingClientRect();
      const x = ((moveEvent.clientX - rect.left) / rect.width) * 640;
      const y = ((moveEvent.clientY - rect.top) / rect.height) * 380;
      savePosition(projectId, entityId, Math.min(620, Math.max(10, x)), Math.min(360, Math.max(14, y)));
      emit();
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };

  const submitEntity = async (event) => {
    event.preventDefault();
    if (!form.name.trim() || busy) return;
    setBusy(true);
    try {
      await addEntity(projectId, form.kind, form.name.trim(), form.summary.trim());
      setForm({ kind: form.kind, name: "", summary: "" });
    } catch (error) {
      lastError = String(error && error.message ? error.message : error);
      emit();
    } finally {
      setBusy(false);
    }
  };

  const submitEdge = async (event) => {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    try {
      await proposeManual(
        projectId,
        edgeForm.from.trim(),
        edgeForm.to.trim(),
        edgeForm.kind.trim() || "关联",
        edgeForm.reason.trim(),
      );
      setEdgeForm({ from: "", to: "", kind: "", reason: "" });
    } catch (error) {
      lastError = String(error && error.message ? error.message : error);
      emit();
    } finally {
      setBusy(false);
    }
  };

  const treeRoot = {
    id: "story-root",
    label: state.world?.title || "故事世界",
    branches: [
      { id: "branch-character", label: "人物", kind: "character" },
      { id: "branch-scene", label: "场景", kind: "scene" },
      { id: "branch-plotline", label: "情节线", kind: "plotline" },
    ],
  };
  const items = new Map();
  const kindBranches = [
    { id: "branch:character", label: "人物", kind: "character" },
    { id: "branch:scene", label: "场景", kind: "scene" },
    { id: "branch:plotline", label: "情节线", kind: "plotline" },
  ];
  items.set("story-root", {
    id: "story-root",
    label: state.world?.title || "故事世界",
    children: kindBranches.map((branch) => branch.id),
  });
  for (const branch of kindBranches) {
    branch.children = state.entities
      .filter((entity) => entity.kind === branch.kind)
      .map((entity) => entity.id);
    items.set(branch.id, branch);
  }
  for (const entity of state.entities) {
    items.set(entity.id, { ...entity, children: undefined });
  }
  const rootItem = items.get("story-root");
  const resolveItem = (id) => items.get(id);

  return React.createElement(
    "div",
    { className: "story-workbench" },
    React.createElement(
      "div",
      { className: "story-workbench__tree" },
      state.error ? React.createElement("p", { className: "story-workbench__error" }, state.error) : null,
      rootItem && host.ui?.Tree
        ? React.createElement(host.ui.Tree, {
            ariaLabel: "故事实体",
            rootItem,
            getItemId: (item) => item.id,
            getItemLabel: (item) => (item.name ? entityLabel(item) : item.label),
            getItemChildren: (item) =>
              item.children ? item.children.map(resolveItem).filter(Boolean) : undefined,
            getItemChildrenCount: (item) =>
              item.children ? item.children.length : undefined,
            selectedIds: state.selectedId ? [state.selectedId] : [],
            onItemSelect: (item) => {
              if (item.name !== undefined) {
                selectedEntityByProject.set(projectId, item.id);
                emit();
              }
            },
            renderBranchFooter: (branch) =>
              React.createElement(
                "button",
                {
                  type: "button",
                  className: "story-tree__add",
                  onClick: () => setForm({ kind: branch.kind, name: "", summary: "" }),
                },
                "+ 新增",
              ),
          })
        : React.createElement("p", null, "故事世界载入中…"),
      React.createElement(
        "form",
        { className: "story-entity-form", onSubmit: submitEntity },
        React.createElement(
          "select",
          {
            value: form.kind,
            onChange: (event) => setForm({ ...form, kind: event.target.value }),
            "aria-label": "实体类型",
          },
          React.createElement("option", { value: "character" }, "人物"),
          React.createElement("option", { value: "scene" }, "场景"),
          React.createElement("option", { value: "plotline" }, "情节线"),
        ),
        React.createElement("input", {
          value: form.name,
          onChange: (event) => setForm({ ...form, name: event.target.value }),
          placeholder: "名称",
          "aria-label": "实体名称",
        }),
        React.createElement("input", {
          value: form.summary,
          onChange: (event) => setForm({ ...form, summary: event.target.value }),
          placeholder: "设定摘要（可选）",
          "aria-label": "实体摘要",
        }),
        React.createElement(
          "button",
          { type: "submit", disabled: busy || !form.name.trim() },
          "新增实体",
        ),
      ),
      selected
        ? React.createElement(
            "div",
            { className: "story-entity-detail" },
            React.createElement("strong", null, `${KIND_LABELS[selected.kind] || selected.kind} · ${selected.name}`),
            React.createElement("p", null, selected.summary || "（无设定摘要）"),
            React.createElement(
              "button",
              {
                type: "button",
                onClick: () => void deleteEntity(projectId, selected.id).catch(() => emit()),
              },
              "删除实体（连带其关系）",
            ),
          )
        : null,
    ),
    React.createElement(
      "div",
      { className: "story-workbench__main" },
      React.createElement(
        "div",
        { className: "story-canvas-card" },
        React.createElement(
          "div",
          { className: "story-canvas-card__legend" },
          React.createElement("span", { className: "story-legend story-legend--confirmed" }, "已确认"),
          React.createElement("span", { className: "story-legend story-legend--pending" }, "待审"),
          React.createElement("span", { className: "story-legend story-legend--rejected" }, "已否决（保留记录）"),
        ),
        React.createElement(
          "svg",
          {
            className: "story-canvas",
            viewBox: "0 0 640 380",
            role: "img",
            "aria-label": "关系画布",
          },
          state.edges.map((edge) => {
            const from = nodeAt(edge.from_entity_id);
            const to = nodeAt(edge.to_entity_id);
            const className =
              edge.status === "confirmed"
                ? "story-edge story-edge--confirmed"
                : edge.status === "pending"
                  ? "story-edge story-edge--pending"
                  : "story-edge story-edge--rejected";
            return React.createElement(
              "g",
              { key: edge.id, className },
              React.createElement("line", {
                x1: from.x,
                y1: from.y,
                x2: to.x,
                y2: to.y,
              }),
              edge.status !== "rejected"
                ? React.createElement(
                    "text",
                    { x: (from.x + to.x) / 2, y: (from.y + to.y) / 2 - 4, textAnchor: "middle" },
                    edge.kind,
                  )
                : null,
            );
          }),
          state.entities.map((entity) => {
            const point = nodeAt(entity.id);
            return React.createElement(
              "g",
              {
                key: entity.id,
                className: "story-node",
                transform: `translate(${point.x}, ${point.y})`,
                onPointerDown: (event) => startDrag(event, entity.id),
                onClick: () => {
                  selectedEntityByProject.set(projectId, entity.id);
                  emit();
                },
              },
              React.createElement("circle", { r: 14 }),
              React.createElement(
                "text",
                { y: 28, textAnchor: "middle" },
                entity.name,
              ),
            );
          }),
        ),
      ),
      React.createElement(
        "div",
        { className: "story-review" },
        React.createElement(
          "form",
          { className: "story-edge-form", onSubmit: submitEdge },
          React.createElement("input", {
            value: edgeForm.from,
            onChange: (event) => setEdgeForm({ ...edgeForm, from: event.target.value }),
            placeholder: "从…",
            "aria-label": "关系起点",
          }),
          React.createElement("input", {
            value: edgeForm.to,
            onChange: (event) => setEdgeForm({ ...edgeForm, to: event.target.value }),
            placeholder: "到…",
            "aria-label": "关系终点",
          }),
          React.createElement("input", {
            value: edgeForm.kind,
            onChange: (event) => setEdgeForm({ ...edgeForm, kind: event.target.value }),
            placeholder: "关系类型",
            "aria-label": "关系类型",
          }),
          React.createElement("input", {
            value: edgeForm.reason,
            onChange: (event) => setEdgeForm({ ...edgeForm, reason: event.target.value }),
            placeholder: "理由（可选）",
            "aria-label": "关系理由",
          }),
          React.createElement(
            "button",
            { type: "submit", disabled: busy || !edgeForm.from.trim() || !edgeForm.to.trim() },
            "加入待审",
          ),
        ),
        React.createElement(
          "div",
          { className: "story-review__section" },
          React.createElement(
            "div",
            { className: "story-review__header" },
            React.createElement("strong", null, `待审提案（${pending.length}）`),
            pending.length
              ? React.createElement(
                  "button",
                  {
                    type: "button",
                    disabled: busy,
                    onClick: () =>
                      void decideBatch(
                        projectId,
                        pending.map((edge) => ({ edge_id: edge.id, decision: "confirmed" })),
                      ).catch(() => emit()),
                  },
                  "全部接受",
                )
              : null,
          ),
          pending.length
            ? pending.map((edge) =>
                React.createElement(
                  "div",
                  { className: "story-review__row", key: edge.id },
                  React.createElement(
                    "span",
                    { className: "story-review__copy" },
                    React.createElement("strong", null, `${edge.from_name} —${edge.kind}→ ${edge.to_name}`),
                    edge.reason ? React.createElement("small", null, edge.reason) : null,
                  ),
                  React.createElement(
                    "button",
                    {
                      type: "button",
                      disabled: busy,
                      onClick: () => void decide(projectId, edge.id, "confirmed").catch(() => emit()),
                    },
                    "接受",
                  ),
                  React.createElement(
                    "button",
                    {
                      type: "button",
                      disabled: busy,
                      onClick: () => void decide(projectId, edge.id, "rejected").catch(() => emit()),
                    },
                    "否决",
                  ),
                ),
              )
            : React.createElement("p", { className: "story-review__empty" }, "没有待审提案。"),
        ),
        rejected.length
          ? React.createElement(
              "div",
              { className: "story-review__section" },
              React.createElement(
                "div",
                { className: "story-review__header" },
                React.createElement("strong", null, `已否决（${rejected.length}，保留供 AI 规避）`),
              ),
              rejected.map((edge) =>
                React.createElement(
                  "div",
                  { className: "story-review__row story-review__row--rejected", key: edge.id },
                  React.createElement(
                    "span",
                    { className: "story-review__copy" },
                    React.createElement("strong", null, `${edge.from_name} —${edge.kind}→ ${edge.to_name}`),
                    edge.reason ? React.createElement("small", null, edge.reason) : null,
                  ),
                  React.createElement(
                    "button",
                    {
                      type: "button",
                      disabled: busy,
                      onClick: () => void decide(projectId, edge.id, "pending").catch(() => emit()),
                    },
                    "恢复待审",
                  ),
                ),
              ),
            )
          : null,
        React.createElement(
          "div",
          { className: "story-review__section" },
          React.createElement(
            "div",
            { className: "story-review__header" },
            React.createElement("strong", null, `不可变修订（${state.revisions.length}）`),
            confirmed.length
              ? React.createElement(
                  "form",
                  { onSubmit: async (event) => {
                      event.preventDefault();
                      if (busy) return;
                      setBusy(true);
                      try {
                        await commitRevision(projectId, revisionNote.trim());
                        setRevisionNote("");
                      } finally {
                        setBusy(false);
                      }
                    } },
                  React.createElement("input", {
                    value: revisionNote,
                    onChange: (event) => setRevisionNote(event.target.value),
                    placeholder: "修订说明（可选）",
                    "aria-label": "修订说明",
                  }),
                  React.createElement(
                    "button",
                    { type: "submit", disabled: busy },
                    `提交修订（${confirmed.length} 条）`,
                  ),
                )
              : null,
          ),
          state.revisions.length
            ? state.revisions.map((revision) =>
                React.createElement(
                  "div",
                  { className: "story-review__row", key: revision.id },
                  React.createElement(
                    "span",
                    { className: "story-review__copy" },
                    React.createElement(
                      "strong",
                      null,
                      `r${revision.seq} · ${revision.confirmed_count} 条关系`,
                    ),
                    revision.note ? React.createElement("small", null, revision.note) : null,
                  ),
                ),
              )
            : React.createElement(
                "p",
                { className: "story-review__empty" },
                "确认关系后提交为不可变修订，之后可由 Agent 查询比对。",
              ),
        ),
      ),
    ),
  );
}

export function register(extensionHost) {
  host = extensionHost;
  React = globalThis.__DBFOX_EXTENSION_HOST__?.React;
  if (!React) throw new Error("DBFox React host is unavailable");
  ensureStylesheet();
  host.connectors.register({
    id: DLC_ID,
    title: "故事",
    icon: React.createElement("span", { "aria-hidden": true }, "✒"),
    addLabel: "创建故事世界",
    onAdd: ({ projectId }) => {
      void (async () => {
        await invoke("worlds.ensure", {}, projectId);
        await loadAll(projectId);
        openWorkbench(projectId);
      })().catch(() => emit());
    },
    render: ({ projectId }) => React.createElement(StoryConnector, { projectId }),
  });
  host.dockViews.register({
    viewType: WORKBENCH_VIEW,
    icon: () => React.createElement("span", { "aria-hidden": true }, "✒"),
    resolveTitle: (view) => `${worldByProject.get(view.projectId)?.title || "故事"} · 工作台`,
    isVisible: (view, context) => !view.projectId || view.projectId === context.activeProjectId,
    render: (view, context) =>
      React.createElement(StoryWorkbench, {
        projectId: view.projectId || context.activeProjectId,
      }),
  });
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

if (typeof window !== "undefined" && window.__DBFOX_STORY_TEST__) {
  window.__DBFOX_STORY_TEST__ = {
    ...window.__DBFOX_STORY_TEST__,
    addEntity,
    decide,
    proposeManual,
    commitRevision,
    loadAll,
  };
}
