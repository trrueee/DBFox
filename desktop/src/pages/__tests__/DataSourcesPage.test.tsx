import { render, fireEvent, waitFor, within } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DataSourcesPage } from "../DataSourcesPage";
import { api } from "../../lib/api";
import type { DataSource } from "../../lib/api";

const { toastMock } = vi.hoisted(() => ({ toastMock: vi.fn() }));

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

vi.mock("../../components/Toast", () => ({
  useToast: () => ({ toast: toastMock }),
}));

vi.mock("../../components/DangerConfirmDialog", () => ({
  DangerConfirmDialog: () => null,
}));

vi.mock("../../components/ConfirmDialog", () => ({
  ConfirmDialog: () => null,
}));

const mockDatasources: DataSource[] = [
  {
    id: "ds-1",
    name: "Production DB",
    db_type: "mysql",
    host: "prod.example.com",
    port: 3306,
    database_name: "app_prod",
    username: "admin",
    is_read_only: false,
    env: "prod",
    last_test_status: "success",
    last_sync_at: "2025-01-15T10:00:00Z",
    last_test_latency_ms: 42,
    last_test_tables_count: 24,
    connection_mode: "direct",
    status: "healthy",
    created_at: "2025-01-15T10:00:00Z",
  },
  {
    id: "ds-2",
    name: "Dev SQLite",
    db_type: "sqlite",
    host: "",
    port: 0,
    database_name: "/data/local.db",
    username: "",
    is_read_only: true,
    env: "dev",
    last_test_status: "failed",
    last_test_error: "File not found",
    connection_mode: "direct",
    status: "unhealthy",
    created_at: "2025-01-15T10:00:00Z",
  },
];

function renderPage(overrides: Partial<React.ComponentProps<typeof DataSourcesPage>> = {}) {
  return render(
    <DataSourcesPage
      onSelectDataSource={vi.fn()}
      activeDataSource={null}
      activeProject={null}
      onRefreshDatasources={vi.fn(async () => { await api.listDatasources(); })}
      initialShowAddForm={false}
      datasources={[]}
      {...overrides}
    />
  );
}

describe("DataSourcesPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toastMock.mockClear();
    vi.mocked(api.listDatasources).mockResolvedValue([]);
  });

  it("shows empty state when no datasources exist", async () => {
    const { getByText } = renderPage();
    await waitFor(() => expect(api.listDatasources).toHaveBeenCalled());
    expect(getByText("暂无数据源连接")).toBeInTheDocument();
    expect(getByText("添加一个数据库连接以开始使用")).toBeInTheDocument();
  });

  it("renders list and detail by default in management mode", async () => {
    vi.mocked(api.listDatasources).mockResolvedValue(mockDatasources);
    const { container } = renderPage({ datasources: mockDatasources });

    await waitFor(() => expect(api.listDatasources).toHaveBeenCalled());
    expect(container.querySelector(".hifi-datasource-list")).toBeInTheDocument();
    expect(container.querySelector(".hifi-datasource-detail")).toBeInTheDocument();
    expect(container.querySelector(".hifi-datasource-console")).toBeInTheDocument();
    expect(container.querySelectorAll(".hifi-datasource-list-item").length).toBe(2);
  });

  it("selecting a row does not activate the datasource", async () => {
    vi.mocked(api.listDatasources).mockResolvedValue(mockDatasources);
    const onSelect = vi.fn();
    const { container } = renderPage({ onSelectDataSource: onSelect, datasources: mockDatasources });

    await waitFor(() => expect(api.listDatasources).toHaveBeenCalled());
    const firstItem = container.querySelector(".hifi-datasource-list-item") as HTMLButtonElement;
    fireEvent.click(firstItem);

    expect(onSelect).not.toHaveBeenCalled();
  });

  it("enters create mode when clicking new connection button", async () => {
    vi.mocked(api.listDatasources).mockResolvedValue(mockDatasources);
    const { container } = renderPage({ datasources: mockDatasources });

    await waitFor(() => expect(api.listDatasources).toHaveBeenCalled());
    const newBtn = container.querySelector(".hifi-page-header .hifi-btn-primary") as HTMLButtonElement;
    fireEvent.click(newBtn);

    expect(container.querySelector("form.hifi-datasource-form")).toBeInTheDocument();
  });

  it("syncs add form visibility when initialShowAddForm changes", async () => {
    const { container, rerender } = renderPage({ initialShowAddForm: false });

    await waitFor(() => expect(api.listDatasources).toHaveBeenCalled());
    expect(container.querySelector("form.hifi-datasource-form")).not.toBeInTheDocument();

    rerender(
      <DataSourcesPage
        onSelectDataSource={vi.fn()}
        activeDataSource={null}
        activeProject={null}
        onRefreshDatasources={vi.fn().mockResolvedValue(undefined)}
        initialShowAddForm={true}
        datasources={[]}
      />
    );
    expect(container.querySelector("form.hifi-datasource-form")).toBeInTheDocument();

    rerender(
      <DataSourcesPage
        onSelectDataSource={vi.fn()}
        activeDataSource={null}
        activeProject={null}
        onRefreshDatasources={vi.fn().mockResolvedValue(undefined)}
        initialShowAddForm={false}
        datasources={[]}
      />
    );
    expect(container.querySelector("form.hifi-datasource-form")).not.toBeInTheDocument();
  });

  it("enters edit mode and pre-fills non-secret fields", async () => {
    vi.mocked(api.listDatasources).mockResolvedValue(mockDatasources);
    const { container } = renderPage({ datasources: mockDatasources });

    await waitFor(() => expect(api.listDatasources).toHaveBeenCalled());

    const firstItem = container.querySelector(".hifi-datasource-list-item") as HTMLButtonElement;
    fireEvent.click(firstItem);

    const detailArea = container.querySelector(".hifi-datasource-detail")!;
    const editBtn = within(detailArea as HTMLElement).getByText("编辑");
    fireEvent.click(editBtn);

    await waitFor(() => expect(container.querySelector("form.hifi-datasource-form")).toBeInTheDocument());

    const formTitle = container.querySelector(".hifi-card-title");
    expect(formTitle?.textContent).toContain("编辑");
  });

  it("shows detail view with action buttons when a datasource is selected", async () => {
    vi.mocked(api.listDatasources).mockResolvedValue(mockDatasources);
    const { container } = renderPage({ datasources: mockDatasources });

    await waitFor(() => expect(api.listDatasources).toHaveBeenCalled());

    const firstItem = container.querySelector(".hifi-datasource-list-item") as HTMLButtonElement;
    fireEvent.click(firstItem);

    const detailArea = container.querySelector(".hifi-datasource-detail");
    expect(detailArea).toBeInTheDocument();

    const buttons = detailArea!.querySelectorAll(".hifi-btn");
    const buttonTexts = Array.from(buttons).map((b) => b.textContent?.trim());
    expect(buttonTexts.some((t) => t?.includes("设为当前"))).toBe(true);
    expect(buttonTexts.some((t) => t?.includes("编辑"))).toBe(true);
    expect(buttonTexts.some((t) => t?.includes("同步"))).toBe(true);
    expect(buttonTexts.some((t) => t?.includes("删除"))).toBe(true);
  });

  it("syncs schema with AI enrichment when the semantic toggle is selected", async () => {
    vi.mocked(api.listDatasources).mockResolvedValue(mockDatasources);
    const syncSchema = vi.fn().mockResolvedValue({
      ok: true,
      aiEnrich: { ai_enriched: true, enriched_count: 3, reason: "", errors: [] },
    });
    const { container, getByText } = renderPage({
      datasources: mockDatasources,
      actions: {
        createDatasource: vi.fn(),
        updateDatasource: vi.fn(),
        deleteDatasource: vi.fn(),
        syncSchema,
        checkHealth: vi.fn(),
      },
    });

    await waitFor(() => expect(api.listDatasources).toHaveBeenCalled());
    const firstItem = container.querySelector(".hifi-datasource-list-item") as HTMLButtonElement;
    fireEvent.click(firstItem);

    const detailArea = container.querySelector(".hifi-datasource-detail")!;
    fireEvent.click(within(detailArea as HTMLElement).getByLabelText("AI 语义增强"));
    const syncButton = within(detailArea as HTMLElement).getByText("同步结构").closest("button") as HTMLButtonElement;
    fireEvent.click(syncButton);

    await waitFor(() => expect(syncSchema).toHaveBeenCalledWith("ds-1", { ai_enrich: true }));
    expect(toastMock).toHaveBeenCalledWith("表结构已同步；AI 语义增强 3 张表", "success");
    expect(getByText("AI 语义增强 3 张表")).toBeInTheDocument();
  });

  it("passes AI enrichment preference when saving a new datasource", async () => {
    const created = { ...mockDatasources[1], id: "new-ds", name: "New SQLite" };
    const createDatasource = vi.fn().mockResolvedValue(created);
    const syncSchema = vi.fn().mockResolvedValue({
      ok: true,
      aiEnrich: { ai_enriched: false, enriched_count: 0, reason: "请先在设置中配置 LLM API Key。" },
    });

    const { container } = renderPage({
      initialShowAddForm: true,
      actions: {
        createDatasource,
        updateDatasource: vi.fn(),
        deleteDatasource: vi.fn(),
        syncSchema,
        checkHealth: vi.fn(),
      },
    });

    await waitFor(() => expect(api.listDatasources).toHaveBeenCalled());
    const form = container.querySelector("form.hifi-datasource-form") as HTMLElement;
    fireEvent.click(within(form).getByLabelText("AI 语义增强"));
    fireEvent.click(within(form).getByText("SQLite"));
    fireEvent.change(within(form).getByPlaceholderText("例：本地 SQLite 数据库"), { target: { value: "New SQLite" } });
    fireEvent.change(within(form).getByPlaceholderText("C:\\Users\\...\\mydb.sqlite"), { target: { value: "D:\\data\\local.db" } });
    fireEvent.click(within(form).getByText("保存并同步 Schema"));

    await waitFor(() => expect(createDatasource).toHaveBeenCalled());
    expect(syncSchema).toHaveBeenCalledWith("new-ds", { ai_enrich: true });
    expect(toastMock).toHaveBeenCalledWith(
      "数据源创建成功；AI 语义增强未完成：请先在设置中配置 LLM API Key。",
      "warning",
    );
  });

  it("invokes onSelectDataSource when set current is clicked", async () => {
    vi.mocked(api.listDatasources).mockResolvedValue(mockDatasources);
    const onSelect = vi.fn();
    const { container } = renderPage({ onSelectDataSource: onSelect, datasources: mockDatasources });

    await waitFor(() => expect(api.listDatasources).toHaveBeenCalled());

    const firstItem = container.querySelector(".hifi-datasource-list-item") as HTMLButtonElement;
    fireEvent.click(firstItem);

    const setCurrentBtn = Array.from(container.querySelectorAll(".hifi-btn")).find(
      (btn) => btn.textContent?.includes("设为当前")
    ) as HTMLButtonElement;
    fireEvent.click(setCurrentBtn);

    expect(onSelect).toHaveBeenCalledWith(mockDatasources[0]);
  });
});
