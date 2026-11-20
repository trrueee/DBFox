import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TooltipProvider } from "../../../components/ui";
import { useConversationStore } from "../../../stores/conversationStore";
import { openArtifactDock } from "../../../stores/artifactDockStore";
import { selectActiveDockOpen, selectActiveDockTabs, selectActiveWorkbenchReferences, useWorkspaceStore } from "../../../stores/workspaceStore";
import type { ConversationArtifact, ConversationEvidence } from "../../../types/conversation";
import { ArtifactDockContent } from "../dockViewContent";

vi.mock("../../workspace/artifacts/ArtifactViewHost", () => ({
  ArtifactViewHost: () => <div>来源正文</div>,
}));

const artifact: ConversationArtifact = {
  id: "artifact-source", session_id: "session-1", run_id: "run-1", version: 1,
  type: "markdown", visibility: "primary", title: "验证记录.md", status: "completed",
  payload: { content: "原始记录" }, provenance: {}, relations: [],
};
const evidence: ConversationEvidence = {
  id: "evidence-2", claim_id: "claim-2", artifact_id: artifact.id,
  label: "第二处结论的依据。", observed_at: "2026-11-20T00:00:00Z",
  locator: { kind: "artifact", value: { citation_index: 2 } },
};

describe("Artifact evidence navigation", () => {
  beforeEach(() => {
    useWorkspaceStore.setState({ activeProjectId: "project-1", mainSurfaceByProject: {
      "project-1": { kind: "conversation", conversationId: "session-1" },
    }, workbenchByConversation: {} });
    useConversationStore.setState({ artifactsById: { [artifact.id]: artifact }, detailById: {
      "session-1": { id: "session-1", title: "验收", project_id: "project-1", protocol_version: 2,
        cursor: 3, resource_intents: [], runs: [], selected_artifact_id: null,
        items: [{ id: "answer-1", type: "message", session_id: "session-1", run_id: "run-1",
          sequence: 3, revision: 1, status: "completed", created_at: evidence.observed_at,
          payload: { role: "assistant", content: "结论", evidence: [evidence], artifact_refs: [], limitation_codes: [] } }],
      },
    } });
  });
  afterEach(cleanup);

  function renderEvidence() {
    openArtifactDock(artifact, { sessionId: "session-1", evidenceId: evidence.id, preview: true });
    const tab = selectActiveDockTabs(useWorkspaceStore.getState())[0];
    const onAsk = vi.fn(reference => useWorkspaceStore.getState().addWorkbenchReference(reference));
    const onToast = vi.fn();
    render(<TooltipProvider><a href="#evidence-2" data-evidence-id="evidence-2">原回答引用</a>
      <ArtifactDockContent tab={tab} showToast={onToast} onAsk={onAsk} />
    </TooltipProvider>);
    return { onAsk, onToast };
  }

  it("reads the exact canonical evidence without selecting next-turn context", () => {
    const { onAsk } = renderEvidence();
    expect(screen.getByText("第二处结论的依据。")).toBeTruthy();
    expect(screen.getByText(/未记录更细的位置/)).toBeTruthy();
    expect(selectActiveWorkbenchReferences(useWorkspaceStore.getState())).toEqual([]);
    expect(useConversationStore.getState().detailById["session-1"].selected_artifact_id).toBeNull();
    expect(onAsk).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "引用到输入框" }));
    expect(onAsk).toHaveBeenCalledWith({ artifactId: artifact.id, label: artifact.title });
    expect(selectActiveWorkbenchReferences(useWorkspaceStore.getState())).toEqual([{ artifactId: artifact.id, label: artifact.title }]);
  });

  it("returns keyboard focus to the cited answer without losing its identity", async () => {
    renderEvidence();
    fireEvent.click(screen.getByRole("button", { name: "返回原文" }));
    expect(selectActiveDockOpen(useWorkspaceStore.getState())).toBe(false);
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("link", { name: "原回答引用" })));
  });
});
