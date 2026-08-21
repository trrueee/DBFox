import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const srcRoot = resolve(here, "..");

function read(relativePath: string) {
  return readFileSync(resolve(srcRoot, relativePath), "utf8");
}

describe("app shell layout", () => {
  it("does not use fixed canvas scaling", () => {
    const app = read("App.tsx");
    const css = read("App.css");

    expect(app).not.toMatch(/\bscale\b|setScale|CSSProperties|1598|1066/);
    expect(css).not.toContain("transform: scale(var(--scale))");
    expect(css).not.toMatch(/width:\s*1598px|height:\s*1066px/);
  });

  it("resizes the sidebar through the DBFox resizable primitive", () => {
    const app = read("App.tsx");
    const layout = read("features/appShell/ResizableWorkspaceLayout.tsx");
    const resizable = read("components/ui/resizable.tsx");

    expect(layout).toContain("ResizablePanelGroup");
    expect(layout).toContain("ResizableHandle");
    expect(app).not.toContain("handleResizeStart");
    expect(resizable).toContain('from "react-resizable-panels"');
  });

  it("uses a real viewport shell with grid rows and a quiet primary workspace", () => {
    const css = read("App.css");

    expect(css).toMatch(/\.app-shell\s*{[^}]*position:\s*fixed;[^}]*inset:\s*0;[^}]*width:\s*100vw;[^}]*height:\s*100vh;/s);
    expect(css).toMatch(/\.app-shell-inner\s*{[^}]*display:\s*grid;[^}]*grid-template-rows:\s*auto minmax\(0,\s*1fr\);[^}]*background:\s*var\(--surface-canvas\);/s);
    expect(css).toMatch(/\.app-body\s*{[^}]*grid-row:\s*2;/s);

    // Quiet Workbench: the primary workspace is a contiguous surface, not a raised card.
    const appMain = css.match(/\.app-main\s*{([^}]*)}/)?.[1] ?? "";
    expect(appMain).toContain("background: var(--surface-workspace)");
    expect(appMain).not.toMatch(/\bmargin\s*:|\bborder\s*:|\bborder-radius\s*:|\bbox-shadow\s*:/);

    // Conversation and Dock sit flush: no canvas gaps between first-class regions.
    expect(css).toMatch(/\.app-v3-stage\s*{[^}]*gap:\s*0;[^}]*padding:\s*0;/s);
  });

  it("keeps decorative gradients out of the structural shell", () => {
    const css = read("App.css");

    expect(css).not.toMatch(/\.app-shell-inner\s*{[^}]*radial-gradient/s);
  });

  it("keeps lazy workspace boundaries visibly loading instead of flashing blank", () => {
    const app = read("App.tsx");

    expect(app).toContain("<TitleBarFallback />");
    expect(app).toContain("<AppLayoutFallback />");
    expect(app).toContain('<LoadingState label="正在载入工作区" />');
  });

  it("keeps window controls inside the Electron titlebar", () => {
    const titlebar = read("components/TitleBar.tsx");
    const css = read("components/TitleBar.css");

    expect(titlebar).toContain('className="titlebar"');
    expect(css).toMatch(/\.titlebar\s*{[^}]*grid-row:\s*1;/s);
    expect(css).toMatch(/\.titlebar-controls\s*{[^}]*-webkit-app-region:\s*no-drag;/s);
  });
});
