# DBFox UI 文档入口

> 文档类型：导航
>
> 状态：当前
>
> 最后核验：2026-08-28
>
> 适用范围：Desktop Core UI、Agent Workspace、Workbench、Dock 与内置 DLC 前端

DBFox 当前 UI 已完成市场驱动的组件调研与第一轮生产替换。新增 UI 不再重复执行整套组件市场
采购任务；开发者应直接复用已经采用的成熟组件，并只为项目中真实缺失的新能力进行专项调查。

## 当前权威

1. [产品与 UI 总合同](dbfox-master-product-ui-contract.md)：产品层级、Core/DLC 视觉所有权和整体体验。
2. [UI 设计与开发规范](quality/ui-design-and-development.md)：新增、替换和验证 UI 的当前工作方式。
3. [组件采用报告](ui/component-adoption-report.md)：已经进入生产的上游组件、许可证和本地落点。
4. [字体与颜色审计](ui/typography-color-audit.md)：Fluent 2 字体角色、语义颜色和唯一 token 边界。
5. [运行时状态清单](ui/ui-runtime-inventory.md)：产品必须呈现的 loading、error、disabled 和恢复状态。
6. [Design Lab 状态矩阵](ui/design-lab-state-matrix.md)：生产组件的主题、语言、缩放和状态验证范围。

## 当前采用基线

| 范围 | 当前方案 |
| --- | --- |
| 字体、字号、行高和默认颜色 | Fluent 2 tokens；Segoe UI/Cascadia/Bahnschrift 与离线 CJK fallback |
| Composer、Message、Sources、Approval | Prompt Kit、AI Elements |
| ToolGroup、Plan、Question | Agent Elements |
| 基础组件与反馈 | shadcn、Radix UI、Lucide |
| Tree | Zag Tree View |
| DataGrid 与虚拟化 | TanStack Table、TanStack Virtual |
| 声明式可视化 | Visualization DLC 内的 Vega-Lite、受限 Vega 与 CSP interpreter |
| Work Surface 与 Dock | react-resizable-panels、Radix Tabs |
| JSON 查看 | react-json-view-lite |

新增功能必须优先直接使用这些现有能力。不得为同一职责再创建一套 Button、Tabs、Tree、DataGrid、
Error、Typography、Theme、Dock layout 或 Agent UI runtime。

## 历史记录

上一阶段的完整任务书已归档为
[UI 市场驱动重构任务记录](archive/reviews/ui-market-driven-refactor-task.md)。它用于解释为什么进行过
广泛市场调查，不再是后续每项新增 UI 的执行流程。
