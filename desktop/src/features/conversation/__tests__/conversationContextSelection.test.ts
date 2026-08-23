import { beforeEach, describe, expect, it, vi } from "vitest";
import { useConversationContextStore } from "../../../stores/conversationContextStore";
import { useConversationStore } from "../../../stores/conversationStore";
import { useWorkspaceStore } from "../../../stores/workspaceStore";
import {
  addCurrentConversationContextResource,
  getCurrentConversationContextSelection,
} from "../conversationContextSelection";

describe("Conversation context selection authority boundary", () => {
  const setResourceIntents = vi.fn().mockResolvedValue(undefined);

  beforeEach(() => {
    setResourceIntents.mockClear();
    useConversationContextStore.setState({ byProject: {} });
    useWorkspaceStore.setState({
      activeProjectId: "project-1",
      mainSurfaceByProject: { "project-1": { kind: "new-conversation" } },
    });
    useConversationStore.setState((state) => ({
      ...state,
      activeConversationId: "conversation-1",
      detailById: {
        "conversation-1": {
          protocol_version: 2,
          id: "conversation-1",
          title: "Billing",
          project_id: "project-1",
          resource_intents: [{ kind: "dbfox.data.database", id: "db-1" }],
          runs: [],
          items: [],
        },
      },
      setResourceIntents,
    }));
  });

  it("writes a new-conversation selection to the Project draft even with a stale active Conversation", async () => {
    await addCurrentConversationContextResource({ kind: "dbfox.data.database", id: "db-2" });

    expect(setResourceIntents).not.toHaveBeenCalled();
    expect(useConversationContextStore.getState().byProject["project-1"])
      .toEqual([{ kind: "dbfox.data.database", id: "db-2" }]);
  });

  it("patches durable intent only when the Conversation is the visible Main Surface", async () => {
    useWorkspaceStore.setState({
      mainSurfaceByProject: { "project-1": { kind: "conversation", conversationId: "conversation-1" } },
    });

    expect(getCurrentConversationContextSelection())
      .toEqual([{ kind: "dbfox.data.database", id: "db-1" }]);
    await addCurrentConversationContextResource({ kind: "dbfox.data.database", id: "db-2" });

    expect(setResourceIntents).toHaveBeenCalledWith("conversation-1", [
      { kind: "dbfox.data.database", id: "db-1" },
      { kind: "dbfox.data.database", id: "db-2" },
    ]);
  });
});
