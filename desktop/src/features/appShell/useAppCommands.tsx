import { useMemo } from "react";
import { Sparkles, Cpu, Database, FileText, Terminal, Bug, MessageSquare, Palette } from "lucide-react";
import type { CommandItem } from "../../components/CommandPalette";
import type { EngineSchemaTable } from "../../lib/api/schema";
import type { ConversationSummary } from "../../types/conversation";
import type { AppSettingsSection } from "../../types/settings";

const PRIMARY_SHORTCUT = /Mac|iPhone|iPad/.test(navigator.platform) ? "⌘" : "Ctrl";

export interface UseAppCommandsProps {
  tables: EngineSchemaTable[];
  conversations: ConversationSummary[];
  openSqlConsole: () => void;
  openSmartQueryTab: () => void;
  openConversationHistoryTab: () => void;
  openConversationResult: (conversation: Pick<ConversationSummary, "id" | "title">) => void;
  openSettings: (section?: AppSettingsSection) => void;
  openConnectionManagerTab: () => void;
  openNewConnectionTab: () => void;
  openTableTab: (tableName: string) => void;
}

export function useAppCommands({
  tables,
  conversations,
  openSqlConsole,
  openSmartQueryTab,
  openConversationHistoryTab,
  openConversationResult,
  openSettings,
  openConnectionManagerTab,
  openNewConnectionTab,
  openTableTab,
}: UseAppCommandsProps) {
  const commandItems = useMemo<CommandItem[]>(() => {
    const tableDisplayName = (table: EngineSchemaTable) => {
      const schemaName = table.table_schema || table.module_tag || "";
      return schemaName ? `${schemaName}.${table.table_name}` : table.table_name;
    };
    const items: CommandItem[] = [
      {
        id: "new-sql",
        name: "新建 SQL 控制台",
        category: "快捷入口",
        shortcut: `${PRIMARY_SHORTCUT} N`,
        icon: <Terminal size={13} />,
        action: () => openSqlConsole(),
      },
      {
        id: "smart-query",
        name: "智能问数 (AI 问数)",
        category: "快捷入口",
        icon: <Sparkles size={13} />,
        action: () => openSmartQueryTab(),
      },
      {
        id: "conversation-history",
        name: "对话历史",
        category: "快捷入口",
        icon: <MessageSquare size={13} />,
        action: () => openConversationHistoryTab(),
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
        id: "create-datasource",
        name: "新建数据源连接",
        category: "数据源",
        icon: <Database size={13} />,
        action: () => openNewConnectionTab(),
      },
      {
        id: "connection-manager",
        name: "数据源连接管理",
        category: "数据源",
        icon: <Database size={13} />,
        action: () => openConnectionManagerTab(),
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
        description: conversation.last_message || "继续这段对话",
        category: "最近对话",
        icon: <MessageSquare size={13} />,
        action: () => openConversationResult(conversation),
      });
    });

    tables.forEach((table) => {
      const displayName = tableDisplayName(table);
      items.push({
        id: `table-${table.id}`,
        name: `打开表: ${displayName}`,
        category: `数据表 (${table.table_schema || table.module_tag || "未分组"})`,
        icon: <FileText size={13} />,
        action: () => openTableTab(table.table_name),
      });
    });

    return items;
  }, [
    tables,
    conversations,
    openSqlConsole,
    openSmartQueryTab,
    openConversationHistoryTab,
    openConversationResult,
    openSettings,
    openConnectionManagerTab,
    openNewConnectionTab,
    openTableTab,
  ]);

  return { commandItems };
}
