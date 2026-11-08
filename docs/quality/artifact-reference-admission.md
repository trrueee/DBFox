# 工件引用入场合同修复

> 文档类型：质量证据
>
> 状态：当前
>
> 最后核验：2026-09-05
>
> 适用范围：Host Artifact Dock 的加入对话操作

Scene 红队留下的实际按钮形状包含 `object.kind="artifact"`。Director 接续执行时发现，该形状在 `ConversationInputReference` 解析时失败：ReferencedObject 是能力所有者的命名空间对象，而 `artifact` 不符合其既有 kind 合同。三项后续场景因此尚未到达 SessionInput admission；不能把此前浏览器点击成功理解为后端提交成功。

沿实际 `WorkspaceDock → ArtifactDockContent → Workbench reference → conversationStore.sendMessage` 核验，没有移除该字段的转换，真实提交会同样被拒绝。既有 `artifactId → artifact_id` 已能完整表达工件身份，因此直接在唯一按钮发送处移除重复的 object。保留 label 和 artifactId，不修改 SDK、生成 API、后端 schema、Artifact 可用性、跨 Session 或资源 authority，不增加 mapper 或回退分支。

扩展现有真实 WorkspaceDock 导航测试，分别在项目草稿和已有聊天中点击「加入对话上下文」，核对实际 Workbench store 引用并通过由后端合同生成的 Zod schema 解析。修复前两项明确失败（发现多余非法 object），修复后导航、Dock、ArtifactViewHost 和 ConversationStore 四文件 **68 passed，9.03秒**；`npm.cmd run typecheck:test` 通过。Director 是本次实现者，这些回归不替代停止中的独立红队。

该修复让引用符合入场合同。工件内容是否可供后续模型读取仍取决于同 Session、生产来源与消费者 exact refs；只附带工件 ID 不自动授予资源权限。独立 ActionRun 的工件不会因此跨 Session 自动导入。
