# Voxel 确定性 CapabilityBench

> 文档类型：验证指南
>
> 状态：当前
>
> 最后核验：2026-09-05
>
> 适用范围：`capability.dbfox-voxel.scripted`，正式签名 DLC 与生产 RunLoop

本 suite 由 Program Director 编写；Director 曾修改 Voxel 的观察投影、前端导航与严格 schema，因此本报告是实现者侧验证，仍需后续独立验证员检查评分逻辑并执行真实桌面流程，不能称为独立审查。

从仓库根执行：

```powershell
D:/Project/DBFox/.venv/Scripts/python.exe -m pytest verification/tests/bench/test_voxel_bench.py -q --tb=short
D:/Project/DBFox/.venv/Scripts/python.exe -m verification.bench run capability.dbfox-voxel.scripted --output D:/Project/DBFox-worktrees/creative-program/voxel-report
```

输出目录必须尚不存在。支持框架既有 case 过滤和重复运行；领域入口为 `python -m verification.bench.capabilities.dbfox_voxel --output <新目录>`。没有新增通用执行引擎、共享领域模型或第三方依赖。runtime fixture 参考已存在的 Scene suite，使用既有签名包安装、迁移、Runtime snapshot、ScriptedProvider 与 reporting；Voxel 专属案例、chunk 局部性评分及世界导出只在本目录。

14 个案例涵盖简单创建、局部增量、多阶段几何、非法输入恢复、先 inspect 再编辑、stale、no-op、歧义不改、128³大型世界、有界 context、人修改后 Agent 编辑、明确不改、整世界替换拒绝，以及64³赛博朋克狐狸神社的十类持续变化。

模型脚本的 `$world_id`、`$version` 和 `$步骤.字段` 仅取真正交付模型的 `function_call_output`。Human step 调用注册的 typed project operation，结果只记作验证证据，后续 Agent 必须再 inspect。歧义以明确回答结束当前 Run；只有 fixture 模拟用户补充说明后才接续 Run，普通增量修改不会每步另开 Run。

Scorer 通过注册 `worlds.get/chunks` 读取不可变修订，检验持久 Run/Invocation/Observation/Artifact 的身份、版本、调用顺序与预算，并逐变化 cell 验证其仍在目标 layer/区域内；不调用领域几何函数重算期望结果。明确坐标、数量和对象属性来自 case 独立断言。Context 不含 cells/chunks，输出不随世界体积膨胀。非法 schema 调用在 Tool admission 阶段拒绝，因此 attempt_count=0；实际执行的调用为1。两者都不得自动重放。

压力作品从正式 Artifact 的注册 manifest/chunks Representation 导出 `fox-shrine.snapshot.json`，并记录 SHA-256、页数和固定版本。它是公开表示的重组证据，不新增领域文件格式。报告不包含私有 SQLite、Token 或凭据。实际脚本化策略不能证明真实 LLM 的独立艺术创作或自然语言理解；浏览器交互、生命周期和最终红队另列门禁。
