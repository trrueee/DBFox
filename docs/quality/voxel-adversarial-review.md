# Voxel 独立对抗审查

> 文档类型：质量证据
>
> 状态：当前
>
> 最后核验：2026-09-05

本阶段在独立 Verification 提交 `6467337c` 结束后，由 Director 明确授予独立 Adversarial Reviewer 角色。审查者未参与 Voxel 产品实现；本阶段新增攻击、测试和证据，产品修复均交 Director。结论：下面已执行的对抗门禁通过，没有遗留已确认产品缺陷；集成决定属于 Director。本报告不以原来的 36 项故障测试或 14 案例作者 suite 代替新增对抗。

最终产品候选 `25b1e76e`，包含前一轮修复 `61002688`；真实冷重签包 digest 为 `98e87d0bf2851212f0820e741c56947d5241b712590433bb6527fa67bf866d99`。共享 Host 为 stdout drain `735ad284` 和 Tree 重开 `fc8d407a`。最终工作树中的 Voxel 产品文件没有验证员改动。

## 新发现及闭环

故障注入只作用于任务独占 SQLite、正式调用的响应或明确提交点。数据库变形说明本地耐久完整性问题，不主张已存在远程攻击者取得写库能力。下面产品反例保留原拒绝、零写入和精确恢复断言；完整索引见 [发现记录](../../verification/bench/capabilities/dbfox_voxel/evidence/adversarial-findings.json)。

| 严重度 / 发现 | 原始反例 | Director 修复和独立复验 |
| --- | --- | --- |
| P2 / 派生计数被当作真实内容 | 八格世界仅将 chunk 的 nonzero_count 改为 9，blob/hash/fingerprint 不变；get/list 两条拒绝断言均失败 | `61002688` 在 `_snapshot` 发布摘要前复用 `_raw` 的有界解压、哈希、真实计数、palette 和边界校验；原两条通过 |
| P1 / no-op 冒领另一调用的有效修订 | 保留原 no-op request/base/payload_hash，将 result/outcome 换成其他真实调用的 v3；重试错误声称 changed=true | `_receipt` 要求该修订唯一 producer 的 project/origin/request 与自身一致；历史 create/no-op/undo 在后续 delete 后仍能精确恢复，不运行几何 |
| P2 / 前端发布不完整或被替换的世界 | 原 6 条中 4 失败：少一块的末页、缺失 delta tombstone、字节换色但 hash 未变、跨页重复坐标 | 使用官方 WebCrypto 验证 chunk，跨页去重，最终块数/非空数和完整世界 fingerprint 校验；另加同计数换色并更新 chunk hash、坐标重排、元数据改写、有效最终页迟到取消，全部通过 |
| P1 / 创建在提交前取消仍提交 | 真实 ToolExecutor 在 receipt 已写而 commit 未执行时取消，释放后返回可成功恢复的 create | `25b1e76e` 在 create 的最终 commit 前调用既有 check_cancel；create/undo 各提交前后取消四例通过，原 fill 的 timeout/cancel 四例回归通过 |
| P2 / 私有 Representation 错误代码泄漏 | 真实历史 Artifact 接收另一个世界的真实分页 cursor，抛 INVALID_CURSOR 后违反公开异常 catalog，转成 ValueError | 在实际公开表示边界使用 INVALID_REQUEST / FORBIDDEN / SOURCE_CHANGED / SOURCE_UNAVAILABLE；游标及四种来源故障保持公开类型和安全状态码 |
| P2 / 合法几何掩盖坏 parent | v2 的 parent 改为自身 2、缺失 999 或 NULL，当前读取均错误成功 | `_snapshot` 验证 v1 parent=NULL、后续 parent=v-1 且存在；三原断言通过 |
| P2 / 当前 head 回退或悬空 | v2 存在，head 回退为有效 v1 时错误成功；head=999 时误报 WORLD_NOT_FOUND | 当前读取检查真实最新修订和 head；两例拒绝且显式完整 v1/v2 历史仍可读取 |

代码权威点是 [store.py](../../dlcs/dbfox.voxel/backend/store.py)、[representation.py](../../dlcs/dbfox.voxel/backend/representation.py) 和 [world-data.js](../../dlcs/dbfox.voxel/frontend/world-data.js)。没有更改历史内容哈希、schema 或迁移，没有重放几何来恢复结果，没有新增第二份世界模型或错误 catalog。

## 新对抗覆盖

[后端新增 55 项](../../verification/tests/system/test_voxel_adversarial.py) 每例安装真实签名完整包，通过当前 public operations、真实注册表、ToolRuntime/ToolExecutor 或生产 RunLoop 执行。几何与摘要期望由验证侧独立计算；仅模型 Responses 和故障边界受控。

| 类别 | 新执行证据 |
| --- | --- |
| Project / owner / selection | 外 Project 无法授权、选择或删除原世界，显式旧 ref 不能替代当前 membership，错误 owner context 和命名空间拒绝；未选择不隐式授权 |
| 三种版本边界 | 冻结 ref / 实际 resource / expected_version 三种错配均失败且四表不变；四个同 base 并发写仅一个成功，三个明确重新读取后各自保留区域，总 v5/32 cells/5 receipts |
| Artifact 来源 | 新建 → 填 slab → 导出是真实三次 RunLoop 调用；缺失 producer、错误工具/turn、失败 producer、外部 refs、自循环及悬空 source 均被正式 available_artifact 拒绝 |
| 明确 lineage / 历史围栏 | 同 Run 的来源不能隐式借权；明确且有效 derived_from 可借权，supports 不可。相同版本跨 Run 可读；新 admission 的版本变化后拒绝旧 ref，原同 Run 成果仍可读 |
| 固定分页 / 删除 | 历史 v2 首页面读取后删当前世界，后续四块仍与固定公开历史逐字节一致；外世界 cursor、请求改 world/version/path/URL/limit 不能改固定身份 |
| 取消 / crash / 回执 | create、undo 各真实执行器提交前后取消，另四个独立 OS 子进程在同样边界 os._exit(73)；提交前四表不变，提交后精确 receipt，SQLite quick_check/foreign_key_check 正常 |
| 深层坏数据 | 尾随压缩数据、4 MiB 解压炸弹、有效 fingerprint 下的未定义 palette 或非空 padding、未知 document schema 均拒绝；parent/head/派生计数及 producer 篡改另有原始反例 |
| 配额 / 大输入 / 输出 | create/no-op/undo 达历史配额均全表不变且历史可读；256³ 全区域超过候选上限时零变更，仍可有界读取；禁止外部路径、URL 和跨世界附加入口 |
| 前端迟到与失效 | 新 [分页攻击](../../desktop/src/features/dlc/__tests__/dbfoxVoxelAdversarial.test.ts) 10 项，另在 [原 fixture](../../desktop/src/features/dlc/__tests__/dbfoxVoxelFixture.test.ts) 添加 scope→deactivate→register 的迟到写/导出两项；旧 26 项仍保留包括 missing Host method、读取失败禁写、零重放和真实原生监听器断言 |

源码检查未发现 owner 导入 engine/private API，`engine` 与非测试 `desktop/src` 没有 Voxel 领域分支；manifest permissions 为空。数据文件与表示由既有 owner store、SDK Resource/Artifact 边界处理，前端外发仅使用 Host operations/representations 和本地 Blob 下载。验证侧没有引入新依赖、通用执行器或镜像业务模型。

## 冷重签真实 Electron

真实 Main、Preload、EngineSupervisor、Electron 43.4.1、React Host 与完整签名 DLC；Vite 提供 renderer。以下不是 WebGL fixture、安装程序或真实 LLM 智能验收。

[实际桌面证据](../../verification/bench/capabilities/dbfox_voxel/evidence/adversarial-electron.json) 保留了原共享 Tree 反例：关闭 Interactive tab 后 aria-selected 仍为 true，原地再次点击同一 leaf 可重新打开 v12，没有清引用或 reload 来绕过重开。600 次经过真实 Host 的只读 HTTP 全 200，3.237 秒完成，仍 v12。后续 [冷启动重放](../../verification/bench/capabilities/dbfox_voxel/evidence/adversarial-electron-replay.json) 将读取身份直接取自公开响应，600 次 3.239 秒；600 是本次边界压力样本，不是无限持续服务保证。迟到的真实 chunk 响应跨到空 Project 后没有创建旧 studio，返回原项目仍 v12。

新完整性检查后的 [大世界证据](../../verification/bench/capabilities/dbfox_voxel/evidence/adversarial-large.json)：64³/v38/23,386 cells/60 chunks，4 页、416 ms、约 93.35 MB JS heap、475 DOM；128³/v2/96,776 cells/296 chunks，19 页、2,010 ms、约 258.85 MB JS heap、454 DOM。128³ 明示 60,000 表面实例上限，crop 得到 64 个表面格；560px 页面 scrollWidth=560，已人工查看三张截图。数值是单机一次实测；没有以此声称性能改善、完整渲染超过上限或覆盖最大 8192 块。

深校验会在每次固定快照读取重验 live chunks；分页读取也承担此成本。最大世界最坏每次需检查 8192×4096 字节，当前没有缓存。本次 64³/128³ 未出现不可用，但最大布局和持续多世界负载仍不在本证据范围。

[新历史下载](../../verification/bench/capabilities/dbfox_voxel/evidence/adversarial-history-download.json) 在当前 v12 时经正式 Representation 重读 v8；manifest 和四块 source_version/fingerprint 一致，历史仅只读 3D，没有可编辑 slice。正常按钮产生真实 Electron DownloadItem 34,256 bytes。保存路径由任务专用原生 will-download.setSavePath 控制，未自动操作原生保存对话框，也没有 renderer 文件系统替代。独立 [磁盘审计](../../verification/bench/capabilities/dbfox_voxel/evidence/adversarial-durable-audit.json) 核对 manifest、全部 chunk、各 chunk SHA 和 1,135 cells；文件 SHA256 仍为 `d1f322665556500a6888ea38a28ee1f44e2abc82aab7639da425a7cc3e59f954`，与上一阶段逐字节一致。当前 v12 的人类 Gold 与三个 Agent 哨兵格均保留。

[Control-held 原生证据](../../verification/bench/capabilities/dbfox_voxel/evidence/adversarial-control-held.json) 使用 CDP 检查实际监听器：canvas 14→0、document 原 owner keydown/keyup→0，detached 且 contextLost=true，之后 3.5 秒无请求。Host tooltip 自身新增监听器另列，未将其误作 Voxel 或从结果中抹去。[历史视图停用与重启](../../verification/bench/capabilities/dbfox_voxel/evidence/adversarial-lifecycle.json) 再按住 Control 卸载历史 GPU：监听器为空、上下文释放；正式停用/重启 generation1→2 后 styles/canvas/tree 全 0，启用/重启到 generation3 后仅一份样式、原世界仍 v12。

固定 Three 上游补丁再次从官方 0.185.1 tarball 重建，SHA-512 integrity、精确单点源替换、esbuild0.28.2 和 bundle SHA 均校验；输出 749,587 bytes，SHA256 `4019cf00891df54884c4d14981c787f36e47b125590241402a5c9b1759351929`，无产品 diff。检查了 [构建脚本](../../desktop/scripts/build-voxel-vendor.mjs) 与 [provenance](../../dlcs/dbfox.voxel/frontend/vendor/provenance.json) 中原始/补丁源码 SHA、MIT、owner 和“上游修复后移除且两项原生监听器回归仍通过”的退出条件。补丁维护项仍存在，不宣称上游已修复。

两轮 Electron 均通过公开 window.close 正常退出；[首轮](../../verification/bench/capabilities/dbfox_voxel/evidence/adversarial-process-cleanup.json) 与 [末轮](../../verification/bench/capabilities/dbfox_voxel/evidence/adversarial-replay-cleanup.json) 的实际子进程和 5181/19227 监听全部消失，未强杀用户进程。原验证 SQLite、包、密钥、profile 和日志留在外部任务目录，不提交。

## 验证结果与限制

52 条新后端与 36 条原独立回归合跑 **88 passed / 124.63s**；随后新增三种冻结资源错配 **3 passed / 5.68s**。因此本阶段新增后端总数为 55，原 36 并未改名计入新攻击。前端 **38 passed / 4.71s**（原26 + 新10分页 + 新2代际交叉），typecheck、pyflakes、完整 build 通过；整仓 lint **0 errors / 5 原有 warnings**。Director 另报作者47项通过24.17s；该数字单列，不冒充本阶段独立测试。

旧 timeout fixture 在并发负载下 0.35 秒可能早于 after_commit 注入点而终止；Director 原回归 82 pass/1 fail 和独立原样单例 1 pass/1.48s 均记录。验证侧将总预算改为 2 秒，仍由真实 executor deadline 终止，必须先进入目标点、只一次调用、提交前回滚/提交后精确恢复，不解除任何关键断言。新增冻结错配测试首次错误期待 output=None；核对 Runtime 的公开失败 envelope 后改为严格 failed/TOOL_INPUT_ERROR/frozen-message 且没有 world 成功字段，该三次原始失败属于验证适配问题。

旧前端 fixture 原用假 hash 和不一致计数，现由 Node createHash 按独立 canonical 合同计算真实字节 SHA 与完整 fingerprint，交互断言保持。磁盘 audit 新增安全的报告文件名参数以保留前阶段文件，并将“隐藏层”字段改成实际可证明的“所有图层与固定公开页一致”；UI 隐藏操作的旧证据留在原报告。本阶段没有新运行真实 LLM、发布安装包、原生保存对话框自动化或跨操作系统 GPU 测试；其他 DLC 和整个仓库用户 dirty baseline 不在本审查改动范围。
