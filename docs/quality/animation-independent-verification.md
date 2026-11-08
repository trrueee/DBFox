# Animation 独立组合与边界验证

> 文档类型：质量验证
>
> 状态：当前
>
> 最后核验：2026-09-07
>
> 适用范围：Animation 作者候选与当前 Core 的确定性后端组合；不含独立原生 UI 验收。

## 结论与基线

真实签名 Scene→Animation 组合与新增独立红队通过。首次独立验证发现共享 Core 的取消探针竞态；作者源头修复 `ec4a4d7a` 在独立树接入为 `5aeaa418` 后，原 HTTP 取消断言保持不变，后端集合 30 项全部通过。该问题在本次验证范围内关闭；未通过 Animation 私查 Core 或放宽断言规避。独立原生 UI 和全部验收仍另行记录。

独立树 `codex/animation-verification` 从 Core `d4c98a6b` 创建。作者 `1aa66a3c5e0644ee619ed529c113291dac19090c` 挑入为 `177c96ea`；作者工程修复 `57087c4bc776067750bae317ad2d35ab5ae4c0f8` 挑入为 `c4e3da2a`。独立验证员未自行修改产品、Core 或 SDK；随后仅精确挑入上述作者 Core 修复。建树时根的 39 个真实 dirty baseline 文件逐字节复制并校验；未覆盖根或作者工作树。

Windows Git checkout 将已有 Music/Visualization 前端文件及新 Three bundle 转换成 CRLF。逐字节检查确认只有换行差异后，恢复根既有文件和作者 Three bundle 的原始字节；没有改写第三方 GLSL。Three bundle 为 259493 bytes，SHA256 `f16f7be89d6c67e82f1f6ed53fba6265d258d0ba79d4827d9143da4fadbb33ca`，与作者 provenance 一致。组合在恢复精确 bundle 后再次通过。

## 架构审查

Animation 的 Document、SQLite、稳定 ID、版本、receipt、undo/diff、曲线和轨道约束留在 DLC。工具与注册的 Workbench operation 调用同一 owner 事务；后端只从公开 `dbfox_dlc_api` 取得 Host 合同。Scene 组合调用 `artifact()` 与 `read_artifact_representation()`，没有 Scene 私有导入、跨 owner store 读取或第二执行循环。固定 Scene 身份和 TRS 保存为 Animation target 的来源快照；编辑 Animation 不会修改 Scene。

Three 0.185.1 与构建用 esbuild 0.28.2 由 DLC 本地 lock 固定。MIT 声明、包 integrity 和 bundle provenance 随 owner 保存。Three 仅求值可丢弃的播放对象；固定 JSON 保存完整关键帧与曲线，避免将 Three 序列化投影当成耐久模型。本轮复用了作者现有 5 个真实 Three 数值测试；没有把 Node 求值速度当作 GPU 或浏览器渲染性能证据。

## 生产组合

[独立组合测试](../../verification/tests/system/test_scene_animation_composition.py) 安装完整签名 Scene 和 Animation 包，创建已迁移元数据库，通过 Project discovery 授权、Session admission/lease、原生产 RunLoop、原 OpenAI Responses adapter、Dispatcher 和 Artifact Repository 执行。仅外部模型 HTTP 使用 `httpx.MockTransport`；测试没有替换 owner 工具、Representation 或手写 Invocation 权限。

10 次工具调用、11 次 HTTP 请求：创建 Scene → 创建稳定 fox 对象 → 创建 Animation → 绑定固定 Scene Artifact v2 → inspect 目标 → 创建 X 轨道 → 添加两帧 → 删除 Scene 活对象 → 修改 Animation 末帧 → 导出。使用默认 32768 prompt 上限，实测最大估算 20433；模型名仅在测试 admission 中为 `gpt-5.4`，未改用户模型设置、未调用付费端点。

独立核对包括：

- Scene object ID、精确版本 2、content hash、Artifact ID 和 TRS `[3,2,1]` 在 Animation 固定目标中完整一致。
- 轨道绑定实际 target ID；v4 末帧时间 4000，v5 为 4001。固定 JSON 的实际 UTF-8 SHA256 等于 Artifact payload。
- 删除 Scene 活对象后，旧 Scene 表示仍能作为固定来源；当前 Scene objects_page 为空，旧 Animation 轨道字节不变。
- 停用 Scene 后，Animation 的旧、新固定导出仍分别逐字节一致。
- bind Invocation 只有准确 Animation document resource；所有 Invocation digest 匹配实际安装 owner 包。没有扩大 Invocation 权限来通过组合。

上述结论证明领域事实的真实消费和持久关联。它不证明真实模型的工具选择质量、三维 Scene 播放、独立 Electron UI 或全 20 DLC 同时工作的容量。

## 新增独立红队

[独立红队测试](../../verification/tests/system/test_animation_independent_redteam.py) 使用完整签名安装、注册 operation 和生产 RunLoop。SQLite 只读计数用于证明拒绝后没有残留 revision/receipt；不直接写 owner 数据库。

| 路径 | 结果 |
| --- | --- |
| 同 Project 准确 selector / 跨 Project selector 与 operation | 前者按当前 Core 合同绑定准确文档，后者拒绝；Input refs 不是排他 ACL，不能将合法 Project 内选择误报越权 |
| 模型 HTTP 期间 Human CAS 修改、未来版本 inspect | 人类写入保留，陈旧模型写和超前版本读取拒绝，无额外 receipt |
| 部分合法批次夹带 foreign track、同轨同 tick 碰撞 | 整体拒绝，无部分数据和 receipt |
| 本地 target_create 伪造 Scene source | 在类型边界 rejected，无 owner 写入 |
| 并发 Workbench CAS、相同 request 的重启恢复、不同请求复用 ID | 一个提交者；重启重复请求恢复原 receipt；不同请求拒绝 |
| 删除 Animation、停用/重启、篡改固定 Artifact 的 hash/project/version | 旧固定关键帧 JSON 保持；篡改表示拒绝 |
| 同 Project 不同 Session 与跨 Project 的 Scene Artifact | 当前 Session 无权读取的来源拒绝绑定，Animation 不变 |
| 模型响应到达前已持久取消 | 首次揭示负缓存竞态；作者 Core 修复后原断言通过，无 owner revision/receipt 增长 |

独立测试初轮修正了测试端的状态值（rejected 与 failed）、request_id 空格和 Project 名称唯一性，以及对 Input refs 的错误排他假设。没有为这些测试错误改产品。首次验证中全部新增路径曾单独通过，但整组重跑再次出现取消残留写入，因此当时未将单次通过报告为取消安全。后续源头修复与独立复验见下节。

## 取消竞态：修复前证据与独立关闭

失败用例为 `test_cancel_during_model_http_prevents_owner_write`。在 HTTP MockTransport 准备返回 function_call 前，通过正式 `RunRepository.request_cancel()` 并提交元数据库。之后仍可能看到：Run 状态 `cancelled`、没有输出 Artifact，但 Animation 的 revisions 从 4 到 5、receipts 从 4 到 5。不是模拟 owner 写，也不是取消前已开始的长工具。

调用链证据：`engine/agent/control.py` 的 `RunControl.is_cancel_requested()` 缓存 false，默认探测间隔 0.1 秒。Animation `store.mutate()` 在事务前与 commit 前调用公开取消探针，但两次可能仍处于该缓存窗口。原生产执行链随后 terminalize 为 cancelled，无法回滚另一个已提交的 owner SQLite 事务。

在作者 19 + 独立组合 1 + 独立红队 10 的最终集合中，结果 **29 passed、1 failed（36.89s）**；取消路径已在两轮集合重现，单独运行会随耗时通过。这份修复前证据保留用于解释根因；没有增加等待 100ms、放宽断言或让 Animation 私查元数据。

作者随后提交 [共享取消修复](durable-cancellation-probe-fix.md) `ec4a4d7a3b93a87637e47a2487446533da1a9710`。唯一生产修改在 `RunControl.is_cancel_requested()`：每次尚未取消时调用既有耐久 probe，仅保留已观察到的 true。独立检查确认租约检查仍优先，deadline、等待审批/澄清、provider retry 等待节奏、终止结算和 owner commit 职责均未改变。没有新增 SDK、轮询线程、provider 分支、映射层或跨 owner 写入。

独立复验结果：

- 原作者 19 + 真实签名组合 1 + 独立红队 10：**30 passed，43.12s**。原 HTTP 取消测试未改，没有时间等待或断言豁免；取消后 owner 的完整计数保持。组合仍为 10 调用、11 HTTP、峰值 20433/32768。
- Core RunControl、取消 terminalizer、Session repository/coordinator、Tool Invocation repository、native tool search 以及 Tool Runtime 的必要相关集合：**70 passed，9.17s**。包括冻结同一 monotonic 值的 checkpoint / boolean probe 两个反例、取消等待审批/澄清、租约接替和中断恢复。
- 工程合同 **45 passed，3.38s**；改动 Core 文件及反例 pyflakes 通过。原有 vendor 换行基线未被覆盖。
- 独立额外从 Git 读取旧 RunControl 到隔离内存模块，在同一 monotonic 值上再次证明 False→持久 True 仍返回 False；没有改工作树旧/新代码。当前版本同时观察到 lease loss 与 cancel 时仍优先抛出 RunLeaseLost。

每次负结果现在产生原有的短只读数据库查询；该额外成本未经吞吐量基准量化。取消仍为协作检查，本次消除了人为 100ms 盲区，不声称取消提交与最后一次检查之后的外部副作用具备跨库原子撤销能力。此准确边界不影响本轮已复现缺陷的关闭。

## 支持范围与后续验收

当前 `engine/api/projects.py` 只提供项目 list/resources/create；没有项目删除 API，公开 `BackendExtensionHost` 也没有项目删除 lifecycle callback。本域 `delete_project` 的原子级联清理已有作者测试，但没有自动调用方。原要求中的“Project 删除时如何处理 state”应回答这个实际支持范围与未来 Host 接入责任；不能宣称自动清理完成，也不能捏造现有删除按钮导致的泄漏事故。本轮不新增 callback 或跨界清理机制。

上一文档操作 notice 在切换文档后短暂残留，属于作者已报告的 UI 提示问题；未把它判定为规范文档或领域事实丢失。独立原生 UI、实际生产打包/CSP、发布门禁、真实模型创作质量由后续角色验证。

## 复现与工程门禁

从独立 worktree 根运行，使用项目已安装 Python：

```powershell
python -m pytest verification/tests/system/test_animation_dlc.py verification/tests/system/test_scene_animation_composition.py verification/tests/system/test_animation_independent_redteam.py -q --tb=short
node --test verification/tests/animation/playback.test.mjs
python -m pytest verification/tests/system/test_engineering_contracts.py -q --tb=short
python -m pyflakes verification/tests/system/test_scene_animation_composition.py verification/tests/system/test_animation_independent_redteam.py
```

作者测试首次基线 19 passed（4.51s）；Three 5 passed。工程初轮发现作者测试放在 DLC、报告页眉与证据文件名合同共 3 项失败，作者 `57087c4b` 修复后独立 **45 passed（3.83s）**，新测试路径的 Three 5 passed。既有 Visualization bundle 的换行差异另行恢复，不将环境误差计入产品修复。本轮未重跑全仓或 UI 测试；仅接入作者上述 Core 修复，独立验证员没有自行编写生产修复、升级依赖、发布或调用 paid API。
