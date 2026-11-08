# dbfox.story — 小说工作台 DLC

> 文档类型：架构说明（DLC 能力）
>
> 状态：当前
>
> 最后核验：2026-08-31
>
> 适用范围：`dlcs/dbfox.story/`、故事世界数据、Agent 故事工具

一句话：一个让 AI 帮你设计虚构世界、并守住它不崩的小说工作台。

## 工作台形态

Dock 内左右分栏，目录顶部可切换两种形态：

- 逻辑形态：左侧是人物、场景和情节线，右侧是关系画布、批量审阅与修订；
- 章节形态：左侧是阅读顺序目录，右侧是章节阅读器和就地编辑器。

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
| `story_graph_query` | `entity_kind?`、`name_contains?`、`world_id?` | 返回 `world_generation`、全部实体和已确认关系 |
| `story_propose_relations` | `relations[]`（from_name/to_name/kind/reason，≤32 条） | 创建待审边；未知实体名直接报错；与待审/已确认重复的提案被跳过 |
| `story_revisions` | — | 列出不可变修订历史（seq、说明、确认计数） |
| `story_upsert_entity` | `name`、`kind`、`summary` | 按名称创建或更新实体摘要 |
| `story_chapters_list` | `world_id?` | 按阅读顺序列章节 |
| `story_chapter_read` | `chapter_id` 或 `title` | 读取 Markdown 权威正文 |
| `story_write_chapter` | 完整正文 + `expected_world_generation`；改写时还需 `expected_chapter_sha256` | 新建或整章改写，追加 AI 版本历史；并发修改时拒绝覆盖 |
| `story_append_chapter` | 增量正文 + `expected_world_generation` + `expected_chapter_sha256` | 续写已有章节，不要求重发旧正文，仍生成完整版本快照；并发修改时拒绝覆盖 |

## 章节存储与一致性

当前章节正文的权威值是 DLC 私有 data path 下的 UTF-8 Markdown 文件；`chapters`
表只保存目录顺序、标题、相对路径和摘要，`chapter_versions` 保存每次作者或 AI
写入后的不可变全文快照。升级时，旧 `chapters.content` 会一次性写入 Markdown，
校验 SHA-256 后清空当前正文列，不保留可写双轨事实源。

Workbench 的 `chapters.list` 只返回有界目录元数据，选中章节后再通过 `chapters.read`
读取一章正文；Agent 的 `story_chapters_list` 复用同一个目录合同。长篇小说不会因打开
目录而把全部正文一次性复制进 Host 响应或前端内存。

章节改写和追加都使用正文 SHA-256 做乐观并发控制：调用方必须先读再写，陈旧写入
返回冲突而不是覆盖新内容。若用户用外部编辑器直接修改 Story 私有 Markdown，下一次
读取会在 SQLite 写锁内把该内容收编为 `author=recovery` 的不可变版本并更新目录摘要；
若当前文件意外丢失，则从最新不可变版本恢复。SQLite 负责串行化目录与版本元数据，
Markdown 仍是当前正文的唯一权威值。

Story 不直接读取 `dbfox.workspace` 的私有 resolver，也不复制 Workspace binding。
普通代码和独立 Markdown 项目由 Workspace 的统一文件工具编辑；Story 工作台章节
继续由 Story 自己拥有。跨 DLC 工作由 Agent 显式编排，避免隐藏授权和双向同步。

Agent 写章前必须先调用 `story_graph_query`，并把返回的 `world_generation` 交给写入
工具；设定在两次调用间变化时写入会失败。成功写入后，Completion Constraint 还要求
再次调用 `story_graph_query`，没有“写前快照 + 写后复核”的 Run 不能直接结束。

## 为什么它是 DBFox 的

关系存在 SQLite 里可查询；每次确认批量是追加式不可变修订；一致性审查
（"第三章已知真相，第七章反应不应不知"）由 Agent 调用 `story_graph_query`
对照结构化事实完成——生成谁都能做，守住二十万字世界不崩只有结构化数据做得到。

## 当前限制

完成约束能证明 Agent 在写前后读取了同一代已确认事实，但矛盾判断仍由模型完成；
系统不会用关键词规则假装理解叙事逻辑。阅读器已提供版本目录、正文并排对比和带
当前正文哈希校验的回退；当前差异视图是全文并排阅读，不做逐词语义 diff。
