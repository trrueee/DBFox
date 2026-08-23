import { useQuery } from "@tanstack/react-query";
import { Boxes, Check, Database, Folder, GitFork, Plus, X } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "../../components/ui";
import type {
  ProjectResourceDescriptor,
  RequestedResourceRef,
} from "../../lib/api/generated/types.gen";
import { listProjectResources } from "../resources/projectResourceRepository";
import "./ResourceContextPicker.css";

interface ResourceContextPickerProps {
  projectId: string;
  selected: readonly RequestedResourceRef[];
  onChange: (next: RequestedResourceRef[]) => void | Promise<void>;
  disabled?: boolean;
  error?: string | null;
}

const resourceQueryKey = (projectId: string) => ["project-resources", projectId] as const;

export function ResourceContextPicker({
  projectId,
  selected,
  onChange,
  disabled = false,
  error,
}: ResourceContextPickerProps) {
  const resourcesQuery = useQuery({
    queryKey: resourceQueryKey(projectId),
    queryFn: () => listProjectResources(projectId),
    enabled: Boolean(projectId),
    staleTime: 15_000,
  });
  const resources = resourcesQuery.data ?? [];
  const selectedKeys = new Set(selected.map(resourceKey));
  const descriptors = new Map(resources.map((resource) => [resourceKey(resource), resource]));

  const commit = (next: RequestedResourceRef[]) => {
    void Promise.resolve(onChange(next)).catch(() => undefined);
  };
  const toggle = (resource: ProjectResourceDescriptor) => {
    const key = resourceKey(resource);
    const next = selectedKeys.has(key)
      ? selected.filter((ref) => resourceKey(ref) !== key)
      : [...selected, { kind: resource.kind, id: resource.id }];
    commit([...next]);
  };
  const remove = (ref: RequestedResourceRef) => {
    commit(selected.filter((candidate) => resourceKey(candidate) !== resourceKey(ref)));
  };

  return (
    <div className="resource-context-picker" aria-label="Agent 上下文">
      <div className="resource-context-picker__chips">
        {selected.map((ref) => {
          const descriptor = descriptors.get(resourceKey(ref));
          const Icon = resourceIcon(ref.kind);
          const name = descriptor?.name || ref.id;
          return (
            <span className="resource-context-chip" key={resourceKey(ref)} title={`${kindLabel(ref.kind)} · ${name}`}>
              <Icon size={13} aria-hidden="true" />
              <span>{name}</span>
              <button
                type="button"
                onClick={() => remove(ref)}
                disabled={disabled}
                aria-label={`从对话上下文移除 ${name}`}
              >
                <X size={12} aria-hidden="true" />
              </button>
            </span>
          );
        })}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              className="resource-context-picker__add"
              disabled={disabled || resourcesQuery.isPending || Boolean(resourcesQuery.error)}
              aria-label="添加 Agent 上下文"
            >
              <Plus size={13} aria-hidden="true" />
              {selected.length === 0 ? "添加上下文" : "上下文"}
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="resource-context-picker__menu">
            {resources.length === 0 ? (
              <DropdownMenuItem disabled>
                这个项目还没有可用资源
              </DropdownMenuItem>
            ) : resources.map((resource) => {
              const Icon = resourceIcon(resource.kind);
              const isSelected = selectedKeys.has(resourceKey(resource));
              return (
                <DropdownMenuItem
                  key={resourceKey(resource)}
                  className="resource-context-picker__option"
                  onSelect={(event) => {
                    event.preventDefault();
                    toggle(resource);
                  }}
                >
                  <Icon size={14} aria-hidden="true" />
                  <span className="resource-context-picker__option-copy">
                    <strong>{resource.name}</strong>
                    <small>{kindLabel(resource.kind)}</small>
                  </span>
                  {isSelected && <Check size={14} aria-label="已添加" />}
                </DropdownMenuItem>
              );
            })}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      {(error || resourcesQuery.error) && (
        <span className="resource-context-picker__error" role="alert">
          {error || "项目资源载入失败"}
        </span>
      )}
    </div>
  );
}

function resourceKey(ref: Pick<RequestedResourceRef, "kind" | "id">): string {
  return JSON.stringify([ref.kind, ref.id]);
}

function kindLabel(kind: string): string {
  if (kind === "dbfox.data.database") return "数据库";
  if (kind === "workspace" || kind.endsWith(".workspace")) return "工作区";
  if (kind.includes("github") || kind.endsWith(".repository")) return "GitHub 仓库";
  return "资源";
}

function resourceIcon(kind: string): LucideIcon {
  if (kind === "dbfox.data.database") return Database;
  if (kind === "workspace" || kind.endsWith(".workspace")) return Folder;
  if (kind.includes("github") || kind.endsWith(".repository")) return GitFork;
  return Boxes;
}
