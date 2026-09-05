# Comic DLC 的领域边界与实现前调查

> 文档类型：技术调查
>
> 状态：草案
>
> 最后核验：2026-09-06
>
> 适用范围：完整 Comic Lead 开始实现前的 Director 调查；不代表产品或独立门禁完成

Comic 的耐久作品应表达页、面板、镜头、角色在镜头中的位置、对白、字幕及视觉注释。角色标签与造型属于这一作品的视觉表达；人物事实、关系、世界设定继续由 Story 拥有。页预览和分镜视图必须编辑同一份内容，不能维护两套布局模型。

## 已核实的复用边界

当前 Story 的[注册入口](../../dlcs/dbfox.story/backend/contributions.py)提供 Project-scoped world/entity/relation/chapter operations、资源和工具；当前文件没有注册 Artifact Representation。其[合同](../../dlcs/dbfox.story/backend/contracts.py)包含人物/场景/情节实体及关系、章节内容与版本。历史 `e91c5748`、`2dc62653` 及当前工作树里的章节改动也表明这些事实归 Story。不得猜测一个尚未存在的 `story.snapshot.v1`，也不能从 Comic 导入 Story store 或读取其 SQLite。

因此，独立 Comic 创作不依赖 Story 安装。原生 Agent 可以在同时获准使用两个资源的生产 Run 中先读取 Story 工具观察，再用 Comic 公开工具编排镜头和对白；这不等于已经实现稳定跨 DLC Artifact 消费。未来需要自动跟踪或固定历史故事输入时，先在 Story 真正的公开边界提供可验证的固定表示，再以 Artifact producer 和 lineage 消费。当前不新增 Story 事实镜像、双向同步或假身份字段。

Scene/Voxel/Pixel 的正式 Runtime 模式已经证明：Library 负责创建入口，Document/World 是耐久资源，内部对象不是独立授权资源；同 Run 每个 invocation 通过既有 resolver 绑定实际版本。直接使用公开 SDK、Tool Runtime、SQLite 事务、不可变修订、精确请求回执和公开 Representation。不要引入通用创作状态机、第二条工具链或 JSON 文档存储包装层。新发现的 Voxel producer、head/parent、最终提交前取消问题应直接成为 Comic 的初始合同和故障用例。

## 画面与文本方案

已检查浏览器 SVG 的 text、foreignObject 以及 Konva Text/Canvas export。原生 SVG 具有对象 DOM、缩放和矢量输出；`text` 默认不换行，不能把它当成现成的完整对白排版器。foreignObject 可复用浏览器 HTML 排版，但必须实际验证独立 SVG、字体、裁剪与目标导出程序。不能仅在工作台预览成功就声称通用导出兼容。[SVG text](https://developer.mozilla.org/en-US/docs/Web/SVG/Reference/Element/text)、[foreignObject](https://developer.mozilla.org/en-US/docs/Web/SVG/Reference/Element/foreignObject)。

Konva 已提供 Text 的宽度、高度、padding、lineHeight、wrap 与 ellipsis，以及 Canvas 图像导出；可避免手写文本测量、命中和缩放，但会引入固定版本 vendor、Canvas 图层/事件清理、像素输出与 SVG 导出差异。其 `toDataURL`/`toImage` 只是渲染器能力，不是 DBFox 的耐久 Artifact 和授权链。[Konva Text](https://konvajs.org/api/Konva.Text.html)、[官方 React 导出](https://konvajs.org/docs/react/Canvas_Export.html)。

最终选择应以小型真实 Chromium 探针决定：中文与英文长对白、显式换行、emoji、缩放后拖动/resize、窄工作台、导出重开和字体一致性。优先使用浏览器或成熟库现成排版；不要新写一个通用 Unicode 换行器，也不要维护 Python/JS 两套字体测量算法。此处尚未选择或安装 Comic 新依赖；候选版本的包字节、维护状况、许可证、漏洞与退出成本须在冻结时记录。用户提供文本应作为纯文本，不能变成 SVG/XML/HTML/脚本/URL 的可执行入口。

## 25 项规范草案

| 问题 | 拟采用的明确边界；最终由完整 Comic 架构合同冻结 |
| --- | --- |
| 1. Resource | 每个 Host Project 的 Comic library，以及独立可编辑的 ComicProject document。 |
| 2. Object | Page、Panel、Shot、CharacterPlacement、SpeechBubble、Caption、VisualNote；稳定 ID 在文档内唯一。 |
| 3. Selection | 当前页、面板及内部对象的前端选择；绝不增加资源权限。 |
| 4. canonical | ComicProject schema 1：有序页面/面板、明确局部坐标、镜头与视觉对象；完整文档的唯一内容哈希。 |
| 5. SQLite | Project membership、当前 head、不可变完整修订与 parent、精确 invocation/request producer 回执；没有冗余故事事实库。 |
| 6. View state | 缩放、滚动、当前页、工具、拖动草稿、选中对象、页视图/分镜视图模式；不会驱动 RunLoop。 |
| 7. Context | 已授权资源 ID/version、作品摘要、页/面板总数、少量有界目录、近期合法 Artifact locator。 |
| 8. 禁止进入 Context | 全部页、全部对白、渲染字节、任意私有 Story 数据、SQL、文件路径、凭据。 |
| 9. Version | 原子批次真变更才产生 v+1；no-op 和失败不改变 head/hash/generation。 |
| 10. stale Invocation | frozen ref、resolved resource、expected_version 必须符合公开 Runtime 合同；错配零写入。 |
| 11. 人/Agent冲突 | 同一 CAS 操作入口；失败保留编辑草稿，明确刷新/对比/重新提交，不自动覆盖或重放。 |
| 12. 日志 | 仅用精确回执恢复一次真实 mutation 的结果；不以重放面板布局计算重建结果。 |
| 13. Undo | 恢复指定完整历史内容为新修订，仍经 CAS；可再撤销；历史无改写。 |
| 14. Diff | 固定两版本的页/对象增删与字段变化；长文本给窗口和完整 hash。 |
| 15. Crash | SQLite 原子提交；commit 前最后检查取消，commit 后精确 producer 回执；缺回执保持 unknown。 |
| 16. Deactivate | 移除全部贡献、DOM/Canvas、原生监听器、observer/timer、待处理加载；迟到写/导航不能跨 generation。 |
| 17. Project删除 | 每次操作与 resolver 验证实际 membership；不因 owner 数据残留重新授权。回收只能用真实支持的生命周期合同。 |
| 18. 大作品 | 固定版本页目录分页、按页加载、分镜可见窗口；不将所有页面常驻 DOM 或 Context。 |
| 19. 结果上限 | 明确总页/面板/对象/文本/历史预算、每批修改和每页输出上限；真实验证后冻结数值，不凭预估宣称支持。 |
| 20. Approval | 正常本地可撤销创作使用既有策略；不发外网、不执行脚本或无关文件操作。 |
| 21. Retry | 纯固定快照读取可安全重试；mutation 仅相同请求身份的精确回执核对。 |
| 22. 非幂等 | 创建、布局、文字/镜头/位置编辑、删除、undo；由 Tool Runtime 管策略与恢复。 |
| 23. Artifact | 真实 Tool/ActionRun 发布不可变 Comic revision locator，并由 Host 记录完整 producer/resource 证明。 |
| 24. Representation | 固定修订的页目录、完整单页、文本窗口与被验证的导出；禁止 request 参数替换 artifact 固定身份。 |
| 25. Composition | 从公开表示消费确切页/面板 ID、版本/hash和合法lineage；不引用 DOM 或私有 store，不提前建 Composition DLC。 |

## 实现与门禁

完整 Lead 仍需交付全部八种指定工具，加上必要的创建、inspect、编辑、删除、undo、diff、export；Page view、Storyboard view、Panel inspector、Dialogue editor 必须提供真实鼠标/键盘直接编辑。拖动需捕获开始版本、在结束时只提交一次，取消/切页/关闭后无晚到写；页面重排与对象局部坐标使用一份规范语义。

独立 Verification 和另行 Adversarial 不因这份调查而省略。十二类 capability bench、复杂成品及连续十类修改、大型多页作品、用户/Agent交替编辑、固定历史导出、真实 Electron 生命周期与公开 Resource/Artifact 负例仍为完整退出条件。本文只降低下一阶段的调查重复；最终模型、预算、依赖和排版/导出决定应写入唯一的 `comic-dlc.md`，届时本文保留调查出处及被替代关系。
