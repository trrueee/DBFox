import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  CheckIcon,
  CaretDownIcon,
  FolderSimpleIcon,
  CircleNotchIcon,
  PlusIcon,
  ArrowsClockwiseIcon,
  GearIcon,
} from "@/components/icons";
import { Button, DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "../../../components/ui";
import { useWorkspaceStore } from "../../../stores/workspaceStore";
import { useProjectState } from "../../projects/useProjectState";
import { useSavedApiConfig } from "../../../hooks/useSavedApiConfig";
import { saveStoredApiConfig } from "../../../lib/llmConfig";
import { listLlmModels } from "../../../lib/api/agent";
import { getUserErrorMessage } from "../../../lib/api/client";

export function ComposerContext({ busy = false }: { busy?: boolean }) {
  const projectId = useWorkspaceStore(state => state.activeProjectId);
  const setActiveProject = useWorkspaceStore(state => state.setActiveProject);
  const openSettings = useWorkspaceStore(state => state.openSettings);
  const openProjectCreate = useWorkspaceStore(state => state.openProjectCreate);
  const { projects, activeProject } = useProjectState(projectId);
  const config = useSavedApiConfig();
  const [modelOpen, setModelOpen] = useState(false);
  const models = useQuery({
    queryKey: ["llm-models", config.apiBase, config.credentialId],
    enabled: modelOpen && Boolean(config.credentialId),
    queryFn: async () => {
      const result = await listLlmModels(config.credentialId, config.apiBase);
      if (!result.ok) throw new Error(result.error_message || "模型列表暂不可用。");
      return [...new Set((result.models ?? []).map(model => model.id))];
    },
    retry: false,
    staleTime: 5 * 60 * 1000,
  });
  const options = [...new Set([config.modelName, ...(models.data ?? [])].filter(Boolean))];

  return <>
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button type="button" variant="ghost" size="sm" className="dbfox-composer__context dbfox-composer__project"
          disabled={busy} aria-label={`当前项目：${activeProject?.name ?? "选择项目"}`} title={activeProject?.name ?? "选择项目"}
          onClick={event => event.stopPropagation()}>
          <FolderSimpleIcon size={16} aria-hidden="true" />
          <span>{activeProject?.name ?? "选择项目"}</span><CaretDownIcon size={16} aria-hidden="true" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="dbfox-composer__context-menu">
        {projects.map(project => <DropdownMenuItem key={project.id} onSelect={() => setActiveProject(project.id)}>
          <FolderSimpleIcon size={16} aria-hidden="true" /><span>{project.name}</span>
          {project.id === projectId ? <CheckIcon size={16} aria-hidden="true" /> : null}
        </DropdownMenuItem>)}
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={openProjectCreate}><PlusIcon size={16} aria-hidden="true" />打开文件夹</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
    <DropdownMenu open={modelOpen} onOpenChange={setModelOpen}>
      <DropdownMenuTrigger asChild>
        <Button type="button" variant="ghost" size="sm" className="dbfox-composer__context dbfox-composer__model"
          disabled={busy} aria-label={`当前模型：${config.modelName || (config.credentialId ? "服务默认" : "配置模型")}`}
          title="选择下一条消息使用的模型" onClick={event => event.stopPropagation()}>
          <span>{config.modelName || (config.credentialId ? "服务默认" : "配置模型")}</span><CaretDownIcon size={16} aria-hidden="true" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="dbfox-composer__context-menu dbfox-composer__model-menu">
        {config.credentialId ? <>
          <DropdownMenuItem onSelect={() => saveStoredApiConfig({ ...config, modelName: "" })}>
            <span>服务默认</span>{!config.modelName ? <CheckIcon size={16} aria-hidden="true" /> : null}
          </DropdownMenuItem>
          {options.map(model => <DropdownMenuItem key={model} onSelect={() => saveStoredApiConfig({ ...config, modelName: model })}>
            <span>{model}</span>{config.modelName === model ? <CheckIcon size={16} aria-hidden="true" /> : null}
          </DropdownMenuItem>)}
          {models.isFetching ? <div className="dbfox-composer__model-status" role="status"><CircleNotchIcon size={16} className="dbfox-composer__loading" aria-hidden="true" />正在获取模型…</div> : null}
          {models.isError ? <div className="dbfox-composer__model-status" role="alert">{getUserErrorMessage(models.error, "模型列表暂不可用。")}</div> : null}
          <DropdownMenuItem disabled={models.isFetching} onSelect={event => { event.preventDefault(); void models.refetch(); }}>
            <ArrowsClockwiseIcon size={16} aria-hidden="true" />{models.isError ? "重试获取模型" : "刷新模型列表"}
          </DropdownMenuItem>
          <DropdownMenuSeparator />
        </> : null}
        <DropdownMenuItem onSelect={() => openSettings("model")}><GearIcon size={16} aria-hidden="true" />模型服务设置</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  </>;
}
