import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LlmConfigPanel } from "../LlmConfigPanel";
import { DEFAULT_LLM_API_BASE } from "../../lib/llmPresets";

describe("LlmConfigPanel", () => {
  afterEach(() => cleanup());

  it("uses embedded chrome without rendering its own page title", () => {
    render(
      <LlmConfigPanel
        chrome="workspace"
        variant="page"
        config={{ apiKey: "", apiBase: DEFAULT_LLM_API_BASE, modelName: "" }}
        onChange={vi.fn()}
        onSave={vi.fn()}
        onTestConnection={vi.fn()}
      />
    );

    expect(screen.queryByRole("heading", { name: "LLM 配置" })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "LLM 服务配置" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "测试连接" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "保存配置" })).toBeInTheDocument();
  });
  it("blocks saving invalid API Base values through schema validation", async () => {
    const onSave = vi.fn();

    render(
      <LlmConfigPanel
        variant="page"
        config={{ apiKey: "sk-test", apiBase: DEFAULT_LLM_API_BASE, modelName: "gpt-4o" }}
        onChange={vi.fn()}
        onSave={onSave}
      />
    );

    fireEvent.change(screen.getByLabelText("API Base URL"), { target: { value: "not-a-url" } });
    fireEvent.click(screen.getByRole("button", { name: /保存配置/ }));

    await waitFor(() => expect(onSave).not.toHaveBeenCalled());
    expect(screen.getByRole("alert").textContent).toContain("API Base URL");
  });
});
