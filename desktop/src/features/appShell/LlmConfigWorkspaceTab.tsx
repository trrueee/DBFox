import { LlmConfigPanel } from "../../components/LlmConfigPanel";
import { useApiConfig } from "../../hooks/useApiConfig";
import type { WorkspaceTab } from "../../types/workspace";
import { WorkspaceShell } from "./WorkspaceShell";
import { testDraftLlmConnection } from "./llmDraftConnection";

interface LlmConfigWorkspaceTabProps {
  activeTab: WorkspaceTab;
  showToast: (message: string) => void;
}

/**
 * Kept as an independently loaded workspace route so model configuration UI
 * and its credential-test client are not part of the desktop bootstrap path.
 */
export function LlmConfigWorkspaceTab({ activeTab, showToast }: LlmConfigWorkspaceTabProps) {
  const { draft, updateDraft, handleSave } = useApiConfig();

  return (
    <WorkspaceShell title={activeTab.title} description="配置桌面端智能问数使用的模型接口。">
      <LlmConfigPanel
        chrome="workspace"
        variant="page"
        config={draft}
        onChange={updateDraft}
        onSave={async () => {
          try {
            await handleSave();
            showToast("LLM 配置保存成功");
          } catch (error) {
            showToast(error instanceof Error ? error.message : "LLM 凭据保存失败");
          }
        }}
        onTestConnection={async () => {
          showToast("正在测试与模型接口握手…");
          try {
            const result = await testDraftLlmConnection(draft);
            if (result.ok) {
              showToast(`连接测试通过 (${result.latency_ms}ms)，模型 ${result.model} 可达`);
              return true;
            } else {
              showToast(`连接失败 [${result.error_code || "UNKNOWN"}]: ${result.error_message || "未知错误"}`);
              return false;
            }
          } catch (error: unknown) {
            const message = error instanceof Error ? error.message : "无法连接到引擎服务，请确认引擎正在运行。";
            showToast(`连接测试失败: ${message}`);
            return false;
          }
        }}
      />
    </WorkspaceShell>
  );
}
