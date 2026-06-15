import { render, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DataSourcesPage } from "../DataSourcesPage";
import { api } from "../../lib/api";

vi.mock("../../lib/api", () => ({
  api: {
    listDatasources: vi.fn(),
    testConnection: vi.fn(),
    createDatasource: vi.fn(),
    updateDatasource: vi.fn(),
    checkDatasourceHealth: vi.fn(),
    deleteDatasource: vi.fn(),
    syncSchema: vi.fn(),
  },
}));

vi.mock("../../components/DangerConfirmDialog", () => ({
  DangerConfirmDialog: () => null,
}));

vi.mock("../../components/ConfirmDialog", () => ({
  ConfirmDialog: () => null,
}));

function renderPage(initialShowAddForm: boolean) {
  return (
    <DataSourcesPage
      onSelectDataSource={vi.fn()}
      activeDataSource={null}
      activeProject={null}
      onRefreshDatasources={vi.fn().mockResolvedValue(undefined)}
      initialShowAddForm={initialShowAddForm}
    />
  );
}

describe("DataSourcesPage", () => {
  beforeEach(() => {
    vi.mocked(api.listDatasources).mockResolvedValue([]);
  });

  it("syncs add form visibility when a reused settings tab switches mode", async () => {
    const { container, rerender } = render(renderPage(false));

    await waitFor(() => expect(api.listDatasources).toHaveBeenCalled());
    expect(container.querySelector("form.hifi-datasource-form")).not.toBeInTheDocument();

    rerender(renderPage(true));
    expect(container.querySelector("form.hifi-datasource-form")).toBeInTheDocument();

    rerender(renderPage(false));
    expect(container.querySelector("form.hifi-datasource-form")).not.toBeInTheDocument();
  });
});
