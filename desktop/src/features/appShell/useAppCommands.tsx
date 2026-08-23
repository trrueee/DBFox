import { useMemo } from "react";
import { Sparkles, Cpu, Bug, MessageSquare, Palette } from "lucide-react";
import type { CommandItem } from "../../components/CommandPalette";
import type { ConversationSummary } from "../../types/conversation";
import type { AppSettingsSection } from "../../types/settings";

export interface UseAppCommandsProps {
  conversations: ConversationSummary[];
  showSmartQueryHome: () => void;
  openConversation: (conversationId: string) => void;
  openSettings: (section?: AppSettingsSection) => void;
}

export function useAppCommands({
  conversations,
  showSmartQueryHome,
  openConversation,
  openSettings,
}: UseAppCommandsProps) {
  const commandItems = useMemo<CommandItem[]>(() => {
    const items: CommandItem[] = [
      {
        id: "smart-query",
        name: "智能问数 (AI 问数)",
        category: "快捷入口",
        icon: <Sparkles size={13} />,
        action: () => showSmartQueryHome(),
      },
      {
        id: "appearance-settings",
        name: "外观与字号设置",
        category: "设置",
        icon: <Palette size={13} />,
        action: () => openSettings("appearance"),
      },
      {
        id: "llm-config",
        name: "模型服务设置",
        category: "设置",
        icon: <Cpu size={13} />,
        action: () => openSettings("model"),
      },
      {
        id: "diagnostics-logs",
        name: "系统诊断",
        category: "设置",
        icon: <Bug size={13} />,
        action: () => openSettings("diagnostics"),
      },
    ];
    conversations.slice(0, 8).forEach((conversation) => {
      items.push({
        id: `conversation-${conversation.id}`,
        name: conversation.title || "新对话",
        description: conversationCommandDescription(conversation),
        category: "最近对话",
        icon: <MessageSquare size={13} />,
        action: () => openConversation(conversation.id),
      });
    });

    return items;
  }, [
    conversations,
    showSmartQueryHome,
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
