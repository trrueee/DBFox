import { cleanup, fireEvent, render, waitFor, within } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { DataSource } from "../../lib/api";
import { api } from "../../lib/api";
import { stripSensitiveDatasourceForm } from "../../lib/datasourceFormSecurity";
import { DataSourcesPage } from "../DataSourcesPage";

const testState = vi.hoisted(() => ({
  datasources: [] as DataSource[],
  activeDatasource: null as DataSource | null,
  setActiveDatasourceId: vi.fn(),
  createDatasource: vi.fn(),
  updateDatasource: vi.fn(),
  deleteDatasource: vi.fn(),
  syncSchema: vi.fn(),
}));
const { toastMock, credentialApi } = vi.hoisted(() => ({
  toastMock: vi.fn(),
  credentialApi: {
    enrollCredentials: vi.fn(),
    releaseCredentialLease: vi.fn(),
  },
}));

vi.mock("../../features/datasource/useDatasourceState", () => ({
  useDatasourceState: () => testState,
}));
vi.mock("../../lib/api", () => ({
  api: {
    testConnection: vi.fn(),
  },
}));
vi.mock("../../lib/api/credentials", () => ({
  enrollCredentials: credentialApi.enrollCredentials,
  releaseCredentialLease: credentialApi.releaseCredentialLease,
}));
vi.mock("../../components/toastState", () => ({
  useToast: () => ({ toast: toastMock }),
}));
vi.mock("../../components/DangerConfirmDialog", () => ({
  DangerConfirmDialog: () => null,
}));

const datasources: DataSource[] = [
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
    connection_mode: "direct",
    status: "unhealthy",
    created_at: "2025-01-15T10:00:00Z",
  },
];

function renderPage(options: {
  initialShowAddForm?: boolean;
  chrome?: "page" | "workspace";
  items?: DataSource[];
} = {}) {
  testState.datasources = options.items ?? [];
  testState.activeDatasource = testState.datasources[0] ?? null;
  return render(
    <DataSourcesPage
      initialShowAddForm={options.initialShowAddForm}
      chrome={options.chrome}
    />,
  );
}

function fillSqliteForm(container: HTMLElement) {
  const form = container.querySelector("form.hifi-datasource-form") as HTMLElement;
  fireEvent.click(within(form).getByText("SQLite"));
  fireEvent.change(within(form).getByPlaceholderText("例：本地 SQLite 数据库"), {
    target: { value: "New SQLite" },
  });
  fireEvent.change(within(form).getByPlaceholderText("C:\\Users\\...\\mydb.sqlite"), {
    target: { value: "D:\\data\\local.db" },
  });
  return form;
}

describe("DataSourcesPage", () => {
  beforeEach(() => {
    cleanup();
    vi.clearAllMocks();
    localStorage.clear();
    credentialApi.enrollCredentials.mockResolvedValue(null);
    credentialApi.releaseCredentialLease.mockResolvedValue(undefined);
    testState.createDatasource.mockResolvedValue(datasources[1]);
    testState.updateDatasource.mockResolvedValue(datasources[0]);
    testState.deleteDatasource.mockResolvedValue({ message: "deleted" });
    testState.syncSchema.mockResolvedValue({
      ok: true,
      aiEnrich: null,
    });
  });

  it("strips datasource form secrets without changing ordinary fields", () => {
    const form = {
      name: "Production DB",
      password: "db-secret",
      ssh_password: "ssh-secret",
      ssh_pkey_passphrase: "key-secret",
      host: "prod.example.com",
    };

    expect(stripSensitiveDatasourceForm(form)).toEqual({
      ...form,
      password: "",
      ssh_password: "",
      ssh_pkey_passphrase: "",
    });
  });

  it("renders an empty state or a datasource list from query state", () => {
    const empty = renderPage();
    expect(empty.getByText("暂无数据源连接")).toBeInTheDocument();
    empty.unmount();

    const populated = renderPage({ items: datasources });
    expect(populated.container.querySelectorAll(".hifi-datasource-list-item")).toHaveLength(2);
    expect(populated.container.querySelector(".hifi-datasource-detail")).toBeInTheDocument();
  });

  it("keeps row selection local and activates only through the explicit action", () => {
    const { container } = renderPage({ items: datasources });
    fireEvent.click(container.querySelector(".hifi-datasource-list-item") as HTMLButtonElement);
    expect(testState.setActiveDatasourceId).not.toHaveBeenCalled();

    fireEvent.click(
      within(container.querySelector(".hifi-datasource-detail") as HTMLElement)
        .getByRole("button", { name: "设为当前" }),
    );
    expect(testState.setActiveDatasourceId).toHaveBeenCalledWith("ds-1");
  });

  it("uses embedded chrome without duplicating the workspace title", () => {
    const view = renderPage({ items: datasources, chrome: "workspace" });
    expect(view.queryByRole("heading", { name: "数据源管理" })).not.toBeInTheDocument();
    expect(view.getByRole("button", { name: "新建连接" })).toBeInTheDocument();
  });

  it("synchronizes schema through the query mutation and reports AI enrichment", async () => {
    testState.syncSchema.mockResolvedValue({
      ok: true,
      aiEnrich: { ai_enriched: true, enriched_count: 3, reason: "", errors: [] },
    });
    const { container } = renderPage({ items: datasources });
    fireEvent.click(container.querySelector(".hifi-datasource-list-item") as HTMLButtonElement);
    const detail = within(container.querySelector(".hifi-datasource-detail") as HTMLElement);
    fireEvent.click(detail.getByLabelText("AI 语义增强"));
    fireEvent.click(detail.getByRole("button", { name: "同步结构" }));

    await waitFor(() =>
      expect(testState.syncSchema).toHaveBeenCalledWith("ds-1", { ai_enrich: true }),
    );
    expect(toastMock).toHaveBeenCalledWith("表结构已同步；AI 语义增强 3 张表", "success");
  });

  it("creates, selects, and synchronizes a datasource through query mutations", async () => {
    const created = { ...datasources[1], id: "new-ds", name: "New SQLite" };
    testState.createDatasource.mockResolvedValue(created);
    const { container } = renderPage({ initialShowAddForm: true });
    const form = fillSqliteForm(container);
    fireEvent.click(within(form).getByRole("button", { name: "保存并同步表结构" }));

    await waitFor(() => expect(testState.createDatasource).toHaveBeenCalled());
    expect(testState.syncSchema).toHaveBeenCalledWith("new-ds", undefined);
    expect(testState.setActiveDatasourceId).toHaveBeenCalledWith("new-ds");
    expect(container.querySelector("form.hifi-datasource-form")).not.toBeInTheDocument();
  });

  it("keeps the created datasource active when the follow-up schema sync fails", async () => {
    const created = { ...datasources[1], id: "new-ds", name: "New SQLite" };
    testState.createDatasource.mockResolvedValue(created);
    testState.syncSchema.mockRejectedValue(new Error("sync unavailable"));
    const { container } = renderPage({ initialShowAddForm: true });
    fireEvent.click(
      within(fillSqliteForm(container))
        .getByRole("button", { name: "保存并同步表结构" }),
    );

    await waitFor(() => expect(testState.setActiveDatasourceId).toHaveBeenCalledWith("new-ds"));
    expect(toastMock).toHaveBeenCalledWith(
      "数据源已保存，但表结构同步失败：表结构同步失败，请重试。",
      "warning",
    );
  });

  it("releases an unclaimed credential lease when creation fails", async () => {
    credentialApi.enrollCredentials.mockResolvedValue({
      credentials: [{ id: "cred-draft", kind: "datasource_password" }],
      lease_id: "lease-draft",
    });
    testState.createDatasource.mockRejectedValue(new Error("network"));
    const { container } = renderPage({ initialShowAddForm: true });
    const form = container.querySelector("form.hifi-datasource-form") as HTMLElement;
    fireEvent.change(within(form).getByLabelText("连接名称"), { target: { value: "Draft DB" } });
    fireEvent.change(within(form).getByLabelText("主机地址"), { target: { value: "db.test" } });
    fireEvent.change(within(form).getByLabelText("数据库名"), { target: { value: "analytics" } });
    fireEvent.change(within(form).getByLabelText("用户名"), { target: { value: "reader" } });
    fireEvent.change(within(form).getByLabelText("密码"), { target: { value: "secret" } });
    fireEvent.click(within(form).getByRole("button", { name: "保存并同步表结构" }));

    await waitFor(() =>
      expect(credentialApi.releaseCredentialLease).toHaveBeenCalledWith("lease-draft"),
    );
  });

  it("clears a stale save error after a successful connection test", async () => {
    testState.createDatasource.mockRejectedValue(new Error("network"));
    vi.mocked(api.testConnection).mockResolvedValue({
      success: true,
      message: "数据库连接测试成功！",
    });
    const { container } = renderPage({ initialShowAddForm: true });
    const form = container.querySelector("form.hifi-datasource-form") as HTMLElement;
    fireEvent.change(within(form).getByLabelText("连接名称"), { target: { value: "Draft DB" } });
    fireEvent.change(within(form).getByLabelText("主机地址"), { target: { value: "db.test" } });
    fireEvent.change(within(form).getByLabelText("数据库名"), { target: { value: "analytics" } });
    fireEvent.change(within(form).getByLabelText("用户名"), { target: { value: "reader" } });
    fireEvent.click(within(form).getByRole("button", { name: "保存并同步表结构" }));
    await waitFor(() => expect(within(form).getByText("保存失败，请重试。")).toBeInTheDocument());

    fireEvent.click(within(form).getByRole("button", { name: "测试连接" }));
    await waitFor(() => expect(within(form).getByText("数据库连接测试成功！")).toBeInTheDocument());
    expect(within(form).queryByText("保存失败，请重试。")).not.toBeInTheDocument();
  });
});
