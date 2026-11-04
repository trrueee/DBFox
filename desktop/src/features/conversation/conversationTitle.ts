/** A short first-sentence title. Full instructions remain in the durable message. */
export function conversationTitle(content: string): string {
  const text = content.replace(/\{\{(?:cite|artifact):[^}]+\}\}/g, "")
    .replace(/^[\s#>*-]+/, "")
    .replace(/^(?:请|麻烦)?(?:帮我|给我|替我|为我)(?:来|先)?\s*/, "")
    .replace(/^(?:请)(?:完整|详细|认真)?\s*/, "")
    .replace(/\s+/g, " ").trim();
  const sentence = text.split(/[\n。！？!?：:；;]/u)[0]?.trim() || text;
  const graphemes = Array.from(new Intl.Segmenter("zh-CN", { granularity: "grapheme" }).segment(sentence), part => part.segment);
  if (!graphemes.length) return "新对话";
  return graphemes.length > 22 ? `${graphemes.slice(0, 21).join("").trimEnd()}…` : sentence;
}
