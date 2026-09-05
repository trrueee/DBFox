# Animation 时间、曲线与引擎复用调查

> 文档类型：技术调查
>
> 状态：草案
>
> 最后核验：2026-09-06
>
> 适用范围：`dbfox.animation` Lead 启动材料；尚未实施产品

原始范围为完整Timeline/Keyframe Studio：AnimationDocument拥有Tracks、Keyframes、Curves、Clips、Markers和Timing，支持track_create/keyframe_add/keyframe_move/easing_set/clip_create/clip_trim/timing_modify。时间线、曲线编辑、播放和Marker必须可由人类直接编辑。此调查不代替实现、千级关键帧UI、12类bench、十类修改或独立门禁。

## 项目内与上游调查

现有Scene固定Three0.185.1和MIT许可；Animation可调查同版本标准动画类，但不能导入Scene私有renderer或把Scene包中的树摇bundle当作公开模块。Scene的公开document表示和glTF导出保留固定revision/contentHash，glTF节点extras.dbfoxId保留owner对象身份。可以经正式授权Artifact表示建立单向显示对象绑定；不能用可重复的显示名称作为跨DLC身份，也不能把普通Scene→Animation编排提前改成联合事实库。

官方[AnimationMixer](https://threejs.org/docs/pages/AnimationMixer.html)、[KeyframeTrack](https://threejs.org/docs/pages/KeyframeTrack.html)、[PropertyBinding](https://threejs.org/docs/pages/PropertyBinding.html)是候选能力。Director另外检查本机既有固定0.185.1包的KeyframeTrack/BezierInterpolant实际源码；KeyframeTrack.js的SHA-256为`3cddf8febcf9fd8d84283731972347a6146143a7ddb3f1372053e9d655b57b1a`，版本中确有InterpolateBezier。没有安装新依赖或修改共享锁。本次仅读取现有第三方包执行Node探针，不构成产品对另一DLC私有路径的依赖。

## 固定版本实际探针

使用真实NumberKeyframeTrack、AnimationClip、AnimationMixer、LoopOnce和Object3D，1001个关键帧覆盖0..8秒，标量值为3×time。禁止用自写插值器代替引擎。探针在原包的公开API上得到：

| 项目 | 结果与含义 |
| --- | --- |
| 显式seek到0/2/4/6/8/0秒 | 值为0/6/12/18/24/0，端点后可以回到起点 |
| 1001 keys、10000次循环seek | 此Node标量探针2.78毫秒；没有DOM/GPU/多轨/曲线UI，不能当千轨或实际工作台性能 |
| timeScale=0时setTime(4) | 得到0；setTime内部仍受timeScale影响 |
| timeScale=1时setTime(4) | 得到12；暂停UI应控制自身播放调度，并明确如何执行时间跳转 |
| LoopOnce+clampWhenFinished到末尾 | action会paused；初次探针未解除该状态，后续结果为0。明确设置action.paused=false再seek后上表通过；这属于API生命周期假设纠正 |
| 带自定义控制点的Bézier中点 | 原track为0.125，clone后为0.5；clone未复制settings，原生插值器在缺tangent时退回linear |
| NumberKeyframeTrack.toJSON(curve) | 仅name/times/values/interpolation/type，没有inTangents/outTangents |
| stopAllAction+uncacheRoot | existingAction返回null；未在此CPU探针验证GL或DOM释放 |

Bézier输入times=[0,1]、values=[0,1]、inTangents=[0,0,0.75,0]、outTangents=[0.25,0,1,1]；控制点为绝对(time,value)坐标。后续不能将原生clone/toJSON结果当作完整曲线的耐久备份。临时复现脚本在本工作树output/animation-preflight.mjs，未提交或纳入DLC。真实Chromium/CSP、已安装签名包、Workbench和曲线数值压力验收仍待完成。

## 给独立Lead的实现约束

规范时间单位、帧率与时间上限必须先冻结，明确duplicate time、相邻key、clip起止端点、trim后的端点取值、负速/循环、Marker重复触发和duration改变语义。曲线及控制点属于唯一AnimationDocument；Three track/mixer是由其重建的派生对象。不要通过Two-way sync、clone补丁或另存一份可写Three JSON修补事实不一致。

复用标准离散/线性/球面或Bézier插值前，实际测试目标值类型、曲线控制点单调性、极端斜率、数值有限性和重复seek；不因为库暴露某个枚举就承诺所有track类型支持。现有原生曲线能力优先于自写通用插值器；严格规范模型仍须拒绝库validate未覆盖的非法输入。

模型只能给稳定Object id及白名单属性（例如translation/rotation/scale等最终领域合同）；禁止任意PropertyBinding字符串访问对象属性。显示侧从规范identity及属性进行一次绑定，缺失或源版本变化显式拒绝。固定导出必须保留曲线控制点、clips和markers，并逐值验证reload/trim/clone语义，不只截图看起来相似。

Authority、SQLite CAS、receipt/undo、Context分页、Artifact producer、公开Representation和DLC生命周期继续复用Host现有边界。时间线、曲线求值、播放调度与显示缓存留在Animation owner；不进入Core。独立Lead仍须完成全部25项权威问答及真实需求规模验证，最终依赖与合同尚未冻结。
