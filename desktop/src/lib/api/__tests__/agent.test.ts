import { describe, expect, it } from "vitest";
import { agentApi } from "../agent";

describe("agentApi", () => {
  it("does not expose reusable SQL memory as a public client API", () => {
    expect("listReusableSqls" in agentApi).toBe(false);
  });
});
