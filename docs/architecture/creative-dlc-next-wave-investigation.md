# Creative DLC 第二批技术调查入口

> 文档类型：技术调查
>
> 状态：草案
>
> 最后核验：2026-09-06
>
> 适用范围：Game、Comic、CAD、Animation 的独立Domain Architect启动材料

Scene通过独立审查及联合验证后，四个隔离工作树与完整Lead模板已经准备。本文记录Director已查到的成熟方案和真实部署约束，尚未冻结领域合同或批准具体依赖；每位Architect仍须核对项目已有实现、版本、许可、官方能力、历史决定，再交付可实施方案。

## Game

Phaser提供Arcade物理世界、固定时间步和seeded随机生成器；可调查其作为局部模拟内核的适配度。需要验证明确步数的playtest、暂停/重置、碰撞和事件日志是否能由同一领域规则产生，而不是另写测试用模拟器。[Arcade World](https://docs.phaser.io/api-documentation/class/physics-arcade-world)、[Phaser数学与随机数](https://docs.phaser.io/phaser/concepts/math)。

Phaser的HEADLESS模式仍是浏览器Game生命周期的一部分，不能据其名称声称Frozen Python Sidecar可直接运行。候选需证明关Dock后Agent仍可playtest，模型只看有界观察，并保留取消、超时与迟到结果隔离；Shader的现有machine operation方案可作为公开合同调查对象，不能偷用其私有状态。暂不承诺跨平台逐位确定性，也未选择第二套物理算法。[Game API](https://docs.phaser.io/api-documentation/class/game)。

补充的[Game 实现前合同调查](game-dlc-preflight.md)记录25项领域边界和固定步骤风险。官方 npm registry 当前返回4.2.1，本机镜像仍返回4.0.0；最终版本必须从官方固定元数据和源码核验，不能照浮动文档或镜像直接冻结。

## Comic

[Comic领域与文字排版调查](comic-dlc-preflight.md)记录25项边界草案及当前Story尚未注册固定Representation的源码事实；最终渲染/导出方案仍须真实Chromium验证。

Comic只拥有页面、镜头、角色放置、对白和视觉注释；Story继续拥有世界事实。先评估原生SVG/Canvas和Konva在面板布局、选择、缩放、文字编辑与导出的差异；Konva已有Canvas导出能力，但这不替代DBFox的耐久Artifact与固定表示。[Konva导出](https://konvajs.org/docs/react/Canvas_Export.html)。

需在实现前冻结故事输入的稳定Representation；没有输入能力时应允许独立创作，不复制Story的角色事实库。页数和面板规模必须通过分页、可见页渲染及有界Context验证。

## CAD

[CAD部署与规范模型调查](cad-dlc-preflight.md)补充真实Chrome因果探针：当前CSP拒绝最小8-byte WASM模块；流式加载另需application/wasm，现有DLC资产返回octet-stream。没有修改Host策略、资产预算或安装产品内核。

JSCAD提供几何布尔和拉伸/旋转等成熟建模操作；其单位由应用约定，不能把输出网格当作canonical参数树。已查文档尚不足以证明它覆盖通用草图约束或任意BRep倒角，因此不能据基本布尔成功宣称CAD全部能力实现。[JSCAD布尔](https://openjscad.xyz/docs/module-modeling_booleans.html)、[建模基础](https://openjscad.xyz/docs/tutorial-02_modelingBasics.html)。

Replicad提供OpenCascade.js上的建模接口，包括fillet和STEP相关API。它依赖WASM；应分别核对JS接口、实际内核、约束求解能力及可发布的构建，而不是使用开发机原生OCP。[库集成](https://replicad.xyz/docs/use-as-a-library)、[形状修改](https://replicad.xyz/docs/tutorial-overview/modifications/)。

本机从发布者npm元数据读取 `replicad@1.1.0` 的license为MIT、解包5,862,747 bytes；`replicad-opencascadejs@1.1.0` 的license为LGPL-2.1-only、解包48,853,341 bytes。`npm pack --dry-run --json`列出的 `replicad_multi.wasm` 为22,481,415 bytes，`replicad_single.wasm` 为22,980,267 bytes，均超过当前DLC单文件20MiB合同。只查看元数据，未安装或改变共享锁文件。许可结论须在最终固定包的许可证文件及上游源码中复核，不能沿用搜索摘要的笼统描述。[发布内核包](https://www.npmjs.com/package/replicad-opencascadejs)。

上游提供按所需绑定定制构建以减少WASM体积，这是可调查的退出路径；尚未构建合格产物。不能静默提高平台配额或分片规避单文件限制。还需实际测试生产Electron的CSP/WASM装载及取消、内存、导出预算。[OpenCascade定制构建](https://ocjs.org/docs/app-dev-workflow/custom-builds)、[体积说明](https://ocjs.org/docs/getting-started/file-size)。

验收仍为78mm×10mm手机、65°倾角、充电槽的可打印支架，以及宽度82mm时参数重算。约束、尺寸和特征树必须驱动重算；不接受改名后的静态STL。

## Animation

可调查Three的AnimationClip、KeyframeTrack与Mixer作为派生播放引擎，轨道/关键帧/曲线/片段仍由Animation自己的规范文档拥有。现有Scene固定Three版本需与被采用API逐项核对，不能把当前在线文档里的新插值选项假设成已固定版本支持。[KeyframeTrack](https://threejs.org/docs/pages/KeyframeTrack.html)。

先独立完成时间线、曲线编辑、播放、Marker和千级关键帧预算。Scene的对象身份和固定版本通过正式表示消费；Scene↔Animation是否需要自有联合状态留到真实八秒镜头任务验证，不能把Timeline提前抽进Core。

## 所有下一批能力共用的边界

继续直接复用公开SDK、已有Tool Runtime、SQLite事务、Artifact/Representation和Bench框架。文档、对象、选择、显示状态与工件身份保持区分；大型创作、十类修改、用户与Agent混合操作和独立对抗门禁均不缩减。重复的领域操作或渲染代码先留在DLC，四项稳定后的Pattern Auditor再按证据决定是否提取。
