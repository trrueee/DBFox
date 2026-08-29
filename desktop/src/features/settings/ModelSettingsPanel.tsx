import { LlmConfigPanel } from "../../components/LlmConfigPanel";
import { useApiConfig } from "../../hooks/useApiConfig";
import { testDraftLlmConnection } from "../appShell/llmDraftConnection";

interface ModelSettingsPanelProps {
  showToast: (message: string) => void;
}

export function ModelSettingsPanel({ showToast }: ModelSettingsPanelProps) {
  const { draft, updateDraft, handleSave } = useApiConfig();

  return (
    <LlmConfigPanel
      config={draft}
      onChange={updateDraft}
      onSave={async () => {
        await handleSave();
        showToast("模型服务配置已保存");
      }}
      onTestConnection={async () => {
        showToast("正在测试模型服务连接…");
        const result = await testDraftLlmConnection(draft);
        if (result.ok) {
          showToast(`连接测试通过 (${result.latency_ms}ms)，模型 ${result.model} 可用`);
          return true;
        }
        showToast(`连接失败 [${result.error_code || "UNKNOWN"}]: ${result.error_message || "未知错误"}`);
        return false;
      }}
    />
  );
}
