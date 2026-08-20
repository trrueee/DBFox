# R5.1 dbfox.github 外置包实现证据

> 文档类型：质量证据 / 架构审计
>
> 状态：当前
>
> 最后核验：2026-08-21

## 范围

R5.1 建立 `dlcs/dbfox.github` 作为 GitHub 能力的独立权威源树。该包拥有 backend、frontend、CSS、typed operations 与新安装实例的 durable state，但本阶段不迁移现有 Core 数据，也不删除旧实现；迁移属于 R5.2，Core 删除属于 R5.3。

## 调查与复用决策

- 复用现有 v2 Ed25519 签名包、Installed Registry、ContributionCompiler、BackendExtensionHost、FrontendExtensionHost、Artifact、Resource、Context 与 Operation seam。
- SQLite 直接使用 Python 标准库 `sqlite3` 的参数化查询、短连接和显式事务；没有引入 ORM、数据库 facade 或新依赖。Python 官方文档明确连接 context manager 负责事务 commit/rollback，但不会自动 close，因此 store 在单一边界同时管理 transaction 与 close。
- GitHub 读取保持固定 `api.github.com` origin、公开只读、immutable revision、路径规范化与响应上限。GitHub 官方 Contents API 允许公开仓库无 token 读取，并为较大文件提供 raw media type；DLC 将产品上限进一步收紧为 2 MiB。
- Frontend 不导入 Desktop 内部模块，不访问 Workspace store、静态 GitHub API 或任意 `dlc_id`；所有调用均通过自动绑定当前包身份的 `host.operations.invoke`，Dock 仅打开自身注册的 view type。
- 现有 Tool runtime 已包含 ArtifactDraft、ToolOutcome、ToolSemanticSpec 与 ToolInputError。R5.1 仅将这些现有类型以及窄化的 `ExtensionToolRunContext` 暴露到 public API；没有新增执行层。
- 实包验证发现 operation 的可安全公开业务错误原先会被统一压成 500。新增 `DlcOperationError` 只允许有界 code/message 与 400、404、409、429、502、503 状态，由通用 endpoint 转成 typed Problem Details；未开放 traceback 或任意 HTTP header。

## 所有权与迁移债务

- 新包的状态唯一写入 `data_path/state.sqlite3`，对应产品路径 `APP_DATA/dlcs/data/dbfox.github/state.sqlite3`。
- R5.1 不从 Core SQL 读取，也不双写 Core 与 DLC 数据库。
- Core GitHub 源码暂时保留，仅用于 R5.1/R5.2 分阶段兼容。删除条件固定为：R5.2 完成幂等迁移且 DLC 数据库成为唯一权威后，在 R5.3 删除静态 route、ORM、tools/resources/context 与 frontend composition。
- 测试签名 key 仅存在于 conformance fixture builder；仓库不包含生产私钥。通用 production build/sign/key management 延后到 R7。

## 验证

- 权威源树 backend 无 `engine.*` import，frontend 无 Desktop 相对 import 或直接 fetch。
- 同一源树可构建 v2 签名 `.dbfox-dlc`，完成 inspect、trust、install、enable 与 ContributionCompiler activation。
- 激活结果包含 3 tools、resource provider/resolver、context contributor、Artifact contract、6 typed operations 与 frontend entrypoint；owner/digest 均绑定 `dbfox.github` 包身份。
- SQLite 项目隔离与 revision freshness fail-closed；非 GitHub origin、自定义端口/query、HTTP URL 与路径穿越均被拒绝。
- Frontend conformance 证明 Connector、Requested Resource、Dock 与 Artifact renderer 全部经 bounded host 注册，registration 阶段不执行 operation 或打开 Dock。
