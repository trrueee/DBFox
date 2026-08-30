# dbfox.story — 小说工作台 DLC

> 文档类型：架构说明（DLC 能力）
>
> 状态：草案（最小验证版）
>
> 最后核验：2026-08-30
>
> 适用范围：`dlcs/dbfox.story/`、故事世界数据、Agent 故事工具

一句话：一个让 AI 帮你设计虚构世界、并守住它不崩的小说工作台。

## 形态

Dock 内左右分栏：左侧复用宿主 `host.ui.Tree` 列出人物 / 场景 / 情节线；右侧是
关系画布，AI 通过工具在画布上"连线"。

## Agent 怎么工作

它不"画"。调用 `story_propose_relations` 工具输出结构化提案
`{from_name, to_name, kind, reason}`，前端渲染成连线，逐条进入待审队列。
连线三态：已确认（实线）、待确认（虚线）、已否决（淡出但保留——保留否决记录，
Agent 查询世界时永远看不到被否决的路径，因此不会重蹈）。

批量审阅面板支持一键接受全部或逐条微调；确认后一次性提交为**不可变修订**
（`revisions.commit`，修订行只追加不改写），供 Agent 查询比对。

## 三条铁律

1. **坐标是视图，关系是数据。** 节点坐标只存 localStorage（按项目键控），
   永不进入任何模型上下文或后端存储。
2. **布局前端算。** 默认 golden-angle 圆周布点 + 拖拽微调，绝不让 LLM 输出坐标。
3. **Authority 边界。** 工具查询（`story_graph_query`）只返回已确认事实；
   待审/已否决关系对 Agent 不可见。故事世界以 `dbfox.story.world` 资源形式
   参与 Run 授权（默认资源自动授权；按设定勾选进入 Run 的细粒度 control
   列入后续迭代）。

## Agent 工具面

| 工具 | 输入 | 行为 |
| --- | --- | --- |
| `story_graph_query` | `entity_kind?`、`name_contains?`、`world_id?` | 返回全部实体 + 已确认关系（含 kind 与 reason） |
| `story_propose_relations` | `relations[]`（from_name/to_name/kind/reason，≤32 条） | 创建待审边；未知实体名直接报错；与待审/已确认重复的提案被跳过 |
| `story_revisions` | — | 列出不可变修订历史（seq、说明、确认计数） |

## 为什么它是 DBFox 的

关系存在 SQLite 里可查询；每次确认批量是追加式不可变修订；一致性审查
（"第三章已知真相，第七章反应不应不知"）由 Agent 调用 `story_graph_query`
对照结构化事实完成——生成谁都能做，守住二十万字世界不崩只有结构化数据做得到。

## 最小验证版（当前实现）

三个角色 + 一张关系图 + 让 AI 写一章 → 偷偷改掉一条已确认设定 → 看 Agent
能否在写作前通过 `story_graph_query` 指出矛盾。这一步成立后，其余
（章节管理、时间线视图、冲突检测工具）都是横向扩展。
