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

  it("resizes the sidebar using real viewport mouse delta", () => {
    const app = read("App.tsx");

    expect(app).toContain("const delta = e.clientX - resizingRef.current.startX;");
  });

  it("uses a real viewport shell with grid rows and a raised main surface", () => {
    const css = read("App.css");

    expect(css).toMatch(/\.app-shell\s*{[^}]*position:\s*fixed;[^}]*inset:\s*0;[^}]*width:\s*100vw;[^}]*height:\s*100vh;/s);
    expect(css).toMatch(/\.app-shell-inner\s*{[^}]*display:\s*grid;[^}]*grid-template-rows:\s*auto minmax\(0,\s*1fr\) auto;/s);
    expect(css).toMatch(/\.app-body\s*{[^}]*grid-row:\s*2;/s);
    expect(css).toMatch(/\.app-statusbar\s*{[^}]*grid-row:\s*3;/s);
    expect(css).toMatch(/\.app-main\s*{[^}]*margin:\s*8px 8px 6px 0;[^}]*border-radius:\s*16px;[^}]*box-shadow:[^}]*overflow:\s*hidden;/s);
  });

  it("keeps the Tauri drag region on the titlebar and out of controls", () => {
    const titlebar = read("components/TitleBar.tsx");
    const css = read("components/TitleBar.css");

    expect(titlebar).toContain('className="titlebar" data-tauri-drag-region');
    expect(titlebar).not.toMatch(/<button[^>]*data-tauri-drag-region/s);
    expect(css).toMatch(/\.titlebar\s*{[^}]*grid-row:\s*1;/s);
    expect(css).toMatch(/\.titlebar-controls\s*{[^}]*-webkit-app-region:\s*no-drag;/s);
  });
});
