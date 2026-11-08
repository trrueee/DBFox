import { describe, expect, it } from "vitest";
import { conversationTitle } from "../conversationTitle";

describe("conversation title", () => {
  it("uses a short meaningful first sentence while leaving the original prompt untouched", () => {
    const prompt = "请帮我分析本周订单。再生成一份完整的销售报告，保留每一步。";
    expect(conversationTitle(prompt)).toBe("分析本周订单");
    expect(prompt).toContain("再生成一份完整");
  });
  it("keeps emoji and combining characters intact when truncating", () => {
    const title = conversationTitle("👨‍👩‍👧‍👦".repeat(30));
    expect(title).toBe("👨‍👩‍👧‍👦".repeat(21) + "…");
  });
  it("handles empty markdown and excludes internal citation syntax", () => {
    expect(conversationTitle("#  ")).toBe("新对话");
    expect(conversationTitle("{{cite:private-id}} 核对订单")).toBe("核对订单");
  });
});
