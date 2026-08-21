# R7.1 DLC SDK / CLI / Conformance 证据

> 文档类型：平台实现与验证证据
>
> 状态：本地门禁通过，远端矩阵待 PR
>
> 最后核验：2026-08-21

## 结果

R7.1 将既有 Extension API、Frontend Host types、manifest schema、canonical
integrity/signature rules 和测试 fixture builder 收敛为一套开发者工具链。新增
`dbfox-dlc init/build/sign/test`，但没有设计新的运行时、包格式、registry 或签名协议。

- `engine.dlc.package_builder` 是确定性产品 builder；`acme.echo` 与 `dbfox.github`
  conformance fixture 的有效包均改用它构建。测试 helper 仅保留畸形 archive 故障注入。
- Host verifier 与 builder 共用 archive bounds、control allowlist、native extension ban、
  canonical JSON、signed bytes、entrypoint presence 和 React Host ownership 规则。
- `sdk/frontend/index.d.ts` 成为 Renderer 与 DLC 作者共用的 Frontend Host v1 类型来源；
  Renderer 原有重复接口改为直接 re-export。
- `sdk/schema/manifest.schema.json` 从 `DlcManifest` 生成并接受二次生成稳定性检查。
- `test` 只在新临时目录内执行生产 verifier、Python compile 与 Node ES module parse，
  不创建 `DlcPackageService`、不读取或修改 installed registry、不执行 DLC 代码，也不声称 sandbox。

## 安全与确定性

- v2 Ed25519 private key 使用 PKCS#8 PEM；`init --generate-key` 默认加密，既有文件不覆盖，
  私钥权限在 POSIX 上设为 `0600`，私钥字节不打印且不进入 archive。
- 离线 unsigned package 已绑定 publisher public key；`sign` 必须用匹配 private key，避免
  signing boundary 静默替换 publisher identity。
- ZIP entry 使用排序 POSIX path、1980 固定时间、固定 regular-file mode 和 `ZIP_STORED`；
  canonical JSON 与确定性 Ed25519 使同 source/manifest/key 产生完全相同 bytes/digest。
- Builder 只采集 real、非 symlink 的 `backend/` 与 `frontend/`，排除 `node_modules`、`.git`
  和 `__pycache__`，并复用 Host 大小、数量、路径和 native binary 边界。
- Bare React import、可识别的 embedded React runtime、缺失 backend/frontend entrypoint 均在
  build 与 install/restart reverify 路径 fail-closed。

## 调研和复用决定

- 项目内已有 `DlcPackageVerifier`、`DlcManifest`、`DlcIntegrity`、Ed25519 trust primitives、
  test archive builder 和两个 first-party fixtures，故采用提取共同常量与薄 CLI，而非另写 verifier。
- Python 官方将 `argparse` 作为基本 CLI 的标准实现，`zipfile.ZipInfo` 提供显式 timestamp、
  create system 与 external attributes；当前需求不需要 Typer/Click 或第三方 archive library。
- 既有 `cryptography` 已支持 Ed25519 generate、PKCS#8 PEM、BestAvailableEncryption 和 raw
  public key serialization，未增加密钥库依赖。
- 未采用 Node/Python 双签名实现、复制 manifest DTO、Renderer bundle 自带 React、CLI registry
  安装测试或 subprocess/temporary directory 伪 sandbox。无兼容层、双写或迁移债务。

官方依据：

- [Python argparse](https://docs.python.org/3/library/argparse.html)
- [Python zipfile / ZipInfo](https://docs.python.org/3/library/zipfile.html)
- [Python packaging console scripts](https://packaging.python.org/en/latest/specifications/pyproject-toml/#entry-points)
- [cryptography Ed25519](https://cryptography.io/en/latest/hazmat/primitives/asymmetric/ed25519/)

## 本地证据

- DLC package/trust/backend/lifecycle/version/activation/fixture/GitHub/CLI：`97 passed`。
- CI classifier 与 first-party fixture focused suite：`14 passed`。
- Frontend DLC/Dock：`33 passed`。
- Pyflakes：通过。
- Mypy：`304 source files`，通过。
- ESLint：`0 errors`；24 个既有 Fast Refresh warnings。
- TypeScript test typecheck：通过。
- Manifest schema 二次生成：无变化。

## 远端门禁

PR 必须通过常规 required checks。新增 `DLC SDK contract` 三平台 job 会在 Windows、macOS、
Linux 分别完成 encrypted/unencrypted key、deterministic build、offline sign、Host verification、
CLI 自举、`acme.echo` 和 `dbfox.github` build/test。随后再执行 `ci.yml workflow_dispatch` 的三平台
packaged release contract，成功后才合并。
