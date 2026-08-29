# DBFox UI 设计与开发规范

> 文档类型：质量与开发规范
>
> 状态：当前
>
> 最后核验：2026-08-28
>
> 适用范围：Desktop Core UI、Agent Workspace、Workbench、Dock、Artifact Renderer 与内置 DLC 前端

本文定义 DBFox 在已完成第一轮市场驱动重构后的 UI 开发方式。目标是持续直接采用成熟、可核验的
设计和实现，删除较弱的重复实现，同时保持 Core/DLC、Runtime、状态和安全边界不被展示组件反向控制。

## 1. 总原则

UI 变更必须遵守以下顺序：

```text
确认产品目标和权威状态
        ↓
检查当前已采用组件是否直接覆盖
        ↓
针对真实缺口调查官方能力和成熟实现
        ↓
直接 ADOPT，或只在真实系统边界做最小 ADAPT
        ↓
替换旧实现并删除重复路径
        ↓
用生产 fixture 验证视觉、交互、错误和可访问性
```

“不计替换成本，只看最终效果”在本项目中的含义是：

- 不因为旧代码已经存在，就保留明显较弱的自研组件；
- 不因为迁移工作量大，就长期维持两套 UI、图表引擎或状态机；
- 选中成熟方案后，直接使用上游包、官方源码或经许可 vendoring 的真实实现；
- 一次性切换并删除旧路径，不建立无退出条件的兼容层。

它不表示忽略安全、许可证、可访问性、维护状态、离线运行、CSP、包体和 Runtime 边界。不能发布、
不能离线工作或要求接管 DBFox 权威状态的方案，不属于“效果更好”。

## 2. 当前事实源

已经完成选型的 UI 不重新采购。生产实现必须直接复用下表的权威能力：

| 变化轴 | 权威方案 | 禁止新增 |
| --- | --- | --- |
| 字体、字号、行高、默认颜色 | Fluent 2 tokens 和 `desktop/src/styles/tokens.css` | Feature 字体栈、在线字体、第二主题系统 |
| Button、Dialog、Tabs、Select、Toolbar、Feedback | shadcn + Radix UI | 同职责自研 primitives |
| Composer、Message、Sources、Approval | Prompt Kit + AI Elements | 第二套 Chat/Message Runtime |
| ToolGroup、Plan、Question | Agent Elements | 把 RunItem 映射成第三方 AI SDK 消息模型 |
| Tree | Zag Tree View | DLC 自建 Tree 状态机 |
| DataGrid | TanStack Table + Virtual | 第二表格引擎、结果数据副本 |
| Work Surface 与 Dock | react-resizable-panels + Radix Tabs | 自研 resize、第二布局 Store |
| 图标 | Lucide | emoji 或混合图标体系 |

具体来源、许可证和本地落点见[组件采用报告](../ui/component-adoption-report.md)。字体与颜色只以
[字体与颜色审计](../ui/typography-color-audit.md)和生产 token 为准。

## 3. 何时需要新调查

只有出现当前依赖和生产组件没有覆盖的真实能力时，才启动专项调查，例如：

- 新的声明式可视化语法和图形运行时；
- 专业音频波形、乐谱或媒体编辑器；
- 当前平台没有的复杂空间交互；
- 新文件格式的成熟查看器；
- 新的无障碍交互原语。

调查深度与风险相匹配。一个成熟依赖已直接提供的局部能力不需要重新比较整个市场；新的图形
运行时、编辑器或状态机则必须调查官方文档、源码、维护状态、安全、许可证和退出成本。

## 4. 采用和替换规则

### 4.1 ADOPT

满足合同的成熟实现应直接采用。优先顺序为：

1. 项目已安装且已验证的能力；
2. 浏览器、React、Electron 或现有框架的官方能力；
3. 官方维护的成熟包；
4. 许可证明确、源码可审查的 registry 组件；
5. 在成熟实现上的最小适配。

### 4.2 ADAPT

只允许在真实边界适配，例如：

- 将上游组件接到 DBFox 的权威 props 和事件；
- 将上游视觉值替换为现有 Fluent/DBFox semantic tokens；
- 在 DLC Host 与 Renderer sandbox 的正式边界注入能力；
- 移除上游强制依赖的第二套 Runtime 或主题。

不得以 ADAPT 为名重新手写同类组件，也不得复制上游状态到新的 ViewModel。

### 4.3 REPLACE

成熟方案明显更好时，应完成单向替换：

- 生产调用方切换到新实现；
- 测试使用真实生产组件；
- 删除旧组件、旧 CSS、旧状态和旧 fallback；
- 更新 provenance、锁文件和采用报告；
- 不让新旧方案无限期共存。

### 4.4 KEEP

只有现有实现本身已经直接建立在成熟能力上，或它承载 DBFox 独有的 Runtime、数据、安全和状态合同
时才 KEEP。KEEP 不是“迁移成本高”的同义词。

## 5. Core 与 DLC 视觉所有权

Core owns the experience；DLC owns the capability。

产品形态是统一的可插拔 Agent Workbench：左侧资源/导航、中央 Conversation/inline 和右侧 Dock
共同服务于一次 Agent 工作过程。它们共享 canonical resource/Artifact identity，但不共享 UI payload
副本；用户选择只有通过类型化 reference 明确附加后才进入下一轮模型上下文。

Core 拥有：

- App Shell、Main Surface 和 Dock 容器；
- DLC View/Renderer/Command contribution 的 Host registry、激活/卸载和通用 chrome；
- Fluent typography、semantic colors、spacing 和 focus grammar；
- Button、Dialog、Tabs、Toolbar、Toast、Empty、Loading、Error；
- Agent Timeline、Composer、Artifact frame 和通用 Renderer context；
- 全局响应式、缩放、高对比度和 reduced-motion 合同。

DLC 拥有：

- 领域 Tool、Artifact payload、Representation 和领域 Renderer；
- 左侧资源项、inline 表达和 Dock 专业视图所需的领域 contribution；
- SQL editor、数据库层级、图形、波形、乐谱等领域内容；
- 领域 loading/error 的原因与恢复动作；
- `inline` 与 `workspace` 中领域信息的取舍。

DLC 不得自带第二套全局字体、Button、Tabs、Toast、Dialog chrome、主题或 Dock layout。

## 6. Artifact 与可视化 UI

Artifact Renderer 必须直接消费权威 Artifact envelope 或按 Artifact ID 读取 Representation，不得保存
payload 镜像。相同 Artifact 在不同 Surface 共享身份：

- `inline`：阅读优先、稳定高度、保留必要交互和“在 Dock 查看”；
- `workspace`：完整交互、来源、血缘、检查、导出和全屏；
- `fullscreen`：只在真实分析需求存在时提供，不创建新的 Artifact 内容副本。

可视化新增能力采用成熟 Vega-Lite/Vega 图形运行时；KPI、标题、说明、Toolbar、错误和表格继续直接
使用现有 React、Fluent、Radix 和 TanStack 基线。不得为图表重新建立字体、颜色、布局 Store 或 DataGrid。

生产 CSP 禁止 inline style element。`style-src-attr` 仅为经过版本固定和源码审计的 Vega Canvas/SVG
renderer 保留；这不是业务组件的通用许可。Host 与 DLC 业务 UI 继续使用共享 token、静态 class 或受控
CSSOM，不接受模型生成 CSS，也不得为新组件扩大该例外。

## 7. 交互和状态底线

- 所有键盘可执行动作必须有可见 focus；不能只依赖 hover。
- 颜色不能是状态或 series 的唯一编码；使用标签、线型、形状或图例补充。
- 超过约 300 ms 的等待显示稳定的 loading；失败提供原因和可执行恢复动作。
- 错误出现在受影响 Surface，使用权威 Problem Details，不创建第二错误事实源。
- 动画只表达状态变化，尊重 `prefers-reduced-motion`，不通过布局抖动制造反馈。
- 图表提供可访问摘要和数据表替代；tooltip/selection 必须能通过键盘或等价控件访问。
- 大型数据先在来源侧聚合、过滤或采样；重型 Renderer 延迟加载并在卸载时释放资源。
- Light、Dark、High Contrast、中文、英文、125%、150%、200% 和窄窗口均属于生产合同。

## 8. 依赖与来源记录

新增 UI 依赖必须记录：

- 上游项目、版本、源码和许可证；
- 维护状态与已知安全边界；
- 为什么现有能力不够；
- bundle、CSP、Electron sandbox 和离线影响；
- ADOPT/ADAPT 范围与本地落点；
- 旧实现删除条件和退出方式。

如果只需一个可分离、许可证允许的上游组件，应优先 vendoring 真实源码；如果核心能力需要持续升级和
安全修复，应使用正式依赖。不得复制整个项目形成私有长期分叉。

## 9. 验证要求

每项 UI 改动至少验证：

1. 权威状态直接进入组件，没有新 mapper 或镜像 Store；
2. idle、loading、empty、error、disabled、cancelled 和 long content；
3. 键盘、焦点恢复、ARIA 名称和 screen-reader summary；
4. Light/Dark/High Contrast、中文/英文和系统缩放；
5. 窄窗口、Dock 开合和 Renderer 卸载；
6. CSP、bundle 和依赖许可证；
7. 生产 fixture，而不是手写 A/B/C 外观替身。

Design Lab 用于真实生产组件的组合、回归和视觉比较。已经采用的组件不因新增功能重新进入采购投票。

## 10. 决策依据

本规范直接继承上一阶段的市场评审和采用结果。`ui-ux-pro-max` 只用于数据密度、无障碍、错误恢复、
响应式和性能核对；它推荐的 landing-page 结构、在线 Fira 字体和独立色板不适用于 local-first、
Windows/CJK、Fluent 2 基线，继续拒绝。

本规范替代历史的[UI 市场驱动重构任务记录](../archive/reviews/ui-market-driven-refactor-task.md)作为新增
UI 的工作方式。历史任务仍保留，用于追溯当时为什么进行广泛采购与替换。
