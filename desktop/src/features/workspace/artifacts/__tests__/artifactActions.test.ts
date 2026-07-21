import { describe, expect, it } from "vitest";
import { escapeCsvCell, toCsv } from "../artifactActions";

describe("CSV formula-injection protection", () => {
  it("matches the backend contract for BOM, whitespace, and control-prefixed formulas", () => {
    expect(escapeCsvCell("=1+1")).toBe("'=1+1");
    expect(escapeCsvCell("+cmd")).toBe("'+cmd");
    expect(escapeCsvCell("@user")).toBe("'@user");
    expect(escapeCsvCell("\ufeff=1+1")).toBe("'\ufeff=1+1");
    expect(escapeCsvCell("\u2003\t\r\n@cmd")).toBe("'\u2003\t\r\n@cmd");
    expect(escapeCsvCell("\x00\x1f+cmd")).toBe("'\x00\x1f+cmd");
    expect(escapeCsvCell("\n\t=SUM(1,2)")).toBe("'\n\t=SUM(1,2)");
    expect(escapeCsvCell("safe\n=1+1")).toBe("safe\n=1+1");
  });

  it("preserves ordinary negative numbers but protects executable minus expressions", () => {
    expect(escapeCsvCell("-10")).toBe("-10");
    expect(escapeCsvCell("\u00a0-0.25e3")).toBe("\u00a0-0.25e3");
    expect(escapeCsvCell("-1+1")).toBe("'-1+1");
  });

  it("protects headers and multiline cells without changing their CSV quoting", () => {
    const header = "\ufeff=column";
    const dangerousMultiline = "\n\t=SUM(1,2)";
    const csv = toCsv([header, "note"], [[dangerousMultiline, "first\nsecond"], ["-10", "safe"]]);

    expect(csv).toContain(`"${escapeCsvCell(header)}","note"`);
    expect(csv).toContain(`"${escapeCsvCell(dangerousMultiline)}","first\nsecond"`);
    expect(csv).toContain('"-10","safe"');
  });
});
