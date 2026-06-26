import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const workspaceSourcePath = join(process.cwd(), "src/features/conversation/workspace/ConversationWorkspace.tsx");
const dockSourcePath = join(process.cwd(), "src/features/conversation/workspace/ArtifactDock.tsx");
const cssPath = join(process.cwd(), "src/features/conversation/workspace/conversationWorkspace.css");

describe("conversation workspace split pane foundation", () => {
  it("delegates artifact split resizing to react-resizable-panels", () => {
    const workspaceSource = readFileSync(workspaceSourcePath, "utf8");
    const dockSource = readFileSync(dockSourcePath, "utf8");

    expect(workspaceSource).toContain('from "react-resizable-panels"');
    expect(workspaceSource).toContain("<PanelGroup");
    expect(workspaceSource).toContain("<PanelResizeHandle");
    expect(workspaceSource).toContain('className="conv-artifact-panel-group"');
    expect(workspaceSource).toContain('className="conv-artifact-main-panel"');
    expect(workspaceSource).toContain('className="conv-artifact-dock-panel"');

    expect(dockSource).not.toContain("PointerEvent");
    expect(dockSource).not.toContain("onPointerDown");
    expect(dockSource).not.toContain("window.addEventListener");
    expect(dockSource).not.toContain("dockWidth");
    expect(dockSource).not.toContain("--conv-artifact-width");
  });

  it("keeps split pane presentation in local CSS without inline width variables", () => {
    expect(existsSync(cssPath)).toBe(true);
    const css = readFileSync(cssPath, "utf8");

    expect(css).toContain(".conv-artifact-panel-group");
    expect(css).toContain(".conv-artifact-main-panel");
    expect(css).toContain(".conv-artifact-dock-panel");
    expect(css).toContain(".conv-artifact-resizer");
    expect(css).not.toContain("width: var(--conv-artifact-width");
  });
});
