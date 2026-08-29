import { describe, expect, it, vi } from "vitest";
import type { ResourceConnectorContribution } from "../types";
import { productResourceConnectors } from "../resourceConnectorComposition";

function connector(id: string): ResourceConnectorContribution {
  return {
    id,
    title: id,
    icon: null,
    render: () => null,
  };
}

describe("productResourceConnectors", () => {
  it("passes the signed DLC connectors through as the resource composition", () => {
    const contributions = [connector("dbfox.data"), connector("acme.notes")];

    const result = productResourceConnectors(vi.fn(), contributions);

    expect(result).toBe(contributions);
    expect(result.filter((item) => item.id === "dbfox.data")).toHaveLength(1);
  });

  it("does not invent a source fallback when the signed Data DLC is unavailable", () => {
    const result = productResourceConnectors(vi.fn(), [connector("acme.notes")]);

    expect(result.map((item) => item.id)).toEqual(["acme.notes"]);
  });
});
