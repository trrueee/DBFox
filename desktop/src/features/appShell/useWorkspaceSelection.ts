import { useState, useCallback } from "react";
import { useToast } from "../../components/Toast";

interface UseWorkspaceSelectionProps {
  onToast?: (msg: string) => void;
}

export function useWorkspaceSelection(props?: UseWorkspaceSelectionProps) {
  const { toast } = useToast();
  const onToast = props?.onToast || toast;
  const [selectedTables, setSelectedTables] = useState<string[]>([]);
  const [contextTables, setContextTables] = useState<string[]>([]);
  const [tableSubTabs, setTableSubTabs] = useState<Record<string, string>>({});

  const addContextTable = useCallback((tableName: string) => {
    setContextTables((prev) => (prev.includes(tableName) ? prev : [...prev, tableName]));
    onToast(`已添加表 ${tableName} 到问数上下文`);
  }, [onToast]);

  const removeContextTable = useCallback((tableName: string) => {
    setContextTables((prev) => prev.filter((table) => table !== tableName));
  }, []);

  const clearContextTables = useCallback(() => {
    setContextTables([]);
  }, []);

  return {
    selectedTables,
    setSelectedTables,
    contextTables,
    setContextTables,
    tableSubTabs,
    setTableSubTabs,
    addContextTable,
    removeContextTable,
    clearContextTables,
  };
}
