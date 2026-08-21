# R6 Side-by-Side Update / Rollback 证据

> 文档类型：质量证据 / 跨平台发布合同
>
> 状态：当前
>
> 最后核验：2026-08-21

## 结论

Installed Registry schema v2 为每个 DLC 保存有界的 verified digest/version 集合、唯一
`selected_digest` 与 `desired_enabled`。安装新版本不执行、不删除旧版本且不自动切换；只有
显式 select 后的受控重启才能改变 `RuntimeContributionSnapshot` 的 active digest。rollback
复用同一个 select 合同，只切换包身份，不回滚 DLC-owned schema。

本 work package 只有在常规 CI 与 Linux、Windows、macOS `workflow_dispatch` release
contract 全绿、且 artifacts 包含 R6 packaged evidence 后才可合并。

## 调研与复用决策

- 通过 CodeGraph 与源码审计复用 `DlcPackageStore`、签名重验、`ContributionCompiler`、typed
  lifecycle API、controlled restart、DLC Center 与 R4.3/R5.4 frozen-sidecar harness。
- SemVer 2.0 继续用于 manifest 格式验证和展示，不用于自动排序或自动升级；选择以签名包的
  exact digest 为唯一身份，避免 build metadata 或版本排序隐式改变用户意图。
- TUF consistent-snapshot / rollback-attack 原则支持继续保留不可变 content-addressed bytes
  和显式可信选择，但 DBFox 当前是本地文件安装，没有远端 update metadata/channel，因此不
  引入完整 TUF 角色、metadata 或新供应链依赖。
- Python 官方 `sys.dont_write_bytecode` 合同用于阻止宿主在已验证包树写入 `__pycache__`；
  否则首次激活后生成的 `.pyc` 会让 restart reverify 把宿主自身写入判为 package tamper。
- 未新增第三方依赖、Service Locator、版本 mapper、自动 GC、fallback 或双写。

## Registry 与安全边界

- schema v1 只由严格 legacy model 读取并单向投影；下一次 registry mutation 原子写为 v2，
  不在磁盘维护双格式。
- 每个 DLC 最多保存 32 个版本；达到上限必须显式移除旧版本，不自动删除 rollback bytes。
- 相同版本号的不同 digest 继续拒绝，避免同一展示版本出现模糊身份；不同 publisher key 不能
  接管既有 DLC id。
- selected digest 和 active digest 都禁止删除。完整卸载要求 desired disabled 且所有已安装
  digest 均不在 active snapshot，然后删除所有未引用 executable bytes，默认保留 DLC data。
- 历史 ToolAttempt 仍保存原 `owner_id/package_digest`；select、rollback、cleanup 不改写历史。

## 自动证明

- Python registry/service/API：v1→v2 单向迁移、side-by-side install、selection 不改变旧 snapshot、
  update restart、rollback restart、unknown/selected/active digest 负向删除、显式 old-version cleanup、
  full uninstall 与 data retention。
- Schema incompatibility：模拟 DLC-owned schema 升级后选择旧包，activation fail-closed；数据标记
  与两个 immutable package 仍保留，可重新选择兼容包。
- Desktop：展示 installed/selected/active/pending，显式 Select / Roll back、remove-old-version
  确认以及“包回滚不等于数据回滚”文案。
- Frozen sidecar：真实签名 `acme.echo` v1/v2 在 packaged runtime 中完成 install-without-select、
  update restart、rollback restart、selected/active delete rejection、inactive old-version removal、
  disable/restart/uninstall/data retained；R5.4 `dbfox.github` 证据继续在同一 run 中执行。

## 兼容与清理

schema v1 reader 是唯一临时兼容面，负责人为 DLC platform。删除条件：一个稳定主版本已经把所有
可支持安装升级写成 schema v2，并且迁移遥测/支持窗口确认不再存在 v1 registry。它不承载新业务
逻辑，所有写入和后续能力只使用 schema v2。
