import { describe, expect, it, vi } from "vitest";
import type { ResourceConnectorContribution } from "../types";
import {
  DATA_CONNECTOR_ID,
  productResourceConnectors,
} from "../resourceConnectorComposition";

function connector(id: string): ResourceConnectorContribution {
  return {
    id,
    title: id,
    icon: null,
    render: () => null,
  };
}

describe("productResourceConnectors", () => {
  it("uses the signed Data DLC connector as the single Data resource tree", () => {
    const contributions = [connector("acme.notes"), connector(DATA_CONNECTOR_ID)];

    const result = productResourceConnectors(vi.fn(), contributions);

    expect(result).toBe(contributions);
    expect(result.filter((item) => item.id === DATA_CONNECTOR_ID)).toHaveLength(1);
  });

  it("keeps the source-development Data connector when the DLC is unavailable", () => {
    const result = productResourceConnectors(vi.fn(), [connector("acme.notes")]);

    expect(result.map((item) => item.id)).toEqual([DATA_CONNECTOR_ID, "acme.notes"]);
  });
});
