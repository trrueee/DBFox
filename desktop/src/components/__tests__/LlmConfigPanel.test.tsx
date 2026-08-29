import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LlmConfigPanel } from "../LlmConfigPanel";
import { ApiError } from "../../lib/api/client";
import { DEFAULT_LLM_API_BASE } from "../../lib/llmProviders";

describe("LlmConfigPanel", () => {
  afterEach(() => cleanup());

  it("renders one focused settings flow without duplicate summaries", () => {
    render(
      <LlmConfigPanel
        config={{ credentialId: "", apiKey: "", apiBase: DEFAULT_LLM_API_BASE, modelName: "" }}
        onChange={vi.fn()}
        onSave={vi.fn()}
        onTestConnection={vi.fn()}
      />
    );

    expect(screen.queryByRole("heading", { name: "LLM 配置" })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "连接与模型" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "模型选择" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "当前配置" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "测试连接" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "保存配置" })).toBeInTheDocument();
  });
  it("blocks saving invalid API Base values through schema validation", async () => {
    const onSave = vi.fn();

    render(
      <LlmConfigPanel
        config={{ credentialId: "cred_llm_api_key_test", apiKey: "TEST_LLM_SECRET", apiBase: DEFAULT_LLM_API_BASE, modelName: "gpt-4o" }}
        onChange={vi.fn()}
        onSave={onSave}
      />
    );

    fireEvent.change(screen.getByLabelText("API Base URL"), { target: { value: "not-a-url" } });
    fireEvent.click(screen.getByRole("button", { name: /保存配置/ }));

    await waitFor(() => expect(onSave).not.toHaveBeenCalled());
    expect(screen.getByRole("alert").textContent).toContain("API Base URL");
  });

  it("retains structured save failures in the form", async () => {
    const onSave = vi.fn().mockRejectedValue(new ApiError(
      "credential backend path must stay private",
      503,
      "CREDENTIAL_VAULT_UNAVAILABLE",
      [],
      { request_id: "model-request-8", secret: "must-not-render" },
    ));
    render(
      <LlmConfigPanel
        config={{ credentialId: "", apiKey: "", apiBase: DEFAULT_LLM_API_BASE, modelName: "" }}
        onChange={vi.fn()}
        onSave={onSave}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "保存配置" }));
    expect(await screen.findByText("模型服务配置保存失败")).toBeTruthy();
    fireEvent.click(screen.getByText("技术详情"));
    expect(screen.getByText("CREDENTIAL_VAULT_UNAVAILABLE")).toBeTruthy();
    expect(screen.getByText("model-request-8")).toBeTruthy();
    expect(document.body.textContent).not.toContain("credential backend path");
    expect(document.body.textContent).not.toContain("must-not-render");
  });
});
