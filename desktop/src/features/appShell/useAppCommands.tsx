import { useMemo } from "react";
import { Sparkles, Cpu, Database, FileText, Terminal, HelpCircle, FlaskConical } from "lucide-react";
import type { CommandItem } from "../../components/CommandPalette";
import type { EngineSchemaTable, EngineColumn } from "../engine/engineApi";

import type { WorkspaceTab } from "../../mock/databoxMock";

interface UseAppCommandsProps {
  tables: EngineSchemaTable[];
  tableColumns: Record<string, EngineColumn[]>;
  openSqlConsole: () => void;
  openLlmConfigTab: () => void;
  openConnectionManagerTab: () => void;
  openNewConnectionTab: () => void;
  openAgentEvalTab: () => void;
  openTableTab: (tableName: string) => void;
  setTabs: React.Dispatch<React.SetStateAction<WorkspaceTab[]>>;
  setActiveTabId: (id: string) => void;
}

export function useAppCommands({
  tables,
  tableColumns,
  openSqlConsole,
  openLlmConfigTab,
  openConnectionManagerTab,
  openNewConnectionTab,
  openAgentEvalTab,
  openTableTab,
  setTabs,
  setActiveTabId,
}: UseAppCommandsProps) {
  const commandItems = useMemo<CommandItem[]>(() => {
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
        action: () => {
          setTabs((prev) =>
            prev.some((t) => t.type === "smart-query")
              ? prev
              : [...prev, { id: "smart-query", title: "问数工作台", type: "smart-query" }]
          );
          setActiveTabId("smart-query");
        },
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
    ];

    tables.forEach((table) => {
      items.push({
        id: `table-${table.table_name}`,
        name: `打开表: ${table.table_name}`,
        category: `数据表 (${table.module_tag || "未分组"})`,
        icon: <FileText size={13} className="text-blue-500" />,
        action: () => openTableTab(table.table_name),
      });
    });

    Object.entries(tableColumns).forEach(([tableName, columns]) => {
      columns.forEach((col) => {
        items.push({
          id: `field-${tableName}-${col.column_name}`,
          name: `查看字段: ${tableName}.${col.column_name} (${col.column_type})`,
          category: `表字段 (${tableName})`,
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
    openLlmConfigTab,
    openConnectionManagerTab,
    openNewConnectionTab,
    openAgentEvalTab,
    openTableTab,
    setTabs,
    setActiveTabId,
  ]);

  return { commandItems };
}
