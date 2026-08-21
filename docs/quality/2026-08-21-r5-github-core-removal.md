# R5.3 GitHub Core 运行图移除证据

> 文档类型：质量证据 / 架构边界
>
> 状态：当前
>
> 最后核验：2026-08-21

## 结论

GitHub 已从 DBFox Core 的生产运行图移除。未激活 `dbfox.github` DLC 时，Core 不再提供
GitHub FastAPI 路由、ORM 模型、tools、resource provider/resolver、context contributor、
前端 connector/store/dock/artifact renderer、手写 API facade 或静态 CSS。

历史 `github_repository_bindings` 表和创建它的 Alembic revision 保留不删，以支持旧数据库
升级。一次性导入实现已移至 `engine.migrations.github_dlc_state`，该模块没有运行时 CRUD
入口，也不被 API、Runtime Kernel、sidecar composition 或桌面前端引用。

## 调查与复用决策

- 复用 R1–R5.2 已有 `ContributionCompiler`、Backend/Frontend Host、operation 与 artifact
  contract；没有增加 GitHub 特判、PluginManager、Service Locator 或第二套组合机制。
- 复用 Alembic [`EnvironmentContext.configure(include_object=...)`](https://alembic.sqlalchemy.org/en/latest/api/runtime.html#alembic.runtime.environment.EnvironmentContext.configure)
  官方扩展点，把已退役但必须保留的历史表排除出 autogenerate 删除建议；没有保留当前
  ORM 镜像模型。
- 核对 PyInstaller [hook/hidden import 官方机制](https://pyinstaller.org/en/latest/hooks.html) 后，
  确认仓库没有显式收集 GitHub 模块；删除生产 import 即会把它移出 sidecar 分析图。
  `httpx` 仍被 LLM HTTP client 使用，因此不能随 GitHub 静态模块删除。未新增依赖。
- 未采用“保留空 facade/兼容 router”的方案，因为它会继续把业务域暴露为 Core 能力，
  也会掩盖无包时的真实 absence。

## 防回归门禁

- 工程合同断言静态后端/前端路径不存在，核心组合根不得重新引用 GitHub 域符号。
- generated OpenAPI 不得包含 `/projects/{project_id}/github` 静态路径。
- 内置工具冻结集合与 snapshot identity 已移除 GitHub；GitHub 能力只能由已验证、启用并在
  重启时激活的 DLC contribution 提供。
- 迁移测试仍覆盖幂等导入、目标冲突 fail-closed、提交后验证失败重放，以及从历史 revision
  到 head 的真实升级。

## 债务与后续

- 兼容层/双写/第二业务 SSOT：无。
- 历史迁移债务：保留旧表与迁移 helper，删除条件是该 revision 早于未来明确公布的升级地板；
  删除前不得破坏受支持旧版本升级。
- R5.4 将以真实包证明 absent、install-disabled、enable+restart、disable+restart、卸载保留
  数据与历史记录的完整产品行为。
