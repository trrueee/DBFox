export function responseText(value: unknown): string {
  const record = value && typeof value === "object" ? value as Record<string, unknown> : {};
  const answer = record.answer && typeof record.answer === "object" ? record.answer as Record<string, unknown> : {};
  if (typeof answer.answer === "string") return answer.answer;
  if (typeof record.explanation === "string") return record.explanation;
  if (typeof record.error === "string") return record.error;
  return "done";
}
