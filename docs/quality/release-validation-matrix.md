# DBFox 发布验证矩阵

> 状态：当前发布合同
> 最后核验：2026-08-06

本矩阵是发布门禁，不是“理论支持”列表。定时 CI 与人工发布前检查必须在三个目标系统上执行相同的锁定依赖、Sidecar 和 Tauri 编译链。

门禁配置不等于平台已通过。每次候选版本必须绑定具体 commit、workflow/job、
产物 SHA-256 和 smoke 输出；缺少真实 Runner/产物时该平台只能标记“静态合同已审查、
未真实验证”。Windows 结果不得外推到 macOS/Linux。

| 能力 | Windows 11 / windows-2025 | macOS 14 / Apple Silicon runner | Ubuntu 24.04 |
|---|---:|---:|---:|
| Python hash lock 安装 | 必须 | 必须 | 必须 |
| Sidecar 平台命名与隐藏依赖测试 | 必须 | 必须 | 必须 |
| PyInstaller Engine Sidecar | 必须 | 必须 | 必须 |
| Frontend TypeScript/Vite build | 必须 | 必须 | 必须 |
| Tauri Rust compile (`--no-bundle`) | 必须 | 必须 | 必须 |
| Tauri GUI 启动与主流程 smoke | 发布候选 | 发布候选 | 发布候选 |
| OS 原生 Keyring 实机检查 | 发布候选 | 发布候选 | 发布候选 |
| 安装、覆盖升级、卸载 | 发布候选 | 发布候选 | 发布候选 |
| Sidecar crash / sleep-resume / 端口重占用 | 发布候选 | 发布候选 | 发布候选 |
| MySQL/PostgreSQL/SQLite 连接与取消 | 发布候选 | 发布候选 | 发布候选 |
| SSH、TLS 与证书路径 | 发布候选 | 发布候选 | 发布候选 |

## 自动门禁

`.github/workflows/ci.yml` 的 `release-platform-contract` 在每周定时任务和手工触发时运行三平台矩阵。任何平台失败都阻止标记发布候选。

生产 Sidecar 的解释器唯一来源为仓库根目录 `.sidecar-python-version`，构建依赖唯一
来源为 `requirements-build.lock`。Frozen smoke 必须从最终可执行文件验证鉴权、
Schema、只读查询、Result Artifact、耐久多 Run 和重启重载；runtime manifest schema 2
必须绑定解释器、锁哈希、关键包版本、SQLite provenance 和 Sidecar 哈希。

截至 2026-08-04 的本地证据仅覆盖 Windows x64；macOS/Linux 的结论必须以对应
远程 Runner 结果另行更新，当前文档不声称这两个平台已通过。

当前自动门禁尚未包含 Tauri GUI WebDriver。Rust 编译、Frozen Sidecar smoke 和前端
组件测试不能替代真实 WebView 启动证据；在经过独立依赖安全审查的 GUI 自动化落地前，
该项继续由发布候选人工证据覆盖，不得据此声称已自动验证。

供应链门禁由 `scripts/dependency_governance.py` 执行：

- Node 从提交的 `package-lock.json` 读取全部依赖与许可证；
- Python 从 hash lock 确定精确版本，并从已安装的锁定 distribution 读取许可证；
- Rust 从 `cargo metadata --locked` 读取 Cargo.lock 对应的完整依赖图；
- 三端分别生成 CycloneDX 1.5 清单，并拒绝未知许可证和没有可接受替代项的强 copyleft/受限许可证。

## 发布候选人工证据

发布负责人需要为三个系统分别保存：安装包哈希、签名验证、首次启动日志、升级前后元数据库版本、Keyring 状态、Sidecar 诊断包、数据库连接/取消结果。该证据属于发布记录，不写入 Agent Session/Event Log。
