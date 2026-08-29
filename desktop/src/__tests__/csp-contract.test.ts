import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";
import { CONTENT_SECURITY_POLICY } from "../../main/appProtocol";

const root = process.cwd();
const indexHtml = readFileSync(join(root, "index.html"), "utf8");
const globalCss = readFileSync(join(root, "src", "index.css"), "utf8");

describe("desktop CSP network boundary", () => {
  it("does not load fonts or API traffic from arbitrary internet origins", () => {
    const csp = CONTENT_SECURITY_POLICY;

    expect(indexHtml).not.toMatch(/fonts\.(?:googleapis|gstatic|loli)\.net|fonts\.googleapis\.com/i);
    expect(globalCss).not.toMatch(/@import\s+url\([^)]*fonts\.googleapis\.com/i);
    expect(csp).toContain("connect-src 'self' http://127.0.0.1:* dlc-asset:");
    expect(csp).not.toContain("connect-src 'self' http://127.0.0.1:* https:");
    expect(csp).toContain("font-src 'self'");
    expect(csp).not.toMatch(/font-src[^;]*(?:googleapis|gstatic|loli)/i);
  });

  it("permits explicit HTTPS image previews without opening general HTTPS fetches", () => {
    const csp = CONTENT_SECURITY_POLICY;

    expect(csp).toContain("img-src 'self' data: https:");
    expect(csp).not.toMatch(/connect-src[^;]*https:/i);
  });

  it("allows audited renderer attributes without permitting inline style elements", () => {
    const directives = CONTENT_SECURITY_POLICY.split(";").map((item) => item.trim());

    expect(directives).toContain("style-src 'self' dlc-asset:");
    expect(directives).toContain("style-src-elem 'self' dlc-asset:");
    expect(directives).toContain("style-src-attr 'unsafe-inline'");
    expect(directives.find((item) => item.startsWith("style-src-elem "))).not.toContain(
      "'unsafe-inline'",
    );
  });
});
