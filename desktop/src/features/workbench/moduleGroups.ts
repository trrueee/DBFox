import type { SchemaTable } from "../../lib/api";

export function groupSchemaTables(tables: SchemaTable[], search: string) {
  const query = search.trim().toLowerCase();
  const filtered = query
    ? tables.filter((table) => table.table_name.toLowerCase().includes(query) || table.table_comment.toLowerCase().includes(query))
    : tables;

  const groups = new Map<string, SchemaTable[]>();
  for (const table of filtered) {
    const key = table.module_tag || table.table_name.split("_")[0] || "default";
    groups.set(key, [...(groups.get(key) ?? []), table]);
  }

  return Array.from(groups.entries())
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([tag, group]) => ({
      tag,
      tables: [...group].sort((a, b) => a.table_name.localeCompare(b.table_name)),
    }));
}
