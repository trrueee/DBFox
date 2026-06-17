import { useReducer, useCallback } from "react";
import type { AgentAnswer } from "../../lib/api/types";
import type { AgentTabStatus } from "../../mock/dbfoxMock";
import type { AgentTaskState, AgentTaskAction, AgentTaskStep } from "./types";
import { computeSummary } from "./types";

// ---------------------------------------------------------------------------
// Initial state
// ---------------------------------------------------------------------------

function createInitialState(queryText: string): AgentTaskState {
  return {
    steps: [],
    status: "idle",
    finalAnswer: null,
    summary: null,
    error: null,
    queryText,
    createdAt: Date.now(),
  };
}

// ---------------------------------------------------------------------------
// Reducer
// ---------------------------------------------------------------------------

function agentTaskReducer(state: AgentTaskState, action: AgentTaskAction): AgentTaskState {
  switch (action.type) {
    case "ADD_THINKING_STEP": {
      const step: AgentTaskStep = {
        id: action.payload.id,
        type: "thinking",
        status: action.payload.status,
        title: action.payload.title,
        content: action.payload.content,
        timestamp: action.payload.timestamp,
      };
      return { ...state, steps: [...state.steps, step] };
    }

    case "ADD_TOOL_CALL_STEP": {
      const step: AgentTaskStep = {
        id: action.payload.id,
        type: "tool_call",
        status: "running",
        title: action.payload.title,
        subtitle: action.payload.subtitle,
        toolName: action.payload.toolName,
        input: action.payload.input ?? null,
        output: null,
        error: null,
        content: "",
        timestamp: action.payload.timestamp,
      };
      // Replace existing tool step with same ID if present (upsert)
      const idx = state.steps.findIndex((s) => s.id === step.id);
      if (idx >= 0) {
        const next = [...state.steps];
        next[idx] = { ...next[idx], ...step };
        return { ...state, steps: next };
      }
      return { ...state, steps: [...state.steps, step] };
    }

    case "UPDATE_STEP": {
      const { id, patch } = action.payload;
      const idx = state.steps.findIndex((s) => s.id === id);
      if (idx === -1) return state;
      const next = [...state.steps];
      next[idx] = { ...next[idx], ...patch, timestamp: Date.now() };
      return { ...state, steps: next };
    }

    case "COMPLETE_TASK": {
      const summary = computeSummary(state.steps);
      return {
        ...state,
        status: "completed",
        finalAnswer: action.payload.finalAnswer,
        error: action.payload.error,
        summary,
      };
    }

    case "FAIL_TASK": {
      const summary = computeSummary(state.steps);
      return {
        ...state,
        status: "failed",
        error: action.payload.error,
        summary,
      };
    }

    case "SET_STATUS": {
      const summary =
        action.payload.status === "completed" || action.payload.status === "failed"
          ? state.summary ?? computeSummary(state.steps)
          : state.summary;
      return { ...state, status: action.payload.status, summary };
    }

    case "CLEAR":
      return createInitialState(state.queryText);

    default:
      return state;
  }
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useAgentTask(queryText: string) {
  const [state, dispatch] = useReducer(agentTaskReducer, queryText, createInitialState);

  const addThinkingStep = useCallback(
    (id: string, title: string, content: string, status: "running" | "info" = "info") => {
      dispatch({
        type: "ADD_THINKING_STEP",
        payload: { id, title, content, status, timestamp: Date.now() },
      });
    },
    [],
  );

  const addToolCallStep = useCallback(
    (id: string, toolName: string, title: string, subtitle?: string, input?: Record<string, unknown> | null) => {
      dispatch({
        type: "ADD_TOOL_CALL_STEP",
        payload: { id, toolName, title, subtitle, input, timestamp: Date.now() },
      });
    },
    [],
  );

  const updateStep = useCallback(
    (id: string, patch: Partial<Pick<AgentTaskStep, "status" | "content" | "output" | "error" | "latencyMs" | "toolName" | "title" | "subtitle">>) => {
      dispatch({ type: "UPDATE_STEP", payload: { id, patch } });
    },
    [],
  );

  const completeTask = useCallback(
    (finalAnswer: AgentAnswer | null, error: string | null = null) => {
      dispatch({ type: "COMPLETE_TASK", payload: { finalAnswer, error } });
    },
    [],
  );

  const failTask = useCallback(
    (error: string) => {
      dispatch({ type: "FAIL_TASK", payload: { error } });
    },
    [],
  );

  const setStatus = useCallback(
    (status: AgentTabStatus | "idle") => {
      dispatch({ type: "SET_STATUS", payload: { status } });
    },
    [],
  );

  const clearTask = useCallback(() => {
    dispatch({ type: "CLEAR" });
  }, []);

  const isRunning = state.status === "running" || state.status === "waiting_approval";
  const isDone = state.status === "completed" || state.status === "failed";
  const hasAnswer = !!state.finalAnswer?.answer;

  return {
    state,
    isRunning,
    isDone,
    hasAnswer,
    addThinkingStep,
    addToolCallStep,
    updateStep,
    completeTask,
    failTask,
    setStatus,
    clearTask,
  };
}
