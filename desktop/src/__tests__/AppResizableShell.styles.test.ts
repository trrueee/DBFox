import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const appSource = join(process.cwd(), "src/App.tsx");
const appCss = join(process.cwd(), "src/App.css");
const treeSource = join(process.cwd(), "src/features/datasource/DataSourceTree.tsx");
const treeCss = join(process.cwd(), "src/features/datasource/DataSourceTree.css");

describe("App resizable shell", () => {
  it("uses the DBFox resizable primitive instead of the hand-rolled sidebar dragger", () => {
    const source = readFileSync(appSource, "utf8");
    const css = readFileSync(appCss, "utf8");
    const tree = readFileSync(treeSource, "utf8");
    const treeStyles = readFileSync(treeCss, "utf8");

    expect(source).toContain("ResizablePanelGroup");
    expect(source).toContain("ResizablePanel");
    expect(source).toContain("ResizableHandle");
    expect(source).toContain('from "./components/ui"');
    expect(source).not.toContain("useSidebarLayout");
    expect(source).not.toContain("handleResizeStart");
    expect(source).not.toContain("sidebarWidth");
    expect(source).not.toContain("app-resizer");
    expect(css).toContain(".app-body-split");
    expect(css).not.toContain(".app-resizer");
    expect(tree).not.toContain("sidebarWidth");
    expect(tree).not.toContain("CSSProperties");
    expect(treeStyles).toContain("width: 100%");
    expect(treeStyles).not.toContain("--sidebar-width");
  });
});
