# 狐狸神殿创作压力示例

> 文档类型：示例与验证说明
>
> 状态：当前
>
> 最后核验：2026-09-05
>
> 适用范围：Scene 正式工具、typed human edit 和不可变 Artifact 导出

可重复输入来自 [Scene CapabilityBench](../../../verification/bench/capabilities/dbfox_scene/README.md) 的 `fox-temple-stress`。没有提供整场景 replace 或私有 Store 写入脚本。

神殿由 63 个稳定命名主体节点构成：6 组、平台和祭坛、12 根柱子、6 级阶梯、5 个狐狸雕像部件、32 块屋瓦。随后正式工具加入主灯、补光和透视相机；材质为月石与铜。坐标遵循 Scene 的 Y 向上、米制与 local TRS 合同。

连续任务如下：

1. 创建月石和铜材质、主体、灯光和主相机，检查基准场景。
2. 加入供品和临时对象，再只删除临时对象。
3. 只旋转狐狸头部，保留其他稳定对象。
4. 将 12 根柱子移动到屋顶组的层级下，保持 local TRS。
5. 将主灯强度从 100 降到 80。
6. 对“两盏灯中的那盏”先检查并要求明确 ID，不写入；之后用新的正式用户输入澄清继续。
7. 指向不存在雕像的变换被拒绝，重新检查版本。
8. 人类通过 typed operation 抬高祭坛；Agent 再 inspect 后调整供品。
9. 暂时再次旋转狐狸头部，然后 undo 到该次 correction 之前，追加历史版本。
10. 调整铜材质粗糙度和颜色，检查并导出本次正式持久 Artifact。

scorer 对每次局部变换/重构比较前后 canonical 历史页，检测无关对象是否改变；用稳定 ID、版本、内容哈希、Invocation 计数证明增量修改。最终应有 67 个节点、2 个材质，主灯 80、狐狸头部 Y 旋转 0.12、铜 roughness 0.35。glTF/GLB 通过同一 Artifact 的注册 Representation 读取，再由包内官方 validator 校验。

2026-09-05 独立正式 RunLoop 执行通过：24 次工具调用、26 个模型回合，最终 v18、67 节点、2 材质，持久 Artifact `artifact_5ee1fb9bc3034b20b726a9996d2ec75f`。下载 [glTF 作品](../../../verification/bench/capabilities/dbfox_scene/evidence/scene-bench-report/fox-temple.gltf) 或 [GLB 作品](../../../verification/bench/capabilities/dbfox_scene/evidence/scene-bench-report/fox-temple.glb)；两者官方 Khronos 校验均为 0 errors/warnings/infos，[哈希及来源证据](../../../verification/bench/capabilities/dbfox_scene/evidence/scene-bench-report/export-evidence.json)固定本次 Artifact 版本。

这是脚本化模型边界下的运行机制与领域结果验证，不证明真实 LLM 自主创意能力。完整通过数量、浏览器证据与边界见 [独立质量记录](../../../docs/quality/scene-dlc-independent-verification.md)。
