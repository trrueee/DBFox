import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const root = process.cwd();
const indexHtml = readFileSync(join(root, "index.html"), "utf8");
const globalCss = readFileSync(join(root, "src", "index.css"), "utf8");
const tauriConfig = JSON.parse(
  readFileSync(join(root, "src-tauri", "tauri.conf.json"), "utf8"),
) as { app: { security: { csp: string } } };

describe("desktop CSP network boundary", () => {
  it("does not load fonts or API traffic from arbitrary internet origins", () => {
    const csp = tauriConfig.app.security.csp;

    expect(indexHtml).not.toMatch(/fonts\.(?:googleapis|gstatic|loli)\.net|fonts\.googleapis\.com/i);
    expect(globalCss).not.toMatch(/@import\s+url\([^)]*fonts\.googleapis\.com/i);
    expect(csp).toContain("connect-src 'self' http://127.0.0.1:*");
    expect(csp).not.toContain("connect-src 'self' http://127.0.0.1:* https:");
    expect(csp).toContain("font-src 'self'");
    expect(csp).not.toMatch(/font-src[^;]*(?:googleapis|gstatic|loli)/i);
  });
});
