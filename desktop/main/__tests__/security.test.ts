import { describe, expect, it } from "vitest";

import { developmentRendererUrl } from "../security";

describe("Electron host security", () => {
  it("accepts only an explicit loopback HTTP development renderer", () => {
    expect(developmentRendererUrl("http://127.0.0.1:5173").origin).toBe(
      "http://127.0.0.1:5173",
    );
    for (const candidate of [
      "https://127.0.0.1:5173",
      "http://localhost:5173",
      "http://example.com:5173",
      "http://user:secret@127.0.0.1:5173",
      "file:///tmp/index.html",
    ]) {
      expect(() => developmentRendererUrl(candidate)).toThrow("explicit 127.0.0.1");
    }
  });
});
