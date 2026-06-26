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

  it("uses percentage split sizes so the artifact dock is not capped to pixels", () => {
    const workspaceSource = readFileSync(workspaceSourcePath, "utf8");

    expect(workspaceSource).toContain('defaultSize="72%"');
    expect(workspaceSource).toContain('minSize="48%"');
    expect(workspaceSource).toContain('defaultSize="28%"');
    expect(workspaceSource).toContain('minSize="22%"');
    expect(workspaceSource).toContain('maxSize="44%"');
    expect(workspaceSource).not.toContain("defaultSize={72}");
    expect(workspaceSource).not.toContain("defaultSize={28}");
    expect(workspaceSource).not.toContain("maxSize={44}");
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

  it("keeps safety SQL dock previews on the shared GitHub Light code surface tokens", () => {
    const css = readFileSync(cssPath, "utf8");
    const safetySqlRule = css.match(/\.conv-dock-safety-sql\s*\{[^}]+\}/)?.[0] ?? "";

    expect(safetySqlRule).toContain("background: var(--sql-code-surface)");
    expect(safetySqlRule).toContain("border: 1px solid var(--sql-code-border)");
  });
});
