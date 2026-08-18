import { describe, expect, it } from "vitest";
import type { ResourceConnectorContribution } from "../types";

// Mock contribution for conformance testing
function createMockContribution(): ResourceConnectorContribution {
  return {
    id: "test.mock",
    title: "Mock",
    icon: "🧪",
    render: () => "mock-content",
    addLabel: "Add Mock",
    onAdd: () => {},
  };
}

describe("ResourceConnectorContribution — conformance", () => {
  it("mock contribution can be created without modifying Shell source", () => {
    const mock = createMockContribution();
    expect(mock.id).toBe("test.mock");
    expect(mock.title).toBe("Mock");
    expect(mock.addLabel).toBe("Add Mock");
    expect(typeof mock.render).toBe("function");
    expect(typeof mock.onAdd).toBe("function");
  });

  it("mock contribution render returns content", () => {
    const mock = createMockContribution();
    const result = mock.render({ projectId: "project-1" });
    expect(result).toBe("mock-content");
  });

  it("addable contributions are filterable", () => {
    const contributions: ResourceConnectorContribution[] = [
      createMockContribution(),
      {
        id: "test.no-add",
        title: "No Add",
        icon: "📄",
        render: () => "no-add-content",
        // no addLabel or onAdd
      },
    ];

    const addable = contributions.filter((c) => c.onAdd && c.addLabel);
    expect(addable).toHaveLength(1);
    expect(addable[0].id).toBe("test.mock");
  });

  it("contribution without onAdd is renderable but not addable", () => {
    const contribution: ResourceConnectorContribution = {
      id: "test.render-only",
      title: "Render Only",
      icon: "📄",
      render: () => "render-only-content",
    };

    expect(contribution.render({ projectId: "p1" })).toBe("render-only-content");
    expect(contribution.onAdd).toBeUndefined();
    expect(contribution.addLabel).toBeUndefined();
  });
});
