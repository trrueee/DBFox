import { useMutation, useQuery } from "@tanstack/react-query";
import { LlmConfigPanel } from "../../components/LlmConfigPanel";
import { SettingsContent, SettingsSection } from "../../components/settings";
import { Button } from "../../components/ui";
import { useApiConfig } from "../../hooks/useApiConfig";
import { testDraftLlmConnection } from "../appShell/llmDraftConnection";
import { ApiError, getUserErrorMessage } from "../../lib/api/client";
import { localModelQuery, testLocalModel } from "../../lib/api/localModel";

import "./ModelSettingsPanel.css";

interface ModelSettingsPanelProps {
  showToast: (message: string) => void;
}

export function ModelSettingsPanel({ showToast }: ModelSettingsPanelProps) {
  const model = useQuery(localModelQuery);
  const test = useMutation({ mutationFn: testLocalModel });

  if (model.isPending) return <div className="settings-page__loading">正在读取模型设置…</div>;
  if (model.isError) {
    return <div className="settings-page__loading" role="alert">
      模型设置暂不可用 <Button size="sm" variant="ghost" onClick={() => void model.refetch()}>重试</Button>
    </div>;
  }
  if (model.data.mode === "remote") return <RemoteModelSettings showToast={showToast} />;

  const status = model.data;
  const error = status.error_message || (test.isError
    ? getUserErrorMessage(test.error, "本地推理测试未通过。")
    : test.data?.error_message);
  return (
    <SettingsContent>
      <SettingsSection
        title="本地模型"
        description="对话和工具调用由这台电脑上的模型处理。"
        trailing={<Button size="sm" variant="secondary" disabled={test.isPending || Boolean(status.error_code)}
          onClick={() => test.mutate()}>
          {test.isPending ? "正在推理…" : "测试推理"}
        </Button>}
      >
        <dl className="local-model-facts">
          <div><dt>模型</dt><dd>{status.model ?? "不可用"}</dd></div>
          {status.models_dir ? <div><dt>权重目录</dt><dd><code>{status.models_dir}</code></dd></div> : null}
          {status.model_size_bytes ? <div><dt>权重大小</dt><dd>{(status.model_size_bytes / 1024 ** 3).toFixed(2)} GiB</dd></div> : null}
          {status.context_length ? <div><dt>上下文</dt><dd>{status.context_length.toLocaleString()} tokens</dd></div> : null}
        </dl>
        {error ? <p className="local-model-status" role="alert">{error}</p> : null}
        {test.data?.ok ? <p className="local-model-status" role="status">
          推理通过 · {(test.data.latency_ms / 1000).toFixed(1)} 秒
        </p> : null}
      </SettingsSection>
    </SettingsContent>
  );
}

function RemoteModelSettings({ showToast }: ModelSettingsPanelProps) {
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
        throw new ApiError(
          result.error_message || "模型连接测试未通过，请检查服务地址、凭据和模型名称。",
          undefined,
          result.error_code || "LLM_CONNECTION_FAILED",
        );
      }}
    />
  );
}
