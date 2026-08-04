# DBFox Runtime 基础能力 ADR

状态口径：2026-08-03。本文记录第二轮反证验证后已实施的决定；“暂缓”不是缺陷确认。

## ADR-01：Rust 是 Runtime 生命周期唯一权威

- 标题：由 Rust `RuntimeSupervisor` 独占 Sidecar 生命周期事实
- 状态：Accepted / Implemented
- 上下文：WebView 无法可靠持有原生 Child 状态，旧配置也不能代表进程仍存活。
- 必须满足的约束：Ready 后持续观察退出；旧 session 立即失效；generation 单调递增；60 秒内只允许三次自动重启；关闭应用不得触发重启。
- 候选方案：前端管理；Rust 只负责启动；Rust Supervisor。
- 方案比较：前两者无法原子协调 Child、端口、Token 与关闭竞态；Supervisor 可在同一所有权边界结算。
- 决定：采用 Rust Supervisor，WebView 只消费状态事件和 session。
- 决定理由：进程事实与进程句柄位于同一层，恢复策略可测试且不会形成双重权威。
- 负面影响：Rust 状态机和故障测试增加；崩溃循环后仍需人工重启。
- 可逆性：中；可替换 Supervisor 实现，但 IPC 合同应保持。
- 何时重新评估：Sidecar 改为系统服务或多 Runtime 架构时。

## ADR-02：Release 强制单实例

- 标题：正式桌面应用只允许一个 Host 实例
- 状态：Accepted / Implemented
- 上下文：产品只有一个本地 Runtime 和共享元数据库，多实例没有独立工作区语义。
- 必须满足的约束：插件必须最先注册；第二进程不得进入 setup、启动 Sidecar 或迁移；已有窗口被显示、取消最小化并聚焦。
- 候选方案：允许多实例；靠 SQLite 锁失败；Release 单实例。
- 方案比较：数据库锁只能局部降低风险且用户体验不可控；单实例在资源创建前消除冲突。
- 决定：使用 Tauri 官方 single-instance 插件。
- 决定理由：符合当前产品约束，且不把迁移互斥误当完整实例协调协议。
- 负面影响：暂不支持多个独立窗口进程。
- 可逆性：高；未来可先定义工作区隔离再移除插件。
- 何时重新评估：产品明确支持多窗口/多 profile 且数据目录完成隔离时。

## ADR-03：诊断包由 Rust 组装

- 标题：Rust 汇总各组件提供的脱敏诊断 fragment
- 状态：Accepted / Implemented
- 上下文：Python、Host、WebView 分别拥有不同日志和运行状态，任一组件单独导出都不完整。
- 必须满足的约束：二次脱敏；输入、单字符串、Host 日志及总包有界；不包含凭据、数据库内容或查询结果；只读取普通文件；ZIP 原子发布。
- 候选方案：Python 组装；WebView 组装；独立工具；Rust 组装。
- 方案比较：Rust 同时拥有平台日志目录、Host 状态和 IPC，且可在 WebView/Engine 不完整时仍导出部分证据。
- 决定：Engine 与 WebView 提交已脱敏 JSON，Rust 再校验、脱敏并生成 ZIP。
- 决定理由：保持所有权清晰，同时不让 Rust理解业务日志模型。
- 负面影响：fragment schema 和 ZIP schema 都需兼容管理。
- 可逆性：中；独立工具可复用现有 fragment 合同。
- 何时重新评估：需要远程支持上传或跨设备关联时。

## ADR-04：采用 RFC 9457 Problem Details

- 标题：HTTP 错误统一为 `application/problem+json`
- 状态：Accepted / Implemented
- 上下文：原有字符串、`detail` envelope 和自定义对象并存，客户端无法稳定分类。
- 必须满足的约束：包含 type/title/status/detail/instance；扩展 code/request_id/checks/errors；验证错误不得回显 input；未知异常使用固定公共消息。
- 候选方案：保留多格式；自定义 envelope；RFC 9457。
- 方案比较：RFC 标准字段适合生成客户端和诊断关联，扩展字段保留 DBFox 机器码。
- 决定：服务边界统一转换，业务路由可继续抛出既有 `HTTPException`/领域异常。
- 决定理由：迁移面集中，错误语义和敏感信息边界可独立测试。
- 负面影响：旧客户端若读取嵌套 `detail.code` 必须同步升级。
- 可逆性：低；发布后应保持 wire contract。
- 何时重新评估：仅在协议大版本升级时。

## ADR-05：HTTP 与 SSE 共用 Runtime Transport

- 标题：保留 HTTP+SSE，但共享不可变 `RuntimeSession`
- 状态：Accepted / Implemented
- 上下文：SSE 曾直接捕获全局端口和 Token，Sidecar 换端口后与普通请求行为分叉。
- 必须满足的约束：generation/port/token 同步切换；重建 URL；GET/HEAD/OPTIONS 最多恢复一次；非幂等请求在响应未知时不自动重放；SSE 保留 cursor/snapshot。
- 候选方案：继续两套实现；改 WebSocket；统一逻辑 Transport。
- 方案比较：WebSocket 不解决生命周期所有权；统一 Transport 可保留已有 SSE 恢复协议并减少迁移风险。
- 决定：所有请求通过同一 session-aware fetch，SSE 只增加解析与 cursor 语义。
- 决定理由：最小变更覆盖端口漂移和 Token 轮换，不重写稳定的 Agent 事件协议。
- 负面影响：写请求失败后可能要求用户显式重试或查询幂等状态。
- 可逆性：高；上层业务合同不依赖具体传输实现。
- 何时重新评估：需要全双工低延迟控制或多 Runtime 路由时。

## ADR-06：现在引入最小运行时握手

- 标题：IPC 返回 protocol、serverInfo、generation 和 capabilities
- 状态：Accepted / Implemented
- 上下文：即使暂无自动更新，Host 与 Sidecar 仍可能因开发、残留进程或安装失败形成版本错配。
- 必须满足的约束：按协议和能力判断兼容性；不使用软件版本猜测功能；不兼容时在请求前失败。
- 候选方案：无握手；只比 semver；协议版本加能力集合。
- 方案比较：semver 无法表达可选能力；能力集合支持向后兼容演进。
- 决定：协议版本固定为 1，当前强制要求 http/sse/problem-details 三项能力。
- 决定理由：成本小，能把潜在错配转为确定的启动错误。
- 负面影响：新增能力必须维护兼容矩阵。
- 可逆性：低；IPC 字段可扩展但不应移除。
- 何时重新评估：首次需要并行支持两个协议版本时。

## ADR-07：SQLite 采用产物门禁

- 标题：最低 SQLite 3.51.3，当前升级目标 3.53.4
- 状态：Accepted / Implemented gate；Runtime upgrade 受构建解释器约束
- 上下文：依赖 hash lock 不约束 CPython 自带 SQLite；原 Windows 构建证据为 3.45.3，最终验收产物已升级为 CPython 3.14.6 / SQLite 3.53.1。
- 必须满足的约束：执行最终 frozen Sidecar；记录 Python/SQLite/version tuple/source_id/compile options；manifest 绑定 Sidecar SHA-256 与 target triplet；从最终安装包再次提取、执行并比对。
- 候选方案：信任构建机；固定旧 Python；最低版本门禁。
- 方案比较：只有产物门禁能发现各平台解释器和链接方式差异。
- 决定：低于 3.51.3 阻断发布，3.53.4 为当前构建环境升级目标。
- 决定理由：3.51.3 是已知 WAL-reset 缺陷的修复边界；目标版本留出补丁余量。
- 负面影响：现有 3.45.3 构建机会立即失败，必须先升级正式构建解释器。
- 可逆性：门禁阈值可提高；降低必须有新的官方证据和 ADR。
- 何时重新评估：SQLite 官方发布新的数据完整性公告，或 Python 链接策略变化时。

## ADR-08：暂不引入自动更新

- 标题：自动安装更新延后，未来从 check-only 开始
- 状态：Deferred
- 上下文：当前尚未完成稳定发布渠道、签名密钥托管、回滚和分阶段发布流程。
- 必须满足的约束：更新包强签名；密钥轮换；失败回滚；灰度与渠道隔离；用户可理解的版本信息。
- 候选方案：立即静默更新；只检查更新；暂不提供。
- 方案比较：自动安装扩大供应链和可用性风险；check-only 可在渠道成熟后先验证元数据链路。
- 决定：本轮不安装 updater 插件，不把“缺少自动更新”列为当前缺陷。
- 决定理由：先完成可验证的安装产物和发布门禁，避免把未成熟发布链路接入客户端。
- 负面影响：已安装版本需要用户手动升级。
- 可逆性：高。
- 何时重新评估：签名、密钥托管、回滚演练和正式发布渠道全部就绪时。

## ADR-09：Sidecar 底层进程适配迁移到官方 Shell 插件

- 标题：使用官方 Shell 统一 Sidecar 解析、输出事件和退出观察
- 状态：Accepted / Implemented
- 上下文：Tauri 官方 `tauri-plugin-shell` 2.3 提供 `externalBin` 路径解析、stdout/stderr 事件、`CommandEvent::Terminated` 和 `CommandChild`。迁移实验最初使用的未跟踪 Frozen 二进制只输出 `{"port":...}`，缺少当前协议要求的 `protocolVersion/serverInfo/capabilities`，因此被 Host 正确拒绝；使用当前源码隔离构建的 Frozen 二进制后，插件事件路径在 Windows x64 正常完成 Ready、health、异常退出观察、自动重启和关闭清理。
- 必须满足的约束：保留 Supervisor 状态机、generation、一次性 Token、Ready/health 握手、崩溃强度、关闭竞态和 Windows process-tree 清理；不得让插件事件与手写轮询长期并存；不得向 WebView 暴露 shell spawn 权限。
- 候选方案：完整采用插件事件；继续全部手写；只采用插件路径解析并保留标准进程事件。
- 方案比较：完整插件事件删除最多重复基础设施并保持一个 Child 所有者；全部手写继续承担 externalBin 路径和 pipe/退出适配；部分采用会长期保留两套进程抽象。
- 决定：开发态与正式态均通过 `app.shell()` 构造命令；正式态只调用 `.sidecar("dbfox-engine")`。Supervisor 只持有 `CommandChild` adapter，并消费 `CommandEvent::Stdout/Stderr/Terminated`；删除 `sidecar_candidate_paths`、target 映射、手写 pipe reader 和 `std::process::Child::try_wait`。Windows 仅在停止时保留已验证的 `taskkill /T /F`，因为 PyInstaller one-file 具有 wrapper/inner 进程树。WebView 不授予任何 `shell:*` capability。
- 决定理由：最大限度复用 Tauri 官方跨平台实现，同时保留 DBFox 的生命周期、协议和安全策略；不引入第二套启动路径。
- 负面影响：Windows process-tree 清理仍有一个平台专用边界；macOS/Linux Frozen 行为仍需远程 Runner 验证。
- 可逆性：高；adapter 隔离插件类型，Supervisor 的领域状态不依赖插件细节。
- 何时重新评估：官方插件能够明确终止完整 PyInstaller 进程树，或 macOS/Linux Frozen characterization 发现平台差异时。

## ADR-10：外部资源只通过 Rust 策略边界交给官方 Opener

- 标题：系统浏览器和诊断目录统一使用 `tauri-plugin-opener`
- 状态：Accepted / Implemented
- 上下文：数据库内容属于不可信输入；`window.open` 属于 WebView 新窗口机制，手写 `explorer/open/xdg-open` 又重复平台适配。正式 CSP 同时禁止任意 HTTPS 图片内联加载。
- 必须满足的约束：只响应直接用户操作；外部 URL 必须为绝对 HTTPS、包含主机且无 userinfo；Rust 必须重复校验；不得向 WebView 授予通用 `opener:*` 权限；不得通过放宽 CSP 或新增图片代理绕过边界。
- 候选方案：继续 `window.open`；WebView 直接使用 opener Guest API；Rust 窄 command 调用官方 opener。
- 方案比较：前两项分别产生 WebView 导航歧义或扩大 capability；Rust command 能集中产品策略，同时复用官方跨平台打开实现。
- 决定：保留 `open_diagnostic_logs` 和 `open_external_https_url` 两个窄 command，内部调用官方 opener；远程图片单元格不再在 WebView 内联加载，只提供经过确认的系统浏览器操作。
- 决定理由：平台机制与产品安全策略分层明确，不需要 fallback、代理或第二套 URL 打开路径。
- 负面影响：不再提供任意数据库远程图片的应用内预览；浏览器开发模式不提供桌面 opener fallback。
- 可逆性：高；若未来需要预览，应先定义可信源、缓存隔离和内容安全合同。
- 何时重新评估：产品形成受管理的媒体源白名单或独立安全图片服务时。

## ADR-11：Sidecar 日志复用官方轮转，DBFox 保留脱敏所有权

- 标题：`tauri-plugin-log` 独占 Host/Sidecar 日志写入和轮转
- 状态：Accepted / Implemented
- 上下文：多个 `SidecarLog` 实例曾各自持有独立 mutex，却操作同一个文件，手动重启和监控线程可能并发轮转。
- 必须满足的约束：写入和轮转只有一个实现；Sidecar 日志与普通 Host 日志分文件；秘密在进入 logger 前完成脱敏；单条消息和文件大小有界；诊断包只收集官方 active/dated rotation 命名且二次脱敏。
- 候选方案：全局共享自写锁；继续每实例文件写入；现有日志插件的过滤 Target。
- 方案比较：共享锁仍需维护文件、命名和轮转协议；官方 Target 已提供同步、平台日志目录和 `KeepSome`，DBFox 只需保留领域事件格式。
- 决定：使用 `dbfox::sidecar` target 写入 `dbfox-sidecar.log`，`dbfox-host` 排除该 target；删除自写 OpenOptions、轮转和实例锁。
- 决定理由：消除并发事实来源，复用已存在依赖，不改变脱敏和诊断包安全策略。
- 负面影响：轮转文件改为带日期名称，诊断包发现逻辑必须与插件合同同步。
- 可逆性：高；事件 schema 与日志后端通过 target 隔离。
- 何时重新评估：需要结构化 tracing、远程日志汇聚或插件轮转合同发生破坏性变化时。

## 运维验收

- `cargo test --manifest-path desktop/src-tauri/Cargo.toml --lib`：Supervisor、crash-loop、关闭竞态、诊断 ZIP。
- `cargo clippy --manifest-path desktop/src-tauri/Cargo.toml --all-targets -- -D warnings`：官方插件适配和日志 target 必须无警告。
- `python -m pytest engine/tests/test_problem_details.py engine/tests/test_build_sidecar.py engine/tests/test_runtime_manifest.py`：错误协议和产物门禁。
- `npm test -- --run src/lib/api/__tests__/engineStartup.test.ts src/lib/diagnostics/__tests__/clientLog.test.ts src/lib/__tests__/externalNavigation.test.ts src/components/__tests__/ImageCell.test.tsx`：会话恢复、写请求不重放、循环日志和外部资源边界。
- 正式发布使用 `python scripts/verify_release_artifact.py --output reports/release-artifact-verification.json`；任何平台没有最终安装包、manifest、匹配 hash 或 SQLite 最低版本都失败。
