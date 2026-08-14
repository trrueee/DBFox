/** Keep database type semantics while removing storage/collation noise from compact UI labels. */
export function databaseTypeLabel(value: string | null | undefined): string {
  const normalized = value?.trim() ?? "";
  if (!normalized) return "";
  return normalized.replace(/\s+(?:CHARACTER\s+SET|COLLATE)\b.*$/i, "").trim();
}
