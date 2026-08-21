# DBFox 文档中心

> 文档类型：导航
>
> 状态：当前
>
> 最后核验：2026-08-12
>
> 适用范围：当前生产实现与后续合并版本

这里是 DBFox 技术文档的唯一导航入口。根目录 [`README.md`](../README.md) 面向第一次接触项目的读者；[`CONTRIBUTING.md`](../CONTRIBUTING.md) 面向准备修改代码的贡献者；本目录解释系统为何这样设计、代码在哪里实现，以及如何验证这些合同。

## 文档层级

| 层级 | 目录 | 内容 | 是否描述当前事实 |
| --- | --- | --- | --- |
| 产品入口 | [`../README.md`](../README.md) | 项目价值、能力、快速开始与平台边界 | 是 |
| 贡献指南 | [`../CONTRIBUTING.md`](../CONTRIBUTING.md) | 开发流程、变更约束、质量检查与提交要求 | 是 |
| 架构说明 | [`architecture/`](architecture/README.md) | 系统边界、运行时、前后端、数据、Agent、工具与记忆 | 是 |
| 实现指南 | [`backend/`](backend/README.md) | 按运行链解释 Python Engine、事务、失败路径、调试与扩展 | 是；不取代架构合同 |
| 规范参考 | [`specs/`](specs/README.md) | 用户可见行为、跨模块合同、状态和验收条件 | 是 |
| 质量与发布 | [`quality/`](quality/README.md) | 测试、供应链、发布合同与平台验证 | 是 |
| 历史档案 | [`archive/`](archive/README.md) | 旧方案、实施计划、审查记录和生成报告 | 否，仅供追溯 |
| 图片 | [`images/`](images/) | README 和文档引用的受控图片资源 | 仅资源 |
| 写作规范 | [`documentation-style-guide.md`](documentation-style-guide.md) | 分类、命名、页眉、中文表达和维护检查表 | 是 |
| 术语表 | [`glossary.md`](glossary.md) | 统一 Runtime、Agent、SQL、记忆和发布术语 | 是 |

## 推荐阅读路线

### 第一次了解 DBFox

1. [`../README.md`](../README.md)
2. [`architecture/system-overview.md`](architecture/system-overview.md)
3. [`architecture/backend-owner-guide.md`](architecture/backend-owner-guide.md)（重点了解后端时）
4. [`backend/README.md`](backend/README.md)（需要详细后端实现手册时）
5. [`architecture/implementation-map.md`](architecture/implementation-map.md)
6. [`quality/engineering-gates.md`](quality/engineering-gates.md)

### 修改桌面启动、Sidecar 或鉴权

1. [`architecture/runtime-foundation-decisions.md`](architecture/runtime-foundation-decisions.md)
2. [`architecture/system-overview.md`](architecture/system-overview.md)
3. [`architecture/error-boundary-contract.md`](architecture/error-boundary-contract.md)
4. [`quality/release-validation-matrix.md`](quality/release-validation-matrix.md)

### 修改 Agent、工具或上下文

1. [`architecture/agent-runtime.md`](architecture/agent-runtime.md)
2. [`architecture/agent-runtime-item-protocol.md`](architecture/agent-runtime-item-protocol.md)
3. [`architecture/agent-tool-context-memory-contract.md`](architecture/agent-tool-context-memory-contract.md)
4. [`architecture/agent-conversation-recall-contract.md`](architecture/agent-conversation-recall-contract.md)
5. [`specs/agent.md`](specs/agent.md)
6. [`quality/agent-evaluation-methodology.md`](quality/agent-evaluation-methodology.md)

### 修改 SQL、结果或数据源能力

1. [`architecture/data-sql-results.md`](architecture/data-sql-results.md)
2. [`specs/data-grid.md`](specs/data-grid.md)（修改表格呈现或值查看时）
3. [`architecture/backend.md`](architecture/backend.md)
4. [`architecture/implementation-map.md`](architecture/implementation-map.md)
5. [`quality/engineering-gates.md`](quality/engineering-gates.md)

### 修改前端工作区布局或右栏 Dock

1. [`architecture/workbench-shell-workspace-dock.md`](architecture/workbench-shell-workspace-dock.md)（已接受的目标 ADR）
2. [`dbfox-quiet-workbench-design.md`](dbfox-quiet-workbench-design.md)（Quiet Workbench 视觉规范与 merge gate）
3. [`architecture/workbench-shell-migration-guide.md`](architecture/workbench-shell-migration-guide.md)（组件复用、迁移顺序与删除条件）
4. [`architecture/frontend.md`](architecture/frontend.md)（当前迁移中实现）
5. [`dbfox-design-baseline.md`](dbfox-design-baseline.md)（当前设计基线）
6. [`dbfox-workspace-dock-design.md`](dbfox-workspace-dock-design.md)（历史交互草案，仅补充细节）
7. [`architecture/implementation-map.md`](architecture/implementation-map.md)

### 准备提交或发布

1. [`../CONTRIBUTING.md`](../CONTRIBUTING.md)
2. [`quality/engineering-gates.md`](quality/engineering-gates.md)
3. [`quality/technical-investigation-and-reuse.md`](quality/technical-investigation-and-reuse.md)
4. [`quality/supply-chain-security.md`](quality/supply-chain-security.md)
5. [`quality/release-validation-matrix.md`](quality/release-validation-matrix.md)
6. [`../AUTHORS.md`](../AUTHORS.md)（作者、署名义务和正式产物来源）

## 当前架构文档

| 文档 | 主要问题 |
| --- | --- |
| [`architecture/system-overview.md`](architecture/system-overview.md) | 系统由哪些进程组成，谁拥有状态，哪些是不变量？ |
| [`architecture/backend-owner-guide.md`](architecture/backend-owner-guide.md) | 不熟悉代码时，如何从真实入口和代码符号理解后端并安全修改？ |
| [`backend/README.md`](backend/README.md) | 如何按多卷手册逐层理解后端运行链、事务、失败路径、调试和扩展？ |
| [`architecture/implementation-map.md`](architecture/implementation-map.md) | 一项功能具体落在哪些代码符号、表和测试中？ |
| [`architecture/frontend.md`](architecture/frontend.md) | React 工作区、Transport、状态与交互边界如何划分？ |
| [`architecture/backend.md`](architecture/backend.md) | FastAPI、Service、Repository 与运行时怎样协作？ |
| [`architecture/data-sql-results.md`](architecture/data-sql-results.md) | SQL 如何校验、执行、分页、持久化并形成制品？ |
| [`architecture/agent-runtime.md`](architecture/agent-runtime.md) | Agent Turn 如何完成、取消、重试和恢复？ |
| [`architecture/agent-runtime-item-protocol.md`](architecture/agent-runtime-item-protocol.md) | Provider item、消息、工具调用和事件如何表达？ |
| [`architecture/agent-tool-context-memory-contract.md`](architecture/agent-tool-context-memory-contract.md) | 工具、上下文预算、记忆与数据边界如何协同？ |
| [`architecture/agent-conversation-recall-contract.md`](architecture/agent-conversation-recall-contract.md) | 历史会话如何检索、授权、注入和审计？ |
| [`architecture/error-boundary-contract.md`](architecture/error-boundary-contract.md) | 内部错误如何变成可信、可展示、可脱敏的公开错误？ |
| [`architecture/runtime-foundation-decisions.md`](architecture/runtime-foundation-decisions.md) | 已收敛的 Runtime、Token、Transport、SQLite 与发布决策是什么？ |
| [`architecture/desktop-release-lifecycle.md`](architecture/desktop-release-lifecycle.md) | 外观、窗口恢复、异常退出、代码签名与自动更新如何协作？ |

## 设计草案

以下文档描述计划中的设计，**不描述当前实现**，不能覆盖当前代码、测试或 [`dbfox-design-baseline.md`](dbfox-design-baseline.md)。

| 文档 | 主要问题 |
| --- | --- |
| [`dbfox-quiet-workbench-design.md`](dbfox-quiet-workbench-design.md) | Quiet Workbench 视觉架构与实现规范：Surface/Border/Radius/Shadow/Motion 合同、DLC Visual Contract、P0–P8 实施顺序与 merge gate 禁止清单。 |
| [`dbfox-workspace-dock-design.md`](dbfox-workspace-dock-design.md) | 历史交互草案；边界决策已被 [`architecture/workbench-shell-workspace-dock.md`](architecture/workbench-shell-workspace-dock.md) 取代，本文只保留交互与视觉细节。 |

## 文档优先级

当资料冲突时，按以下顺序判断：

1. 当前生产代码、迁移和自动化测试；
2. `docs/architecture/` 与 `docs/specs/` 中标记为“当前”的文档；
3. `docs/quality/` 中当前执行的工程与发布合同；
4. 根目录贡献与运行说明；
5. `docs/archive/` 中的历史材料。

历史文档不能覆盖当前实现。若历史设计重新生效，应先形成新的当前文档或架构决定记录（ADR），并同时更新实现和测试。

## 写作与维护规则

完整规则见[文档编写与维护规范](documentation-style-guide.md)，统一术语见[术语表](glossary.md)。以下是提交时必须遵守的最小要求：

- 文档先说明类型、状态、最后核验日期和适用范围，再描述设计。
- 当前事实使用现在时；计划、建议和未验证内容必须明确标记。
- 架构文档从职责与数据流写到具体 Symbol，不复制大段源码。
- 协议、状态枚举、安全边界和发布承诺必须能由测试或产物证据验证。
- 新设计优先更新现有权威文档；不要为同一主题创建第二份“最终版”。
- 已失效文档移动到 `archive/`，保留背景并指向替代文档，不静默删除决策历史。
- 文件名使用小写 kebab-case；图片放在 `images/`，避免散落二进制资源。
- 修改代码导致架构、合同、命令或支持范围变化时，文档必须在同一提交或紧随其后的独立文档提交中更新。

## 新增文档前检查

1. 现有文档是否已经覆盖该主题？
2. 内容是当前事实、规范、质量证据，还是历史材料？
3. 是否有真实实现、测试、官方资料或决策记录作为依据？
4. 是否会制造第二份事实来源或重复导航？
5. 是否需要同步更新根 README、实现地图或贡献指南？

如果不能确定归类，先在现有文档中增加小节；只有存在清晰、长期稳定的独立主题时才新增文件。
