import { describe, expect, it } from "vitest";
import { installCspStyleNoncePropagation } from "../cspStyleNonce";

describe("CSP style nonce propagation", () => {
  it("copies the Tauri style-anchor nonce to framework-created style elements before insertion", () => {
    const sandbox = document.implementation.createHTMLDocument("nonce-test");
    const style = sandbox.createElement("style");
    style.setAttribute("data-tauri-csp-style-nonce", "");
    style.nonce = "tauri-style-nonce";
    sandbox.head.append(style);
    const script = sandbox.createElement("script");
    script.nonce = "different-script-nonce";
    sandbox.head.append(script);

    const restore = installCspStyleNoncePropagation(sandbox);
    const dynamicStyle = sandbox.createElement("style") as HTMLStyleElement;

    expect(dynamicStyle.nonce).toBe("tauri-style-nonce");
    restore();
  });

  it("does not patch documents without a Tauri-provided nonce", () => {
    const sandbox = document.implementation.createHTMLDocument("without-nonce");
    const original = sandbox.createElement;

    const restore = installCspStyleNoncePropagation(sandbox);

    expect(sandbox.createElement).toBe(original);
    restore();
  });
});
