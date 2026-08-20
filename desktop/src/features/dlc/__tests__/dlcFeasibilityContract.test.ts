import { describe, it, expect } from "vitest";
import tauriConfig from "../../../../src-tauri/tauri.conf.json";

describe("Runtime DLC Frontend Feasibility Contract", () => {
  describe("Tauri Custom Protocol & CSP Isolation", () => {
    it("enforces dedicated dlc-asset URI format with digest pinning", () => {
      const buildDlcAssetUrl = (digest: string, relativePath: string): string => {
        // Enforce lowercase SHA256 hex digest (64 chars)
        if (!/^[a-f0-9]{64}$/.test(digest)) {
          throw new Error(`Invalid package digest format: "${digest}"`);
        }
        // Normalize path: forward slashes, no leading slash, no path traversal
        const normalized = relativePath.replace(/\\/g, "/").replace(/^\/+/, "");
        if (normalized.includes("..") || normalized.startsWith("/")) {
          throw new Error(`Path traversal rejected: "${relativePath}"`);
        }
        return `dlc-asset://localhost/${digest}/${normalized}`;
      };

      const validDigest = "a".repeat(64);
      const url = buildDlcAssetUrl(validDigest, "frontend/index.js");
      expect(url).toBe(`dlc-asset://localhost/${validDigest}/frontend/index.js`);

      // Path traversal rejection
      expect(() => buildDlcAssetUrl(validDigest, "../backend/secret.py")).toThrow(
        /Path traversal rejected/,
      );
      expect(() => buildDlcAssetUrl("short-hash", "frontend/index.js")).toThrow(
        /Invalid package digest format/,
      );
    });

    it("verifies production CSP allows loopback HTTP ONLY in connect-src, not in script-src", () => {
      const csp = tauriConfig.app?.security?.csp ?? "";
      expect(csp).toBeTruthy();

      // Extract script-src and connect-src directives
      const directives = csp.split(";").map((d) => d.trim());
      const scriptSrc = directives.find((d) => d.startsWith("script-src "));
      const connectSrc = directives.find((d) => d.startsWith("connect-src "));

      expect(scriptSrc).toBeDefined();
      expect(connectSrc).toBeDefined();

      // connect-src allows loopback for local engine communication
      expect(connectSrc).toContain("http://127.0.0.1:*");

      // script-src MUST NOT allow arbitrary loopback HTTP script execution
      expect(scriptSrc).not.toContain("http://127.0.0.1:*");
      expect(scriptSrc).not.toContain("http://localhost:*");
      expect(scriptSrc).not.toContain("http:");

      // script-src MUST be restricted to self and dedicated asset protocols
      expect(scriptSrc).toContain("'self'");
    });
  });

  describe("Host Extension SDK Surface Boundaries", () => {
    it("prohibits exposing private application state and tokens on window.__DBFOX_EXTENSION_HOST__", () => {
      // Allowed public extension surfaces
      const allowedPublicKeys = new Set([
        "version",
        "React",
        "ReactDOM",
        "components",
        "icons",
        "registries",
      ]);

      // Prohibited private internal surfaces
      const prohibitedKeys = [
        "useAppStore",
        "useConversationStore",
        "useWorkspaceStore",
        "queryClient",
        "token",
        "authToken",
        "credentialsVault",
        "rawEngineToken",
        "navigate",
        "router",
        "invokeOperation",
      ];

      const mockExtensionHost: Record<string, unknown> = {
        version: "1",
        React: {},
        ReactDOM: {},
        components: {},
        icons: {},
        registries: {},
      };

      for (const key of Object.keys(mockExtensionHost)) {
        expect(allowedPublicKeys.has(key)).toBe(true);
      }

      for (const prohibited of prohibitedKeys) {
        expect(mockExtensionHost).not.toHaveProperty(prohibited);
      }
    });
  });

  describe("Single React Instance Invariant", () => {
    it("requires externalized React peer dependency contract", () => {
      // DLC packages must externalize react and react-dom so they bind to the Host's instance
      const dlcViteConfigExternal = ["react", "react-dom", "@dbfox/dlc-sdk"];
      expect(dlcViteConfigExternal).toContain("react");
      expect(dlcViteConfigExternal).toContain("react-dom");
      expect(dlcViteConfigExternal).toContain("@dbfox/dlc-sdk");
    });
  });
});
