import type {
  ConversationArtifact,
  ConversationRun,
  ConversationRunItem,
  ConversationStreamEvent,
  RunItemDeltaEnvelope,
} from "../types/conversation";
import type { ConversationStore } from "./conversationStore";
import {
  isTerminalRun,
  isTerminalRunItem,
} from "../features/conversation/conversationState";
import { mergeProjectionById } from "./conversationProjection";

export function removeConversationState(
  state: ConversationStore,
  conversationId: string,
): ConversationStore {
  const runIds = new Set(
    state.detailById[conversationId]?.runs.map((run) => run.id) ?? [],
  );
  const detailById = { ...state.detailById };
  delete detailById[conversationId];
  const streamErrorById = { ...state.streamErrorById };
  delete streamErrorById[conversationId];
  return {
    ...state,
    summaries: state.summaries.filter((summary) => summary.id !== conversationId),
    activeConversationId: state.activeConversationId === conversationId
      ? null
      : state.activeConversationId,
    detailById,
    streamErrorById,
    artifactsById: filterRecord(
      state.artifactsById,
      (artifact) => artifact.session_id !== conversationId,
    ),
    liveFieldsById: filterRecord(
      state.liveFieldsById,
      (_value, key) => ![...runIds].some((runId) => key.startsWith(`${runId}:`)),
    ),
  };
}

export function upsertRun(
  state: ConversationStore,
  conversationId: string,
  run: ConversationRun,
): ConversationStore {
  const detail = state.detailById[conversationId];
  if (!detail) return state;
  return {
    ...state,
    detailById: {
      ...state.detailById,
      [conversationId]: {
        ...detail,
        runs: mergeProjectionById(detail.runs, [run]).sort(
          (left, right) => left.session_sequence - right.session_sequence,
        ),
      },
    },
  };
}

export function upsertItem(
  state: ConversationStore,
  conversationId: string,
  item: ConversationRunItem,
): ConversationStore {
  const detail = state.detailById[conversationId];
  if (!detail) return state;
  const current = detail.items.find((candidate) => candidate.id === item.id);
  if (current && current.revision > item.revision) return state;
  const next: ConversationStore = {
    ...state,
    detailById: {
      ...state.detailById,
      [conversationId]: {
        ...detail,
        items: sortItems(mergeProjectionById(detail.items, [item])),
      },
    },
  };
  return isTerminalItem(item) ? clearLiveFields(next, item.id) : next;
}

export function upsertArtifacts(
  state: ConversationStore,
  artifacts: ConversationArtifact[],
): ConversationStore {
  if (artifacts.length === 0) return state;
  const artifactsById = { ...state.artifactsById };
  for (const artifact of artifacts) artifactsById[artifact.id] = artifact;
  return { ...state, artifactsById };
}

export function reduceStreamEvent(
  state: ConversationStore,
  envelope: ConversationStreamEvent,
): ConversationStore {
  return envelope.kind === "delta"
    ? reduceLiveDelta(state, envelope.delta)
    : reduceCommittedEvent(state, envelope.event);
}

function reduceCommittedEvent(
  state: ConversationStore,
  event: Extract<ConversationStreamEvent, { kind: "event" }>["event"],
): ConversationStore {
  const detail = state.detailById[event.session_id];
  if (!detail || event.sequence <= (detail.cursor || 0)) return state;

  let next: ConversationStore = {
    ...state,
    detailById: {
      ...state.detailById,
      [event.session_id]: { ...detail, cursor: event.sequence },
    },
  };
  if (event.payload.run) {
    next = upsertRun(next, event.session_id, event.payload.run);
  }
  if (event.payload.item) {
    next = upsertItem(next, event.session_id, {
      ...event.payload.item,
      sequence: event.payload.item.sequence || event.sequence,
    });
  }
  return next;
}

function reduceLiveDelta(
  state: ConversationStore,
  delta: RunItemDeltaEnvelope,
): ConversationStore {
  const detail = state.detailById[delta.session_id];
  const run = detail?.runs.find((candidate) => candidate.id === delta.run_id);
  const item = detail?.items.find((candidate) => candidate.id === delta.item_id);
  if (
    !run
    || isTerminalRun(run.status)
    || !item
    || item.type !== delta.item_type
    || isTerminalItem(item)
  ) {
    return state;
  }

  const fieldKey = `${delta.run_id}:${delta.item_id}:${delta.field}`;
  const cursor = state.liveFieldsById[fieldKey];
  const current = deltaFieldValue(item, delta.field);
  let value: string;

  // The live hub seeds a reconnecting subscriber with one authoritative
  // full-field snapshot at offset zero. Ordinary deltas are append-only.
  if (delta.offset === 0) {
    if (cursor && delta.revision <= cursor.revision) return state;
    value = delta.content;
  } else {
    if (
      !cursor
      || delta.revision !== cursor.revision + 1
      || delta.offset !== cursor.offset
      || codePointLength(current) !== delta.offset
    ) {
      return state;
    }
    value = current + delta.content;
  }

  const patched = patchDeltaField(item, delta.field, value);
  if (!patched) return state;
  const next = upsertItem(
    {
      ...state,
      liveFieldsById: {
        ...state.liveFieldsById,
        [fieldKey]: {
          revision: delta.revision,
          offset: delta.offset + codePointLength(delta.content),
        },
      },
    },
    item.session_id,
    patched,
  );
  return next;
}

function deltaFieldValue(item: ConversationRunItem, field: RunItemDeltaEnvelope["field"]): string {
  if (field === "content" && item.type === "message") return item.payload.content;
  return "";
}

function patchDeltaField(
  item: ConversationRunItem,
  field: RunItemDeltaEnvelope["field"],
  value: string,
): ConversationRunItem | null {
  if (field === "content" && item.type === "message") {
    return { ...item, payload: { ...item.payload, content: value } };
  }
  return null;
}

function clearLiveFields(state: ConversationStore, itemId: string): ConversationStore {
  return {
    ...state,
    liveFieldsById: filterRecord(
      state.liveFieldsById,
      (_value, key) => !key.includes(`:${itemId}:`),
    ),
  };
}

function isTerminalItem(item: ConversationRunItem): boolean {
  return isTerminalRunItem(item.status);
}

function sortItems(items: ConversationRunItem[]): ConversationRunItem[] {
  return [...items].sort((left, right) => (
    left.sequence - right.sequence
    || left.created_at.localeCompare(right.created_at)
    || left.id.localeCompare(right.id)
  ));
}

function filterRecord<T>(
  record: Record<string, T>,
  keep: (value: T, key: string) => boolean,
): Record<string, T> {
  return Object.fromEntries(Object.entries(record).filter(([key, value]) => keep(value, key)));
}

function codePointLength(value: string): number {
  return [...value].length;
}
