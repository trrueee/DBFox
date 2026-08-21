import { mkdir, rm, symlink, writeFile } from "node:fs/promises";
import { join, resolve } from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import { ProjectFolderAccess, validateDlcPackage } from "../nativeFiles";

const roots: string[] = [];
afterEach(async () => {
  for (const root of roots.splice(0)) await rm(root, { recursive: true, force: true });
});

describe("Electron native file boundary", () => {
  it("lists and reads only below a persisted approved root", async () => {
    const base = resolve(`.native-files-${Date.now()}-${Math.random()}`);
    roots.push(base);
    const project = join(base, "project");
    const outside = join(base, "outside");
    await mkdir(join(project, "src"), { recursive: true });
    await mkdir(join(project, "node_modules"));
    await writeFile(join(project, "README.md"), "# Demo\n");
    await writeFile(join(project, "src", "blob.bin"), Buffer.from([0, 1, 2]));
    await mkdir(outside);
    await writeFile(join(outside, "secret.txt"), "outside");
    await symlink(outside, join(project, "escape"), process.platform === "win32" ? "junction" : "dir");
    const access = new ProjectFolderAccess(join(base, "access.json"));
    await access.approve(project);

    const listing = await access.list(project);
    expect(listing.error).toBeNull();
    expect(listing.entries.map((entry) => entry.name)).toEqual(["escape", "src", "README.md"]);
    expect((await access.read(join(project, "README.md"))).content).toBe("# Demo\n");
    expect((await access.read(join(project, "src", "blob.bin"))).binary).toBe(true);
    expect((await access.read(join(outside, "secret.txt"))).error).toContain("不在你选择过的项目文件夹内");
    expect((await access.read(join(project, "escape", "secret.txt"))).error).toContain("不在你选择过的项目文件夹内");
  });

  it("fails closed on a corrupted approval store and validates DLC files", async () => {
    const base = resolve(`.native-files-${Date.now()}-${Math.random()}`);
    roots.push(base);
    await mkdir(base);
    const accessFile = join(base, "access.json");
    await writeFile(accessFile, "{broken");
    expect((await new ProjectFolderAccess(accessFile).list(base)).error).toContain("授权记录损坏");
    const dlc = join(base, "fixture.dbfox-dlc");
    await writeFile(dlc, "fixture");
    expect(await validateDlcPackage(dlc)).toBe(dlc);
    const zip = join(base, "fixture.zip");
    await writeFile(zip, "fixture");
    await expect(validateDlcPackage(zip)).rejects.toThrow(".dbfox-dlc");
  });
});
