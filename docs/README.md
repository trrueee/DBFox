# DBFox 文档体系

## 目录总览

```
docs/
├── designs/     功能设计文档 —— "要做什么，怎么做"
├── plans/       实现计划     —— "分几步做，每一步产出什么"
├── superpowers/ 补充规格与计划 —— 由 superpowers 技能生成的 specs + plans
├── reviews/     审查报告     —— "有哪些问题，严重程度如何"
├── qa/          测试与质量   —— "怎么测，测什么，质量标准"
├── reports/     调研报告     —— "调研了什么，结论是什么"
└── reference/   长期参考     —— "一直有效的规范、经验、术语"
```

---

## 每个目录的使用方式

### `designs/` — 功能设计文档

**何时创建**：当开始一个新功能或重大重构，需要先设计再动手时。

**命名**：`YYYY-MM-DD-{功能名}.md`

功能名要求：**动词 + 对象**，说明"对什么做什么"。

| 好 | 差 |
|----|-----|
| `datasource-split.md` | `split-executor-and-datasource.md`（太长） |
| `zustand-migration.md` | `app-state.md`（没说做什么） |
| `agent-state-contract.md` | `agent-state-contract-and-ai-schema-linking.md`（and = 两个主题） |

**内容要求**：
- 问题描述（为什么需要这个功能）
- 设计方案（架构图、数据流、关键接口）
- 关键决策点（为什么选 A 不选 B）
- 影响范围（改哪些模块，哪些不变）
- 风险与边界

**生命周期**：创建 → review → merge → 对应 plan 执行 → 完成后不删除，作为历史记录


### `plans/` — 实现计划

**何时创建**：design 完成后，动手写代码之前。

**命名**：**与对应 design 完全同名**，靠目录区分。

```
designs/2026-06-17-datasource-split.md   ← 设计
plans/2026-06-17-datasource-split.md     ← 实现计划
```

**内容要求**：
- 拆解为独立可验证的步骤（Task）
- 每步有明确的产出物和验证方式
- 标注依赖关系
- 关联到对应 design

**生命周期**：创建 → 执行（逐个勾掉 task）→ 全部完成后标记完成


### `superpowers/` — 补充规格与计划

由 superpowers 技能自动生成的规格和计划文件，作为 `designs/` + `plans/` 的补充。

```
superpowers/
├── specs/    规格文档（与 designs/ 同等内容标准）
└── plans/    实现计划（与 plans/ 同等内容标准）
```

当 superpowers specs 与 designs 内容重叠时，以 designs 为准。完成后手工整理合并到标准目录。


### `reviews/` — 审查报告

**何时创建**：对代码库进行了系统性审查（架构审查、安全审查、代码质量审查）后。

**子目录**：

```
reviews/architecture/    ← 架构审查（16 篇）
reviews/codegraph/       ← CodeGraph 自动化审查
```

**命名**：`NN-{子系统或问题域}.md`

编号表示审查范围和阅读顺序，不表示优先级。

**内容要求**（每条发现）：
- 标题：简明扼要描述问题
- 严重程度：Critical / High / Medium / Low
- 现状：代码位置、具体问题
- 影响：会导致什么后果
- 建议修复方案

`00-index.md` 汇总所有发现，`99-*.md` 存放降级/移除的条目。

**生命周期**：创建 → 逐条修复或降级 → 完成后作为技术债清零记录保留


### `qa/` — 测试与质量规范

**何时创建**：定义测试策略、测试标准、质量门禁时。

**命名**：`NN-{主题}.md`，编号决定阅读顺序。

```
04-integration-test.md    ← 集成测试怎么写
05-defect-reports.md       ← 缺陷报告规范
06-whitebox-test.md        ← 白盒测试策略
07-blackbox-test.md        ← 黑盒测试策略
08-nonfunctional.md        ← 非功能需求
09-refactoring.md          ← 安全重构计划
10-frontend-ux-issues.md   ← 前端 UX 问题追踪
```

**生命周期**：创建 → review → merge → 随项目演进持续更新


### `reports/` — 调研报告

**何时创建**：进行了一次深度调研、技术选型分析、竞品对比等。

**命名**：`YYYY-MM-DD-{主题}.md`

**内容要求**：调研目的 → 方法 → 发现 → 结论 → 建议

**生命周期**：创建 → review → 结论明确后可作为设计输入


### `reference/` — 长期参考

**何时创建**：文档内容长期有效，不绑定特定版本或时间点。

| 适合放 | 不适合放 |
|--------|----------|
| 编码规范、命名约定 | 某个版本的功能说明 |
| 经验教训总结 | 一次性的 bug 分析 |
| 术语表、缩写表 | 已过时的设计文档 |
| 数据库工具规范 | 临时的会议记录 |

**命名**：`{主题}.md`，无日期前缀。

**生命周期**：创建 → 随项目演进持续更新，不删除


---

## 命名规范速查

| 规则 | 说明 |
|------|------|
| **全英文 kebab-case** | `datasource-split.md`，不用中文、空格、下划线 |
| **日期格式** | `YYYY-MM-DD-`，即创建日期 |
| **不重复后缀** | 目录已表达类型，文件名不再加 `-design` `-spec` `-report` |
| **design ↔ plan 同名** | 同名文件分别放 `designs/` 和 `plans/` |
| **一个文档一个主题** | 标题出现 "and" 通常是两个文档强行合并的信号 |

---

## 典型工作流

```
1. 新功能启动
   ├─ 需要调研？ → reports/YYYY-MM-DD-{调研主题}.md
   └─ 设计方案 → designs/YYYY-MM-DD-{功能名}.md

2. 设计完成
   └─ plans/YYYY-MM-DD-{功能名}.md  （与 design 同名）

3. 实现完成
   └─ 运行审查 → reviews/architecture/NN-{问题域}.md（如有发现）

4. 质量规范变更
   └─ qa/NN-{主题}.md（更新或新增）

5. 经验沉淀
   └─ reference/lessons-learned.md（持续追加）
```
