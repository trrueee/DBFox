import { resolve } from "node:path";
import { ESLint } from "eslint";
import { expect, it } from "vitest";

it("checks executable first-party JavaScript for undefined symbols", async () => {
  const eslint = new ESLint({
    cwd: resolve(process.cwd(), ".."),
    overrideConfigFile: resolve(process.cwd(), "eslint.dlcs.config.js"),
  });
  const [result] = await eslint.lintText("export function render() { return missingHost.ui.Tree; }", {
    filePath: "dlcs/dbfox.workspace/frontend/contract-probe.js",
  });
  expect(result.messages).toEqual([expect.objectContaining({ ruleId: "no-undef", severity: 2 })]);
});
