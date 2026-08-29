import { useMemo } from "react";
import { Bug, Cpu, FolderKanban, Home, MessageSquare, PackageOpen, Palette, Plus } from "lucide-react";
import type { CommandItem } from "../../components/CommandPalette";
import type { ConversationSummary } from "../../types/conversation";
import type { AppSettingsSection } from "../../types/settings";

export interface UseAppCommandsProps {
  conversations: ConversationSummary[];
  showSmartQueryHome: () => void;
  showProjectOverview: () => void;
  openConversation: (conversationId: string) => void;
  openSettings: (section?: AppSettingsSection) => void;
}

export function useAppCommands({
  conversations,
  showSmartQueryHome,
  showProjectOverview,
  openConversation,
  openSettings,
}: UseAppCommandsProps) {
  const commandItems = useMemo<CommandItem[]>(() => {
    const items: CommandItem[] = [
      {
        id: "new-task",
        name: "新任务",
        category: "新任务",
        icon: <Plus size={16} />,
        action: () => showSmartQueryHome(),
      },
      {
        id: "home",
        name: "主页",
        category: "前往",
        icon: <Home size={16} />,
        action: () => showSmartQueryHome(),
      },
      {
        id: "project-context",
        name: "项目管理",
        description: "配置项目资源，查看最近工作",
        category: "前往",
        icon: <FolderKanban size={16} />,
        action: () => showProjectOverview(),
      },
      {
        id: "extensions",
        name: "打开扩展",
        category: "操作",
        icon: <PackageOpen size={16} />,
        action: () => openSettings("dlc"),
      },
      {
        id: "appearance-settings",
        name: "外观与字号设置",
        category: "设置",
        icon: <Palette size={16} />,
        action: () => openSettings("appearance"),
      },
      {
        id: "llm-config",
        name: "模型服务设置",
        category: "设置",
        icon: <Cpu size={16} />,
        action: () => openSettings("model"),
      },
      {
        id: "diagnostics-logs",
        name: "系统诊断",
        category: "设置",
        icon: <Bug size={16} />,
        action: () => openSettings("diagnostics"),
      },
    ];
    conversations.slice(0, 8).forEach((conversation) => {
      items.push({
        id: `conversation-${conversation.id}`,
        name: conversation.title || "新对话",
        description: conversationCommandDescription(conversation),
        category: "最近工作",
        icon: <MessageSquare size={16} />,
        action: () => openConversation(conversation.id),
      });
    });

    return items;
  }, [
    conversations,
    showSmartQueryHome,
    showProjectOverview,
    openConversation,
    openSettings,
  ]);

  return { commandItems };
}

function conversationCommandDescription(conversation: ConversationSummary) {
  const lastMessage = conversation.last_message?.trim();
  if (lastMessage && lastMessage !== conversation.title.trim()) return lastMessage;
  const updatedAt = new Date(conversation.updated_at || "");
  if (Number.isNaN(updatedAt.getTime())) return "继续这段对话";
  return `上次更新于 ${updatedAt.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  })}`;
}
