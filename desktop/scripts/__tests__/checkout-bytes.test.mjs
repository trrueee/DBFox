import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdir, mkdtemp, readFile, realpath, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { basename, dirname, join } from "node:path";
import { expect, it } from "vitest";

it.each(["true", "false"])("keeps verified artwork and generated source bytes with autocrlf=%s", async (autocrlf) => {
  const temporaryRoot = await realpath(tmpdir());
  const directory = await mkdtemp(join(temporaryRoot, "dbfox-checkout-bytes-"));
  const attributesFile = new URL("../../../.gitattributes", import.meta.url);
  const files = new Map([
    ["desktop/assets/phosphor/verified.svg", Buffer.from("<svg>\r\n<path/>\r\n</svg>\r\n")],
    ["desktop/assets/lobe/verified.svg", Buffer.from("<svg>\n<path/>\n</svg>\n")],
    ["desktop/public/assets/ui-icons/phosphor-test.svg", Buffer.from("<svg>\n<symbol/>\n</svg>\n")],
    ["dlcs/dbfox.music/frontend/vendor/runtime.js", Buffer.from("// pinned\r\nexport const value = 1;\r\n")],
    ["dlcs/dbfox_data/frontend/vendor/runtime.js", Buffer.from("// pinned\nexport const value = 2;\n")],
    ["desktop/src/components/icons/index.ts", Buffer.from("// generated\nexport const icon = 1;\n")],
    ["desktop/src/components/brand/providerPaths.ts", Buffer.from("// generated\nexport const provider = 1;\n")],
  ]);
  const git = (...args) => execFileSync("git", ["-c", `core.autocrlf=${autocrlf}`, ...args], {
    cwd: directory,
    stdio: ["ignore", "pipe", "pipe"],
  });
  try {
    git("init", "--quiet");
    await writeFile(join(directory, ".gitattributes"), existsSync(attributesFile) ? await readFile(attributesFile) : "");
    await writeFile(join(directory, "control.txt"), "ordinary\ntext\n");
    for (const [path, bytes] of files) {
      await mkdir(dirname(join(directory, path)), { recursive: true });
      await writeFile(join(directory, path), bytes);
    }
    git("add", "--force", "--", ".gitattributes", "control.txt", ...files.keys());
    for (const [path, bytes] of files) {
      expect(git("cat-file", "blob", `:${path}`), `${path}: index`).toEqual(bytes);
      expect(git("cat-file", "--filters", `--path=${path}`, `:${path}`), `${path}: checkout`).toEqual(bytes);
    }
    expect(git("cat-file", "--filters", "--path=control.txt", ":control.txt").toString()).toBe(
      autocrlf === "true" ? "ordinary\r\ntext\r\n" : "ordinary\ntext\n",
    );
  } finally {
    if (dirname(directory) !== temporaryRoot || !basename(directory).startsWith("dbfox-checkout-bytes-")) {
      throw new Error("Refusing to remove an unexpected fixture directory");
    }
    await rm(directory, { recursive: true, force: true });
  }
}, 15_000);
