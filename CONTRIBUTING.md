# 参与 DBFox 开发

感谢你改进 DBFox。这个项目同时包含桌面 Runtime、Web UI、Python API、Agent Harness 和数据库工具链；小改动也可能跨越安全或状态边界。请在编码前先确认真实调用链，并让实现、测试和文档保持一致。

## 开始之前

1. 阅读 [`README.md`](README.md) 了解产品与支持范围。
2. 从 [`docs/README.md`](docs/README.md) 选择对应阅读路线。
3. 使用 [`docs/architecture/implementation-map.md`](docs/architecture/implementation-map.md) 定位权威实现与测试。
4. 检查项目、标准库、框架和官方组件是否已有成熟能力，再决定复用、最小适配或自研。
5. 修改文档前阅读 [`docs/documentation-style-guide.md`](docs/documentation-style-guide.md)，并复用 [`docs/glossary.md`](docs/glossary.md) 中的统一术语。

当前正式验证平台是 Windows x64。没有真实 Runner、构建产物和 smoke 证据时，不要声称 macOS 或 Linux 已通过。

## 开发环境

- Python 3.12
- Node.js 22.18 或更高版本
- Rust 1.95（桌面壳与 Rust 测试）
- Git

安装 Python 依赖：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --require-hashes -r requirements-dev.lock
```

安装前端依赖：

```powershell
Set-Location desktop
npm ci
Set-Location ..
```

使用锁文件和 `--require-hashes` 保持构建可复现。不要通过修改锁文件、关闭哈希或添加安装 fallback 绕过依赖问题。

## 启动

从仓库根目录启动 Python API 和前端开发服务器：

```powershell
.\dev.ps1
```

运行 Electron 桌面应用：

```powershell
Set-Location desktop
npm run electron:dev
```

Unix 开发脚本为 `./dev.sh`，但脚本存在不等同于 macOS/Linux 发布已经验证。

## 架构不变量

- **单一 Runtime 权威**：Rust 管理 Sidecar 生命周期、generation、endpoint 与短期 token；不要增加第二套启动或探活路径。
- **单一协议模型**：在真实系统边界做一次类型转换；不要堆叠 mapper、DTO、兼容表或双轨协议。
- **Provider-neutral Agent**：Turn、Completion、Tool 与错误语义不能依赖某一家模型提供商的可选字段。
- **SQL-first 工具链**：数据分析优先让数据库聚合、过滤和分页；SQL 必须走正式的校验、参数绑定、执行与结果制品链。
- **耐久事实在数据库**：会话、运行、事件、工具结果和制品由 Repository 持久化；UI 内存和 SSE 只是投影与传输。
- **秘密不进入业务合同**：凭据进入 OS vault；公开错误、日志、工具 Observation 和诊断包必须经过可信消息与脱敏边界。
- **非幂等不重放**：取消、断线和 generation 刷新不能让不确定结果的写操作被自动重复执行。

如果变更需要兼容层或 fallback，必须记录适用范围、删除条件、使用量观测和退出计划；否则优先修复根因。

## 质量检查

按改动范围运行最小充分的检查。提交前至少运行与你修改部分对应的命令。

### Python / Engine

```powershell
python -m pytest -q --tb=short
python -m pyflakes engine build_sidecar.py
python -m mypy engine build_sidecar.py
```

### Frontend / Desktop

```powershell
Set-Location desktop
npm run lint
npm run typecheck:test
npm test -- --maxWorkers=1
npm run build
npm run test:rust
```

### 工程合同

```powershell
python -m pytest engine/tests/test_engineering_contracts.py -q
git diff --check
```

高风险变更还应运行对应的集成、故障注入、Frozen Sidecar 或安装包验证。平台验证规则见 [`docs/quality/release-validation-matrix.md`](docs/quality/release-validation-matrix.md)。

## 变更要求

- 先建立基线和可复现证据，再修改生产源码。
- 修复权威路径，并为失败路径增加回归测试；不要只在 UI 或 Adapter 末端遮蔽问题。
- 保持提交独立、可测试、可回滚，不混入无关格式化或用户本地文件。
- 行为、架构、命令、配置或支持范围变化时，同步更新标记为“当前”的文档。
- 新依赖必须说明适配度、维护状态、安全、许可证、体积、锁定与退出成本。
- 实现非简单功能或通用能力（含前端组件、交互与素材选型）前，先按[技术调研、方案复用与架构克制](docs/quality/technical-investigation-and-reuse.md)完成调查并明确复用/自研决策；重要决策在 PR 描述中列出决策依据。
- 不降低鉴权、SQL、安全、capability、供应链或发布门禁来让测试通过。

## 提交前检查

```powershell
git status --short
git diff --check
git diff --stat
```

确认没有提交：

- `.env*`、API Key、Token、DSN 或带密码 URL；
- 本地 SQLite 数据库、缓存、日志和诊断包；
- MSI、NSIS、Sidecar 可执行文件或来源不明二进制；
- 临时测试脚本、截图草稿、IDE 或 Agent 私有工作目录；
- 与当前任务无关的用户改动。

提交信息应简洁说明意图，例如：

```text
fix: preserve provider-neutral completion semantics
docs: refine project onboarding and navigation
```

维护者提交和正式发布源提交必须使用已登记到 GitHub 账户的 SSH、GPG 或 S/MIME 密钥签名。普通贡献者建议签名；Release 工作流会拒绝 GitHub 未验证的源提交。不要改写已经公开的历史来补签，也不要共享私钥或将签名密钥放入仓库。正式产物的来源和校验合同见 [`AUTHORS.md`](AUTHORS.md)。

## 文档维护

- 当前设计写入 `docs/architecture/`，跨模块合同写入 `docs/specs/`，质量与发布证据写入 `docs/quality/`。
- 旧方案和完成后的阶段报告移动到 `docs/archive/` 并标明替代关系。
- 不创建 `final-v2`、`latest-new` 等重复事实来源；优先更新已有权威文档。
- 所有相对链接、命令、文件名和平台结论都必须在提交前核对。
- 文档状态只使用“当前”“已接受”“草案”“历史”；不要混用 `Current`、`Implemented` 或自定义状态。
- 中文说明优先使用通俗、统一的词；代码名和协议字段保留原文，并在首次出现时解释。

详细规则见[文档中心](docs/README.md)和[文档编写与维护规范](docs/documentation-style-guide.md)。

## Pull Request

PR 描述应包含：

- 问题与根因；
- 采用的设计，以及为何复用或不采用其他方案；
- 修改范围和明确非目标；
- 测试命令与实际结果；
- 平台覆盖与未验证项；
- 安全、兼容、迁移和回滚影响；
- 是否新增兼容层、fallback、双轨路径或新依赖。

合并前保持 CI 通过，并如实保留无法验证的风险。不要创建 tag、Release 或修改主分支来替代正常审查流程。
