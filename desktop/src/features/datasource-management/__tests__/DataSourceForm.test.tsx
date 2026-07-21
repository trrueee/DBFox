import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DataSourceForm } from "../DataSourceForm";
import { emptyDatasourceForm, formFromDataSource, type DatasourceFormState } from "../formState";

function renderForm(overrides: Partial<React.ComponentProps<typeof DataSourceForm>> = {}) {
  const updateForm = vi.fn();
  const props = {
    mode: "create" as const,
    form: emptyDatasourceForm(),
    formError: "",
    testResult: { status: "idle" as const, message: "" },
    actionState: "idle" as const,
    syncAiEnrich: false,
    onSyncAiEnrichChange: vi.fn(),
    updateForm,
    onTestConnection: vi.fn(),
    onSubmit: vi.fn(),
    ...overrides,
  };

  render(<DataSourceForm {...props} />);
  return props;
}

describe("DataSourceForm", () => {
  beforeEach(() => cleanup());

  it("keeps datasource form defaults and datasource normalization stable", () => {
    expect(emptyDatasourceForm()).toMatchObject({
      db_type: "mysql",
      port: 3306,
      env: "dev",
      ssh_port: 22,
      ssl_verify_identity: true,
    });

    expect(
      formFromDataSource({
        id: "ds-structure",
        name: "Local",
        db_type: "sqlite",
        connection_mode: "direct",
        host: null,
        port: 0,
        database_name: "local.db",
        username: null,
        status: "active",
        created_at: "",
      }),
    ).toMatchObject({
      db_type: "sqlite",
      host: "",
      port: 0,
      username: "",
      database_name: "local.db",
    });
  });

  it("validates required MySQL fields through the form schema before submit", async () => {
    const onSubmit = vi.fn();

    renderForm({ onSubmit });

    fireEvent.click(screen.getByRole("button", { name: "保存并同步表结构" }));

    expect(onSubmit).not.toHaveBeenCalled();
    expect(await screen.findByText("请完整填写连接名称、主机、数据库名和用户名。")).toBeInTheDocument();
  });

  it("passes normalized valid form values to submit after schema validation", async () => {
    const onSubmit = vi.fn();
    const form: DatasourceFormState = {
      ...emptyDatasourceForm(),
      name: "Production DB",
      host: "prod.example.com",
      database_name: "creatorhub",
      username: "admin",
      port: 3306,
    };

    renderForm({ form, onSubmit });

    fireEvent.click(screen.getByRole("button", { name: "保存并同步表结构" }));

    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
        name: "Production DB",
        host: "prod.example.com",
        database_name: "creatorhub",
        username: "admin",
        port: 3306,
      })),
    );
  });
});
