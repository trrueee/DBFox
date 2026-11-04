import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createStagedExtensionHost, initExtensionHostGlobalSdk } from "../extensionHost";
import type { DlcModule } from "../types";

const fixturePath = resolve(process.cwd(), "../dlcs/dbfox.story/frontend/index.js");

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("dbfox.story System DLC frontend fixture", () => {
  it("keeps chapter tree selection and reader content in one controlled state", async () => {
    initExtensionHostGlobalSdk();
    const jsdomDocument = document;
    vi.stubGlobal("document", undefined);
    const source = await readFile(fixturePath, "utf8");
    const moduleUrl = `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`;
    const module = await import(/* @vite-ignore */ moduleUrl) as DlcModule;
    const chapters = [
      {
        id: "chapter-1",
        seq: 1,
        title: "第一章",
        content: "第一章正文",
        content_path: "chapters/p1/chapter-1.md",
        content_sha256: "a".repeat(64),
        updated_at: "2026-08-31T00:00:00Z",
      },
      {
        id: "chapter-2",
        seq: 2,
        title: "第二章",
        content: "第二章正文",
        content_path: "chapters/p1/chapter-2.md",
        content_sha256: "b".repeat(64),
        updated_at: "2026-08-31T00:01:00Z",
      },
    ];
    const invokeOperation = async <TOutput,>(
      _dlcId: string,
      operationName: string,
      input: unknown,
    ): Promise<TOutput> => {
      if (operationName === "worlds.get") {
        return { id: "world-1", title: "测试世界", generation: 1 } as TOutput;
      }
      if (operationName === "entities.list") return { entities: [] } as TOutput;
      if (operationName === "relations.list") return { edges: [] } as TOutput;
      if (operationName === "revisions.list") return { revisions: [] } as TOutput;
      if (operationName === "chapters.list") return { chapters } as TOutput;
      if (operationName === "chapters.read") {
        const chapterId = (input as { chapter_id: string }).chapter_id;
        return chapters.find((chapter) => chapter.id === chapterId) as TOutput;
      }
      if (operationName === "chapter_versions.list") {
        const chapterId = (input as { chapter_id: string }).chapter_id;
        return {
          versions: [{
            id: `version-${chapterId}`,
            chapter_id: chapterId,
            seq: 1,
            title: chapterId === "chapter-1" ? "第一章" : "第二章",
            content_sha256: chapterId === "chapter-1" ? "a".repeat(64) : "b".repeat(64),
            author: "author",
            created_at: "2026-08-31T00:00:00Z",
          }],
        } as TOutput;
      }
      throw new Error(`Unexpected operation ${operationName}`);
    };
    const staged = createStagedExtensionHost("dbfox.story", {
      invokeOperation,
      openDockTab: vi.fn(),
      pickFolder: vi.fn(),
      pickFile: vi.fn(),
      readPickedFile: vi.fn(),
    });
    await module.register?.(staged.host);
    vi.stubGlobal("document", jsdomDocument);
    const workbench = staged.getContributions().dockViews[0];

    render(workbench.render(
      {
        viewKey: "story:p1",
        viewType: "dbfox.story.workbench",
        title: "故事",
        projectId: "p1",
        closeable: true,
      },
      {
        activeProjectId: "p1",
        activeConversationId: null,
        showToast: vi.fn(),
        workbenchScopeId: "scope-1",
        onAsk: vi.fn(),
      },
    ));

    await waitFor(() => expect(
      (screen.getByRole("button", { name: "章节" }) as HTMLButtonElement).disabled,
    ).toBe(false));
    fireEvent.click(screen.getByRole("button", { name: "章节" }));
    await screen.findByText("第一章正文");

    fireEvent.click(screen.getByText("2. 第二章"));
    await screen.findByText("第二章正文");
    expect(screen.queryByText("第一章正文")).toBeNull();
    expect(await screen.findByText("版本历史")).not.toBeNull();
  });
});
