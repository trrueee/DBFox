import { useMemo } from "react";
import { Sparkles, Cpu, Database, FileText, Terminal, HelpCircle, FlaskConical, Bug, MessageSquare } from "lucide-react";
import type { CommandItem } from "../../components/CommandPalette";
import type { EngineSchemaTable, EngineColumn } from "../../lib/api/schema";

interface UseAppCommandsProps {
  tables: EngineSchemaTable[];
  tableColumns: Record<string, EngineColumn[]>;
  openSqlConsole: () => void;
  openSmartQueryTab: () => void;
  openConversationHistoryTab: () => void;
  openLlmConfigTab: () => void;
  openConnectionManagerTab: () => void;
  openNewConnectionTab: () => void;
  openAgentEvalTab: () => void;
  openDiagnosticsTab: () => void;
  openTableTab: (tableName: string) => void;
}

export function useAppCommands({
  tables,
  tableColumns,
  openSqlConsole,
  openSmartQueryTab,
  openConversationHistoryTab,
  openLlmConfigTab,
  openConnectionManagerTab,
  openNewConnectionTab,
  openAgentEvalTab,
  openDiagnosticsTab,
  openTableTab,
}: UseAppCommandsProps) {
  const commandItems = useMemo<CommandItem[]>(() => {
    const tableById = new Map(tables.map((table) => [table.id, table]));
    const tableDisplayName = (table: EngineSchemaTable) => {
      const schemaName = table.table_schema || table.module_tag || "";
      return schemaName ? `${schemaName}.${table.table_name}` : table.table_name;
    };
    const items: CommandItem[] = [
      {
        id: "new-sql",
        name: "新建 SQL 控制台",
        category: "快捷入口",
        shortcut: "⌘N",
        icon: <Terminal size={13} className="text-green-500" />,
        action: () => openSqlConsole(),
      },
      {
        id: "smart-query",
        name: "智能问数 (AI 问数)",
        category: "快捷入口",
        icon: <Sparkles size={13} className="text-purple-500" />,
        action: () => openSmartQueryTab(),
      },
      {
        id: "conversation-history",
        name: "对话历史",
        category: "快捷入口",
        icon: <MessageSquare size={13} className="text-indigo-500" />,
        action: () => openConversationHistoryTab(),
      },
      {
        id: "llm-config",
        name: "打开 LLM 配置",
        category: "系统配置",
        icon: <Cpu size={13} className="text-pink-500" />,
        action: () => openLlmConfigTab(),
      },
      {
        id: "create-datasource",
        name: "新建数据源连接",
        category: "数据源",
        icon: <Database size={13} className="text-blue-500" />,
        action: () => openNewConnectionTab(),
      },
      {
        id: "connection-manager",
        name: "数据源连接管理",
        category: "数据源",
        icon: <Database size={13} className="text-slate-500" />,
        action: () => openConnectionManagerTab(),
      },
      {
        id: "agent-eval",
        name: "Agent 评测 (Golden 任务)",
        category: "AI 能力",
        icon: <FlaskConical size={13} className="text-amber-500" />,
        action: () => openAgentEvalTab(),
      },
      {
        id: "diagnostics-logs",
        name: "打开诊断日志",
        category: "开发与诊断",
        icon: <Bug size={13} className="text-rose-500" />,
        action: () => openDiagnosticsTab(),
      },
    ];

    tables.forEach((table) => {
      const displayName = tableDisplayName(table);
      items.push({
        id: `table-${table.id}`,
        name: `打开表: ${displayName}`,
        category: `数据表 (${table.table_schema || table.module_tag || "未分组"})`,
        icon: <FileText size={13} className="text-blue-500" />,
        action: () => openTableTab(table.table_name),
      });
    });

    Object.entries(tableColumns).forEach(([tableId, columns]) => {
      const table = tableById.get(tableId);
      const tableName = table?.table_name ?? tableId;
      const displayName = table ? tableDisplayName(table) : tableName;
      columns.forEach((col) => {
        items.push({
          id: `field-${tableId}-${col.column_name}`,
          name: `查看字段: ${displayName}.${col.column_name} (${col.column_type})`,
          category: `表字段 (${displayName})`,
          icon: <HelpCircle size={13} className="text-slate-400" />,
          action: () => openTableTab(tableName),
        });
      });
    });

    return items;
  }, [
    tables,
    tableColumns,
    openSqlConsole,
    openSmartQueryTab,
    openConversationHistoryTab,
    openLlmConfigTab,
    openConnectionManagerTab,
    openNewConnectionTab,
    openAgentEvalTab,
    openDiagnosticsTab,
    openTableTab,
  ]);

  return { commandItems };
}
