import { useMemo } from "react";
import { Sparkles, Cpu, Database, FileText, Terminal, Bug, MessageSquare, Palette } from "lucide-react";
import type { TableTabDatasourceContext } from "../../types/workspace";
import type { CommandItem } from "../../components/CommandPalette";
import type { EngineSchemaTable } from "../../lib/api/schema";
import type { ConversationSummary } from "../../types/conversation";
import type { AppSettingsSection } from "../../types/settings";

const PRIMARY_SHORTCUT = /Mac|iPhone|iPad/.test(navigator.platform) ? "⌘" : "Ctrl";

export interface UseAppCommandsProps {
  tables: EngineSchemaTable[];
  conversations: ConversationSummary[];
  openSqlConsole: () => void;
  showSmartQueryHome: () => void;
  openConversation: (conversationId: string) => void;
  openSettings: (section?: AppSettingsSection) => void;
  openConnectionDialog: (mode?: "detail" | "create") => void;
  connectionManagementAvailable?: boolean;
  openTable: (
    tableName: string,
    initialSubtab?: string,
    datasource?: TableTabDatasourceContext,
  ) => void;
  activeDatasource?: TableTabDatasourceContext;
}

export function useAppCommands({
  tables,
  conversations,
  openSqlConsole,
  showSmartQueryHome,
  openConversation,
  openSettings,
  openConnectionDialog,
  connectionManagementAvailable = true,
  openTable,
  activeDatasource,
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
        id: "create-datasource",
        name: "新建数据库连接",
        category: "数据源",
        icon: <Database size={13} />,
        action: () => openConnectionDialog("create"),
      },
      {
        id: "diagnostics-logs",
        name: "系统诊断",
        category: "设置",
        icon: <Bug size={13} />,
        action: () => openSettings("diagnostics"),
      },
    ];
    if (connectionManagementAvailable) {
      items.splice(5, 0, {
        id: "connection-manager",
        name: "数据库连接管理",
        category: "数据源",
        icon: <Database size={13} />,
        action: () => openConnectionDialog("detail"),
      });
    }

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

    tables.forEach((table) => {
      const displayName = tableDisplayName(table);
      items.push({
        id: `table-${table.id}`,
        name: `打开表: ${displayName}`,
        category: `数据表 (${table.table_schema || table.module_tag || "未分组"})`,
        icon: <FileText size={13} />,
        action: () => openTable(table.table_name, "preview", activeDatasource),
      });
    });

    return items;
  }, [
    tables,
    conversations,
    openSqlConsole,
    showSmartQueryHome,
    openConversation,
    openSettings,
    openConnectionDialog,
    connectionManagementAvailable,
    openTable,
    activeDatasource,
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
