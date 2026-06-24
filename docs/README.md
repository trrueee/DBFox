# DBFox 文档体系

## 目录总览

```
docs/
├── designs/     功能设计与规范 —— "要做什么，怎么做，规范是什么"
├── plans/       实现计划       —— "分几步做，每一步产出什么"
└── qa/          测试与质量     —— "怎么测，测什么，质量标准"
```

---

## 每个目录的使用方式

### `designs/` — 功能设计与规范文档

**何时创建**：当开始一个新功能、重大重构、或制定核心工具与技术规范时。

**命名**：`YYYY-MM-DD-{主题}.md`

主题名要求：**动词 + 对象** 或 **组件/工具名**，说明"这是什么主体的设计或规范"。

| 好 | 差 |
|----|-----|
| `datasource-split.md` | `split-executor-and-datasource.md`（太长） |
| `db-tools-spec.md` | `db-tools-rules-and-definitions.md`（过冗余） |
| `zustand-migration.md` | `app-state.md`（没说做什么） |

**内容要求**：
- 背景与动机（为什么需要这个功能或规范）
- 方案设计（架构图、数据流、关键接口、规则定义）
- 关键决策点（为什么选 A 不选 B）
- 影响范围与风险边界

**生命周期**：创建 → review → merge → 对应 plan 执行（如适用）→ 长期保留作为历史记录与当前系统行为的单一事实来源。


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
1. 新功能/规范启动
   └─ 设计方案与规范 → designs/YYYY-MM-DD-{功能/规范名}.md

2. 设计完成（如涉及具体实施）
   └─ plans/YYYY-MM-DD-{功能/规范名}.md  （与 design 同名）

3. 质量规范与重构控制
   └─ qa/NN-{主题}.md（更新或新增）
```
