import { describe, expect, it } from "vitest";

import { databaseTypeLabel } from "../databaseTypeLabel";

describe("databaseTypeLabel", () => {
  it("keeps the meaningful SQL type and removes collation details", () => {
    expect(databaseTypeLabel('VARCHAR(64) COLLATE "utf8mb4_unicode_ci"')).toBe("VARCHAR(64)");
    expect(databaseTypeLabel("VARCHAR(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")).toBe("VARCHAR(64)");
    expect(databaseTypeLabel("DECIMAL(18, 2) UNSIGNED")).toBe("DECIMAL(18, 2) UNSIGNED");
  });
});
