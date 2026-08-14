import { describe, expect, it } from "vitest";
import { classifyCellValue } from "../cellValue";

describe("classifyCellValue", () => {
  it("keeps SQL null, empty text, and the literal NULL distinct", () => {
    expect(classifyCellValue(null)).toMatchObject({ kind: "null", displayText: "NULL", copyText: "NULL" });
    expect(classifyCellValue("")).toMatchObject({ kind: "text", displayText: "", copyText: "" });
    expect(classifyCellValue("NULL")).toMatchObject({ kind: "text", displayText: "NULL", copyText: "NULL" });
  });

  it("uses database types before transport strings for scalar presentation", () => {
    expect(classifyCellValue("42.50", { dataType: "decimal(10,2)" }).kind).toBe("number");
    expect(classifyCellValue("0", { dataType: "boolean" })).toMatchObject({ kind: "boolean", displayText: "FALSE" });
    expect(classifyCellValue("2026-05-09T10:22:57.506000", { dataType: "datetime" })).toMatchObject({
      kind: "datetime",
      displayText: "2026-05-09 10:22:57.506",
    });
  });

  it("classifies structured values, safe URLs, images, and binary placeholders", () => {
    expect(classifyCellValue({ enabled: true }, { dataType: "jsonb" })).toMatchObject({
      kind: "json",
      displayText: "JSON · Object(1)",
    });
    expect(classifyCellValue("https://example.com/report?id=7").kind).toBe("url");
    expect(classifyCellValue("https://cdn.example.com/a.webp").kind).toBe("image-url");
    expect(classifyCellValue("<binary>", { dataType: "blob" }).kind).toBe("binary-placeholder");
    expect(classifyCellValue("<binary>", { dataType: "varchar" }).kind).toBe("text");
  });

  it("fails closed to text for unsafe or contradictory inputs", () => {
    expect(classifyCellValue("http://cdn.example.com/a.png").kind).toBe("text");
    expect(classifyCellValue("javascript:alert(1)").kind).toBe("text");
    expect(classifyCellValue("not-json", { dataType: "json" })).toMatchObject({
      kind: "json",
      displayText: "JSON · 无法完整解析",
      parsedJson: null,
    });
  });
});
