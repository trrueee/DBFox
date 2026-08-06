# DBFox 文档中心

> 状态：当前文档导航
> 最后整理：2026-08-06

这里是 DBFox 文档的唯一入口。文档采用“当前事实与历史证据分离”的结构，并借鉴 Diátaxis 对解释、操作、参考的区分，以及 C4/arc42 的自顶向下架构视角；项目不会为了套模板而复制第二份事实源。

## 目录结构

```text
docs/
├─ architecture/   当前系统设计、运行视图、实现地图、协议与 ADR
├─ specs/          当前产品行为和验收规范
├─ quality/        CI、依赖、发布门禁和候选版本证据
├─ archive/        已完成、已取代或仅绑定旧基线的历史材料
└─ images/         README 和文档资源
```

旧 `designs/`、`plans/`、`reviews/` 和工具生成材料已经归入 `archive/`。它们不会被删除或机械改写，因为仍有考古价值；但不得再作为当前实现依据。

## 从哪里开始

### 了解产品和系统

1. [根 README](../README.md)：产品能力、支持平台、开发和构建入口。
2. [架构导航](./architecture/README.md)：按系统、容器、组件和运行管线逐层阅读。
3. [系统总览](./architecture/system-overview.md)：目标、约束、部署拓扑和核心不变量。
4. [实现地图](./architecture/implementation-map.md)：从入口到状态、副作用、持久化和用户反馈。

### 开发或修改功能

1. 阅读对应的 `architecture/` 专题，确定唯一所有者和边界。
2. 阅读 [Agent 规范](./specs/agent.md) 或其他适用规范。
3. 使用 [工程质量门禁](./quality/engineering-gates.md) 选择验证命令。
4. 涉及正式产物时，再检查 [发布验证矩阵](./quality/release-validation-matrix.md)。

### 调查历史决定

从[历史归档](./archive/README.md)进入。归档文档中的旧目录、协议、库和测试结果只对原基线有效。

## 事实优先级

发生冲突时按以下顺序判断：

1. 当前源码、数据库迁移、OpenAPI、Tauri/Cargo/npm/Python 锁文件和 CI 配置；
2. 绑定当前 commit、平台和正式产物的可复现测试证据；
3. `architecture/` 当前事实和已实施 ADR；
4. `specs/` 当前产品合同；
5. `quality/` 中明确限定范围的验证结果；
6. `archive/` 历史材料。

Windows 验收不能证明 macOS/Linux 已通过，单元测试也不能替代 Frozen Sidecar、安装包、签名、公证或真实 GUI 验收。

## 文档类型和写法

| 类型 | 回答的问题 | 放置位置 | 更新规则 |
| --- | --- | --- | --- |
| 系统解释 | 为什么这样设计、有哪些约束 | `architecture/` | 生产合同变化时同步 |
| 技术参考 | 模块、状态机、协议、文件入口 | `architecture/` | 与类型、迁移和协议测试同步 |
| 产品规范 | 用户可见行为和验收条件 | `specs/` | 产品语义变化时同步 |
| 操作指南 | 如何开发、构建、验证 | 根 README、Desktop README、`quality/` | 命令或平台合同变化时同步 |
| 决策记录 | 采用什么方案、为什么 | `architecture/*-decisions.md` | 决定改变时追加或标记 superseded |
| 历史证据 | 当时的设计、计划、评审和报告 | `archive/` | 不追赶当前源码，只补状态和替代链接 |

## 命名与状态

- 当前文档使用稳定的语义名，例如 `system-overview.md`、`implementation-map.md`、`agent-runtime.md`。
- 历史材料保留日期前缀和原主题，避免丢失时间上下文。
- 当前文档在标题后注明 `状态` 和 `最后核验`；验证报告还必须注明 commit、平台、产物和命令。
- 允许的状态：`当前事实`、`当前规范`、`已接受决策`、`草案`、`历史归档`、`已取代`。
- 文件名只表达一个主题，不添加 `final`、`new`、`latest`、`v2-final` 等失去时间语义的后缀。

## 维护规则

生产合同变化时，同一提交优先同步：

1. 对应源码类型、迁移、OpenAPI 或配置；
2. 契约和回归测试；
3. 对应架构专题或 ADR；
4. 根 README/分类 README 的入口；
5. 发布矩阵中的适用范围。

不要新增重复 README、字段映射表或兼容说明来掩盖上下游合同不一致。应修正唯一事实源，在真实边界只做一次必要转换，并更新指向它的文档入口。
