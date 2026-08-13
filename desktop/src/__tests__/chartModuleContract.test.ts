import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

describe("chart module contract", () => {
  it("uses the package ESM core entry in the deferred production chunk", () => {
    const source = readFileSync(
      resolve(process.cwd(), "src/features/workspace/artifacts/ChartArtifactView.tsx"),
      "utf8",
    );

    expect(source).toContain('from "echarts-for-react/esm/core"');
    expect(source).not.toContain('from "echarts-for-react/lib/core"');
  });
});
