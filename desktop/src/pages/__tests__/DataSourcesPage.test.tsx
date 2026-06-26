import { cleanup, render, fireEvent, waitFor, within } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DataSourcesPage } from "../DataSourcesPage";
import { api } from "../../lib/api";
import type { DataSource } from "../../lib/api";
import { stripSensitiveDatasourceForm } from "../../lib/datasourceFormSecurity";

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
    cleanup();
    vi.clearAllMocks();
    localStorage.clear();
    toastMock.mockClear();
    vi.mocked(api.listDatasources).mockResolvedValue([]);
  });

  it("strips datasource form secrets without changing non-secret fields", () => {
    const form = {
      db_type: "mysql",
      name: "Production DB",
      host: "prod.example.com",
      port: 3306,
      database_name: "app_prod",
      username: "admin",
      password: "db-secret",
      is_read_only: false,
      env: "prod",
      ssh_enabled: true,
      ssh_host: "bastion.example.com",
      ssh_port: 22,
      ssh_username: "ops",
      ssh_password: "ssh-secret",
      ssh_pkey_path: "C:\\keys\\prod.pem",
      ssh_pkey_passphrase: "key-secret",
      ssl_enabled: true,
      ssl_ca_path: "C:\\certs\\ca.pem",
      ssl_cert_path: "C:\\certs\\client.pem",
      ssl_key_path: "C:\\certs\\client.key",
      ssl_verify_identity: true,
    };

    expect(stripSensitiveDatasourceForm(form)).toEqual({
      ...form,
      password: "",
      ssh_password: "",
      ssh_pkey_passphrase: "",
    });
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
    expect(container.querySelector(".ds-page-console")).toBeInTheDocument();
    expect(container.querySelectorAll(".hifi-datasource-list-item").length).toBe(2);
  });

  it("filters sqlite datasources without crashing when host is null", async () => {
    const datasources = [
      { ...mockDatasources[1], host: null },
    ] as unknown as DataSource[];
    vi.mocked(api.listDatasources).mockResolvedValue(datasources);
    const { container } = renderPage({ datasources });

    await waitFor(() => expect(api.listDatasources).toHaveBeenCalled());
    const searchInput = container.querySelector('input[placeholder="搜索..."]') as HTMLInputElement;
    expect(() => {
      fireEvent.change(searchInput, { target: { value: "local" } });
    }).not.toThrow();
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
    const newBtn = within(container.querySelector(".ds-page-header") as HTMLElement).getByRole("button", {
      name: "新建连接",
    });
    fireEvent.click(newBtn);

    expect(container.querySelector("form.hifi-datasource-form")).toBeInTheDocument();
  });

  it("uses embedded chrome without a duplicate page title", async () => {
    vi.mocked(api.listDatasources).mockResolvedValue(mockDatasources);
    const { getByRole, queryByRole } = renderPage({ datasources: mockDatasources, chrome: "workspace" });

    await waitFor(() => expect(api.listDatasources).toHaveBeenCalled());

    expect(queryByRole("heading", { name: "数据源管理" })).not.toBeInTheDocument();
    expect(getByRole("button", { name: "新建连接" })).toBeInTheDocument();
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

    const detail = within(detailArea as HTMLElement);
    expect(detail.getByRole("button", { name: "设为当前" })).toBeInTheDocument();
    expect(detail.getByRole("button", { name: "编辑" })).toBeInTheDocument();
    expect(detail.getByRole("button", { name: "同步结构" })).toBeInTheDocument();
    expect(detail.getByRole("button", { name: "删除" })).toBeInTheDocument();
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

  it("passes stored LLM config when syncing schema with AI enrichment", async () => {
    localStorage.setItem(
      "dbfox-api-config",
      JSON.stringify({
        apiKey: "sk-configured",
        apiBase: "https://api.deepseek.com/v1",
        modelName: "deepseek-chat",
      }),
    );
    vi.mocked(api.listDatasources).mockResolvedValue(mockDatasources);
    const syncSchema = vi.fn().mockResolvedValue({
      ok: true,
      aiEnrich: { ai_enriched: true, enriched_count: 1, reason: "", errors: [] },
    });
    const { container } = renderPage({
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
    fireEvent.click(within(detailArea as HTMLElement).getByText("同步结构").closest("button") as HTMLButtonElement);

    await waitFor(() =>
      expect(syncSchema).toHaveBeenCalledWith("ds-1", {
        ai_enrich: true,
        api_key: "sk-configured",
        api_base: "https://api.deepseek.com/v1",
        model_name: "deepseek-chat",
      }),
    );
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

  it("keeps a newly created datasource when schema sync fails", async () => {
    const created = { ...mockDatasources[1], id: "new-ds-sync-fail", name: "New SQLite" };
    const createDatasource = vi.fn().mockResolvedValue(created);
    const syncSchema = vi.fn().mockRejectedValue(new Error("sync unavailable"));
    const onSelect = vi.fn();

    const { container } = renderPage({
      initialShowAddForm: true,
      onSelectDataSource: onSelect,
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
    fireEvent.click(within(form).getByText("SQLite"));
    fireEvent.change(within(form).getByPlaceholderText("例：本地 SQLite 数据库"), { target: { value: "New SQLite" } });
    fireEvent.change(within(form).getByPlaceholderText("C:\\Users\\...\\mydb.sqlite"), { target: { value: "D:\\data\\local.db" } });
    fireEvent.click(within(form).getByText("保存并同步 Schema"));

    await waitFor(() => expect(createDatasource).toHaveBeenCalled());
    expect(syncSchema).toHaveBeenCalledWith("new-ds-sync-fail", undefined);
    await waitFor(() => expect(onSelect).toHaveBeenCalledWith(created));
    expect(toastMock).toHaveBeenCalledWith("数据源已保存，但 Schema 同步失败：sync unavailable", "warning");
    expect(container.querySelector("form.hifi-datasource-form")).not.toBeInTheDocument();
  });

  it("invokes onSelectDataSource when set current is clicked", async () => {
    vi.mocked(api.listDatasources).mockResolvedValue(mockDatasources);
    const onSelect = vi.fn();
    const { container } = renderPage({ onSelectDataSource: onSelect, datasources: mockDatasources });

    await waitFor(() => expect(api.listDatasources).toHaveBeenCalled());

    const firstItem = container.querySelector(".hifi-datasource-list-item") as HTMLButtonElement;
    fireEvent.click(firstItem);

    const detailArea = container.querySelector(".hifi-datasource-detail")!;
    const setCurrentBtn = within(detailArea as HTMLElement).getByRole("button", { name: "设为当前" });
    fireEvent.click(setCurrentBtn);

    expect(onSelect).toHaveBeenCalledWith(mockDatasources[0]);
  });
});
