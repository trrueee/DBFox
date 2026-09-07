# DBFox Animation Studio

> 状态：当前；作者候选，独立验收另行记录。

本地 Timeline / Keyframe Studio。AnimationDocument 统一保存轨道、关键帧、混合缓动曲线、片段、标记和时序；人类与 Agent 共用增量事务。没有代码执行框、整份 JSON 编辑器或在线依赖。

打开项目资源中的 Animation Studio，创建动画，添加对象及目标属性轨道。时间线点击定位，拖动关键帧编辑时间；展开关键帧列表可用键盘选择。方向键移动1帧，Shift移动10帧，Delete删除，Ctrl+Z撤销。曲线可以拖拽 Bézier 手柄或修改数值。片段裁剪保留原关键帧，标记在播放跨越时提示。导出打开固定版本 Artifact，JSON保留完整曲线和来源身份。

时间单位为整数毫秒，时长最长一小时，播放0.1..4倍正向速度。单文档最多500轨道/20,000关键帧；每片段最多128轨道。改动必须带expected_version，冲突拒绝且不自动重放。绑定Scene对象必须由Agent经授权Scene Artifact读取公开表示，不能粘贴伪造Scene对象JSON。

架构、25项权威合同与当前Host项目清理接入缺口见 [animation-dlc.md](../../docs/architecture/animation-dlc.md)。

构建与验证（仓库根）：

```powershell
cd dlcs/dbfox.animation
npm ci
npm run build
npm run test:three
cd ../..
python -m pytest verification/tests/system/test_animation_dlc.py -q
python -m verification.bench.capabilities.dbfox_animation --output output/animation-bench-new
```

使用独立owner包中的 Three 0.185.1，MIT声明和可重建bundle指纹在licenses/。不导入其他DLC私有包，不修改Core/SDK。示例 `examples/fox-gesture.json` 是完整规范动画文档，可供检查或通过同样增量操作重建；本版不提供绕过增量验证的整份文档导入工具。
