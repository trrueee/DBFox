# Pixel DLC 验证证据

> 文档类型：质量记录
>
> 状态：当前
>
> 最后核验：2026-09-05
>
> 适用范围：`dbfox.pixel` 实施与集成门禁

当前完成 **Lead调查、独立Domain Architect核验、Backend与Workbench实施/作者验证**。33项后端作者测试、27项前端组件fixture通过；真实浏览器Canvas与窄窗口作者检查见第8节。独立benchmark/stress、完整签名Electron验收和红队仍待执行。架构与接口唯一方案见 [Pixel DLC](../architecture/pixel-dlc.md)。本文不能作为完整DLC完成或发布证据。

## 1. 工作区和基线

| 项目 | 值 |
| --- | --- |
| worktree | `D:/Project/DBFox-worktrees/creative-pixel` |
| branch | `creative/pixel` |
| Lead调查基线 HEAD | `2dc626534fe542ad532dca66a10a23e715b5feb4` |
| Python | `D:/Project/DBFox/.venv/Scripts/python.exe` |
| node_modules | 共享只读 junction，不安装或改共享锁 |
| CodeGraph | 此 worktree 无 `.codegraph/`，已跳过 |
| 基线 | 包含 Director 提供的用户原未提交变更；禁止改写或提交 |

Pixel 允许修改：`dlcs/dbfox.pixel/`、`verification/tests/system/test_pixel_dlc.py`、`desktop/src/features/dlc/__tests__/dbfoxPixelFixture.test.ts`、`verification/bench/capabilities/dbfox_pixel/`、本页与架构页。本阶段只新增两份文档，没有提交 Git。

## 2. 专员排程与可恢复状态

初始全局4槽均使用中（Director、Scene Backend、Voxel Backend、Pixel Lead）。Pixel Lead 已申请 Domain Architect 槽。Director 随后要求先提交精确 canonical/API/codec 方案并阶段返回，腾出执行槽给 Scene Workbench；后续由 Director 按逻辑 Pixel Lead 归属复用工作线程，禁止把角色复用虚报为同时存在的5个 Agent。

| 逻辑角色 | 实际线程/状态 | 本阶段产出 |
| --- | --- | --- |
| Pixel Lead | `/root/pixel_lead`，阶段交接 | 原模板完整读取、Host/codec 调查、canonical/API 方案 |
| Domain Architect | `/root/scene_lead/domain_architect`，Director调度转任、逻辑归属`/root/pixel_lead`；本阶段完成 | 首次参与Pixel，只读核验并修正权威架构页；未写Pixel backend/frontend/tests |
| Backend Engineer | `/root/pixel_backend`，Director独立分配，本阶段完成 | canonical、Store、18Tools、12operations、PNG Representation、30作者测试；不自称独立红队 |
| Workbench Engineer | `/root/pixel_workbench`，Director独立分配，本阶段完成 | Canvas、图层/帧/标签与选区编辑、固定成果表示、27项fixture及作者视觉检查；不自称独立红队 |
| Verification Engineer | 未分配 | 待最小实现可运行后添加独立确定性测试、bench 和 stress |
| Adversarial Reviewer | 未分配 | 必须由未参与相应实现的作者以外 Agent 执行；不得作者自审 |

机器可读状态（与上表同义，用于调度恢复）：

```json
{
  "dlc_id": "dbfox.pixel",
  "logical_lead": "/root/pixel_lead",
  "worktree": "D:/Project/DBFox-worktrees/creative-pixel",
  "branch": "creative/pixel",
  "phase": "workbench_implemented_author_verified",
  "integrated": false,
  "implementation_started": true,
  "specialists_created": 1,
  "specialist_roles_completed": ["domain_architect", "backend_engineer", "workbench_engineer"],
  "assigned_specialist_threads": ["/root/scene_lead/domain_architect", "/root/pixel_backend", "/root/pixel_workbench"],
  "specialist_schedule": ["domain_architect", "backend_engineer", "workbench_engineer", "verification_engineer", "adversarial_reviewer"],
  "next_action": "Independent Verification uses the complete frontend/backend package, then capability bench/stress and Adversarial Review",
  "core_changes": [],
  "proposed_dependency": "PyPNG 0.20220715.0, unmodified pure Python vendor, MIT",
  "dependency_downloaded": true,
  "dependency_in_product": true,
  "tests_passed": ["33 backend author tests, 9.10 seconds", "27 frontend author fixtures, 6.72 seconds", "typecheck:test", "lint: 0 errors, 5 preexisting warnings", "production build + token/bundle checks", "pyflakes", "mypy: 5 authored source files"],
  "review_completed": false,
  "architecture_review_completed": true,
  "known_constraints": ["No public Project deletion hook", "No owner state subscription in public frontend SDK", "Package forbids native binaries", "Author tests are not independent review or full DLC completion", "Backend package tests use an isolated temporary frontend stub"]
}
```

## 3. 已完成的调查证据

- 完整读取 Director 实例化 `lead-pixel.md`、仓库 AGENTS 与 CONTRIBUTING；读取原始总任务，核对 Pixel 范围和五专员要求。
- 核对 `dbfox_dlc_api.py` 的公开导出，以及 `sdk/frontend/index.d.ts` 的全部声明。
- 查看 Capability 合同、Runtime 架构、implementation map、Artifact/Representation、Core 宪章、复用规范、文档规范与术语表。部分长文档批量输出被工具截断；后继 Architect 应按具体边界继续读相关段落，不能把此记录理解成“全部 docs 全量审查通过”。
- 读取 Music canonical/contracts/Store/Tools/operations/前端注册模式，Story typed operations 与冲突，Visualization Representation provider。Data/Workspace/GitHub 的完整实现、完整 docs/specs 与历史质量矩阵仍需专员补充调查。
- 公开源码确认 `ExtensionToolRunContext.is_cancelled()`、历史 ResourceScopeRef、owner project operation、显式 `DlcActionRunsHost` 均可用。
- 搜索发现 Pillow 仅在开发依赖；未发现 Pixel 现有实现；`git log --all -- dlcs/dbfox.pixel` 无记录。未开展 GitHub issue 全量检索。
- 浏览 PyPNG 官方 PyPI、MDN Canvas 2D、Python sqlite3 与 SQLite 事务文档。PyPNG 文档旧路径返回404，选型事实来自其官方分发说明；尚未下载、审计或测量 vendored 包。

## 4. 待执行验证矩阵

Director 另行核验了候选 PNG 依赖：从 PyPI 官方分发下载固定源码包，SHA-256 与架构页及
PyPI 元数据一致；只提取原样 `code/png.py`（82,781 bytes，SHA-256
`b1c6211078af892bbe975f948d40e19f2e9ec064994f635b6e431b5c55e56830`）与 MIT 许可证。
候选文件与 provenance 暂存仓库外 `D:/Project/DBFox-worktrees/creative-program/pypng-review`，
未加入产品包、未安装到共享 Python 环境。使用该编码器生成 32×32、320×32 与 1024×256 RGBA
图，再由开发依赖 Pillow 独立解码；尺寸与全部像素完全一致，最大样本编码约 0.010 秒。
这仅证明候选库在当前开发环境中的输出兼容性，不能替代 Pixel Representation 和 Frozen
Sidecar 包的后续验证；产品代码也不能据此依赖 Pillow。

| 门禁 | 场景 | 当前结果 |
| --- | --- | --- |
| canonical | 全部高层操作、删帧/标签、锁层、坏索引、空作品、预算、no-op | 未运行 |
| persistence | 新库、重启、事务故障、损坏、未知版本、重复 receipt | 未运行 |
| concurrency | 同head双写、stale scope、stale expected version、Human→Agent | 未运行 |
| runtime | 编译注册、正式Tool执行、取消、timeout、reconcile、同Run create→edit→inspect→edit | 未运行 |
| lifecycle | activate/deactivate/reactivate、contribution清理、timer/request释放 | 未运行 |
| representation | Artifact provenance/hash/版本、PNG交叉解码、sheet/tag对齐、非法路径/URL | 未运行 |
| frontend | Canvas真实输入、选择、palette、layer、timeline、animation、undo、旧请求隔离 | 未运行 |
| benchmark | 简单/增量/多阶段、坏指令恢复、先inspect、stale、no-op、歧义、大图、有界context、negative | 未运行 |
| stress | 狐狸骑士32×32、4idle+6attack，经生产Tool path及至少10类连续修改 | 未运行 |
| independent review | Core泄漏、权限、取消、重放、并发、损坏、UI divergence | 未运行 |
| package | manifest、API v2编译、纯Pythonvendor许可证/哈希、禁止native/eval/WASM | 未运行 |

预期命令（文件尚未实现，当前不得报告通过）：

```powershell
D:/Project/DBFox/.venv/Scripts/python.exe -m pytest verification/tests/system/test_pixel_dlc.py -q --tb=short
```

前端完成后在 `desktop` 运行针对 `dbfoxPixelFixture.test.ts` 的串行测试、`npm run typecheck:test`；DLC独立静态合同与必要package测试由 Verification 专员明确补齐。正式宿主集成、目录登记和全量共享门禁由 Director 协调。

## 5. 接续实施说明

独立Architect已把预算、binary alpha、typed op字段、删除恢复与表示决定写回同一架构页，没有新增平行合同。之后 Backend 只实现 `dlcs/dbfox.pixel`，Workbench 只消费冻结接口。Verification 不以作者解释替代运行证据；Reviewer 保持独立。所有 confirmed high-severity findings 修复并回归后，Lead 才能提交正式 `DLC COMPLETION REPORT`。Director 是 integrated 状态的唯一审批者。

## 6. 独立架构核验记录

结论：**accepted，接受已直接修正的权威架构合同**。评审者此前仅参与Scene与Voxel，未参与Pixel Lead原设计或任何Pixel实现；因此本次属于独立Pixel架构评审。若后续转任Pixel Backend Engineer，该作者将不能再承担Pixel独立红队。没有新建子Agent、没有执行实现/fixture，也没有使用或购买额度重置。

本轮读取完整外部 `creative-program/lead-pixel.md`、AGENTS、CONTRIBUTING、Pixel架构/质量页，补读文档规范、术语与Capability合同。无 `.codegraph`，使用rg和精确源码读取。核验实际边界：

- `engine/dlc/api.py` 的 Tool context、DlcActionRunsHost、DlcOperationSpec；公开 `dbfox_dlc_api` 提供BaseModel/Field/ConfigDict，可用model_post_init作本地跨字段校验，不需导入Engine。
- `engine/tools/runtime/base.py:148` 的ToolInputModel只默认extra/frozen，不默认严格int/bool；使用当前环境Pydantic的内存探针证实 `ConfigDict(strict=True)` 下 `Literal[1]` 仍接受true，而 `Field(strict=True)` int拒绝bool、bool拒绝0。探针只打印校验结果，未写测试或产品文件。
- `engine/tools/runtime/resource_authority.py:58` 与 `engine/agent/tool_dispatcher.py:316`：每次Invocation从Project discovery绑定当前身份/版本；仍须DLC expected_version防旧意图。历史resolver只支持读取/reconcile，不授权新写。
- `engine/dlc/action_runs.py:118` 附近：未传session_id会新建Session，不能宣称跨Session idempotency。架构明确未知导出不重放；若提供同mutation_id查询，则先预留owner精确receipt，未知预留fail closed，不造第二个Run或scheduler。
- `engine/representation.py:24` 和 `:110`：operation区分JSON/stream；单独冻结sheet_layout JSON，不把布局混进PNG结果。`DlcOperationSpec` 默认输出1MiB，因此frames.read需显式2MiB。
- `engine/dlc/loader.py`：命名空间内原样Python子模块可加载，package信任与校验不等同恶意插件安全沙箱；仍需后续真实签名package验证。

修正前发现并已在同一权威页消除的歧义：事务外查receipt的并发窗口；未定义owner历史quota；nullable默认和patch-null语义；整数schema版本接受bool；frame_delete绕过locked cel；对象ID历史复用；restore的deleted Resource不可discovery；完整tag目录超过Tool budget；frames.read默认输出预算偏小；sheet stream和布局JSON混同；ActionRun与owner事务不能原子结算的导出重复风险。

冻结的主预算为262144像素槽、canonical2MiB、owner历史128MiB、每Project128 active documents、每动作128ops/规范输入64KiB、Tool输出16KiB、context4×2000字符。具体字段、操作顺序、锁语义、全部25问只维护在架构页，本页不复制合同。

PNG选型复核：浏览官方 [PyPI固定版本页](https://pypi.org/project/pypng/0.20220715.0/)，其归档hash与Director provenance一致；Get-FileHash重算仓库外png.py，得到 `b1c6211078af892bbe975f948d40e19f2e9ec064994f635b6e431b5c55e56830`。阅读MIT许可证、Writer参数与AST导入列表；全部标准库，源码包含的Reader/CLI不开放给产品输入。采用受限Writer内存编码，拒绝自研PNG、产品Pillow/native包或共享依赖变更。没有再次宣称已跑Director的三尺寸Pillow probe；该结果保留其原作者归属，后续必须跑实际Representation解码/透明像素/sheet顺序测试。

未关闭门禁：Pixel生产实现与所有功能测试仍未开始；Director在Scene生产RunLoop发现ArtifactRepository仍按初始SessionInput校验新合法Invocation refs的通用Host问题，后续独立Host正确性审查处理。Pixel禁止清空refs或每次创建新Run规避，必须用真实same-Run create→edit→inspect→edit验证。Host openArtifact通用导航的独立实现也不等于本Pixel工作台已经集成。

本轮仅修改 `docs/architecture/pixel-dlc.md` 与本页；没有提交Git。文档检查使用 `git diff --check -- docs/architecture/pixel-dlc.md docs/quality/pixel-dlc-evidence.md`；源码缺失、未运行产品测试是当前事实，不是测试通过。

## 7. Backend实施与作者验证（2026-09-05）

本节是架构评审之后的实施记录；第3至6节中的“尚未实现/未运行”描述其当时阶段。实施者 `/root/pixel_backend` 只修改Pixel专属文件，没有修改Core、公开SDK、共享锁文件或环境。所有Host修改由Director另行提交和合入。

实现入口：[contracts.py](../../dlcs/dbfox.pixel/backend/contracts.py)、[domain.py](../../dlcs/dbfox.pixel/backend/domain.py)、[store.py](../../dlcs/dbfox.pixel/backend/store.py)、[contributions.py](../../dlcs/dbfox.pixel/backend/contributions.py)、[representation.py](../../dlcs/dbfox.pixel/backend/representation.py)。Workbench接入说明见 [DLC README](../../dlcs/dbfox.pixel/README.md)。Manifest已声明正式frontend入口，产品前端尚待实现；后端测试只在pytest临时source放置明确stub，不把它作为作品编辑UI。

Windows当前环境、Host集成HEAD `8b70c89c` 上执行：

```powershell
D:/Project/DBFox/.venv/Scripts/python.exe -m pytest verification/tests/system/test_pixel_dlc.py -q --tb=short
```

结果：**33 passed in 9.10s**。测试源见 [test_pixel_dlc.py](../../verification/tests/system/test_pixel_dlc.py)。另运行5个自有核心源码的pyflakes、mypy `--follow-imports=skip --no-incremental`，均通过。Vendor保持原样，不把upstream编码风格的lint改动混入。

| 边界 | 实际作者证据 |
| --- | --- |
| 严格模型 | bool/float/字符串坐标与版本拒绝；schema true拒绝；null默认归一后经Host exclude_none再解析一致；未知字段拒绝 |
| 领域编辑 | fill/line/rect/stamp、三种旋转镜像及重叠move快照；palette/frame/layer/tag操作、锁层及标签删除约束 |
| 版本/身份 | no-op只存receipt、历史hash可重现的undo/redo、tombstone/restore、历史ID禁止复用、同批create/delete不复用 |
| 并发/恢复 | 双writer只有一方推进；exact duplicate双writer返回同一结果；输入/actor/frozen scope绑定；重启历史resolver/reconcile |
| 进程故障 | 子进程BEGIN后修改head并 `os._exit(7)`；重开仍为旧修订；receipt插入trigger故障使新revision/head一起回滚 |
| 坏状态 | 非SQLite文件、未知user_version、hash错、缺cel、坏palette index、未知document schema、重复JSON key、缺birth record、坏receipt全部fail closed；读取blob前先用SQLite length/typeof拒绝超预算document/receipt |
| 预算 | 128×128×16 frames及128×128×16 layers分别验证262144slots；新增超限拒绝；128ops/64KiB输入；quota拒绝但旧读/exact receipt仍可用 |
| 取消 | 计算后commit前取消不落库；deadline前置拒绝；commit后的Host取消回报经原receipt查证恢复，不自动执行第二次 |
| PNG | 真正Representation输出由开发Pillow解码核对透明、实际颜色、图层visible、tag逆序sheet、duration、128×128；更新palette后旧Artifact PNG字节完全不变 |
| 签名生命周期 | 临时前端隔离fixture + 全部真实后端/vendor签名、信任、安装、激活18Tools/12operations；禁用清贡献、再启用读取原状态 |
| 实际RunLoop | 同一个Run创建→rect→inspect→line→export；5个成功Invocation，最终revision3；动态document_id/version只读正式function_call_output，不由Store回填模型 |
| 实际Observation | 对Provider收到的完整JSON同时校验≤18000字节与字符；耐久facts无pixels；inspect的64格pixels只在临时Provider窗口，ID/version完整可用于下一步 |
| Human导出 | 真实 `documents.export` 经生产DlcActionRunsHost，生成第二个completed Run和Artifact；同mutation_id再次调用返回原结果，元数据库仍只有两个Run；reservation在Run开始前预留完整16KiB结果额度，额度不足不留下reservation |

同Run测试首次在旧Host上 **29 pass / 1 fail**，失败为ArtifactDraftContractError造成TOOL_OUTPUT_CONTRACT_FAILED。Director将独立authority修复 `8ba14f69` 合入后，原样强断言通过。没有xfail、清refs、私读Core补authority或每次新Run规避。Human导出额外Run是用户明确导出边界，与前述单Run连续创作测试分开。

实施收紧的可见合同：Agent `pixel_documents` 每页最多8以适应16KiB输出；Human目录保持32。Inspect/diff输出过大时明确要求缩小page_size并从page0重新读取，保留完整条目和确定页偏移。新增 `pixel_delete` 正式工具暴露可恢复tombstone，与既有Human delete使用同Store。无通用mapper、镜像文档、私有HTTP或额外调度器。

依赖决策落实：PyPNG 0.20220715.0原样png.py与LICENCE已vendored，逐字节SHA验证通过；provenance保留官方归档和单文件hash。DLC内 `.gitattributes` 禁止对已核验upstream字节做换行转换。只调用Writer内存RGBA输出，产品没有Pillow依赖、图片Reader入口或native包。未声称全量供应链漏洞审计。

仍未关闭：真实完整前后端包/Canvas交互、独立12类能力bench、狐狸骑士4idle+6attack持续10类生产Tool编辑、独立adversarial review以及Composition验证。作者测试没有借用别的DLC的bench或scorer，不将scripted模型解释为真实LLM创造力证明。33项通过只允许交接Workbench，integrated仍为false。

## 8. Workbench实施与作者验证（2026-09-05）

实施者 `/root/pixel_workbench` 在已接受架构和后端提交 `113f5334` 后单独承担前端实施，不是Pixel独立Reviewer。过程中Director合入共享Context修复，交付前HEAD为 `7ff6b369`。本阶段自有文件只有frontend三文件、对应fixture及Pixel README/架构/本质量页。无Core/SDK/后端/manifest合同/共享依赖修改；manifest原有entrypoint直接指向现有真实工作台。

已实现功能与操作说明只维护在 [Pixel README](../../dlcs/dbfox.pixel/README.md)。技术调查读取完整Lead模板、规范、严格后端contracts、SDK、Scene/Voxel/Music工作台模式，并采用仓库UI/UX skill的键盘、焦点、清理和窄窗口要求；不采用其建议的外部像素字体/主题，继续使用Host语义令牌。平台依据为 [MDN Pointer Capture](https://developer.mozilla.org/en-US/docs/Web/API/Element/setPointerCapture)、[Canvas插值控制](https://developer.mozilla.org/en-US/docs/Web/API/CanvasRenderingContext2D/imageSmoothingEnabled)、[requestAnimationFrame](https://developer.mozilla.org/en-US/docs/Web/API/Window/requestAnimationFrame)。不引入绘图依赖、兼容层或迁移。

Windows作者检查：

| 命令/边界 | 实际结果 |
| --- | --- |
| `npm.cmd test -- --maxWorkers=1 src/features/dlc/__tests__/dbfoxPixelFixture.test.ts` | 27 passed，6.72s；实际产品组件，仅typed transport/Canvas设备测试边界控制 |
| `npm.cmd run typecheck:test` | 通过，包含fixture对公开SDK的静态类型检查 |
| `npm.cmd run lint` | 通过，0 errors / 5个原有共享组件warnings；设计令牌合同通过 |
| `npm.cmd run build` | 通过，Electron构建、生产Token检查与bundle预算通过；入口gzip186032B |
| `node --check frontend/index.js`、`model.js` | 语法通过 |

27项fixture覆盖：同修订帧/palette/cel核对；真实组件创建入口；整数坐标与一次批量笔迹；cancel/lost capture/超128段整笔取消；橡皮/flood/矩形；锁层与父document onAsk；区域translate/rotate及显式clip；palette/layer/frame/tag编辑；顺序/时长/非循环播放；输入框快捷键隔离与键盘一格绘制；历史undo；CAS冲突读回且不自动重发；可见head同步；262144slots结构上限；导出缺失Host方法先失败；同signal操作与导航；unmount/scope/deactivate的迟到导出与写入隔离；未知导出不创建替代Run、已知成果仅重试导航；deactivate即刻释放指针及停止旧onAsk；迟到初始读取不再读取帧；重复注册只保留一个样式；公开不可变PNG/sheet读取及URL释放。

作者真实浏览器检查使用Codex in-app浏览器和任务私有的本地页面，产品模块/Host React/设计令牌原样运行；operation transport和32×32/10帧狐狸骑士示例为明确的内存视觉fixture。真实Canvas、指针捕获、ResizeObserver、RAF和CSP运行，不用jsdom Canvas替代。记录：

- 1280×720浅色、1280×800深色：完整狐狸角色、调色板、图层、动画预览、10帧时间线可见。真实拖动经 `documents.apply` 将r1推进r2，并读回显示已保存。
- 初始12×导致短窗口裁掉部分画布；修正为ResizeObserver计算整数适配级别，并提供“适应画布”，手动缩放不被后续自动覆盖。修正后浅色6×、深色8×完整显示。
- 375×812：第一轮发现侧栏超出flex基础高度，时间线覆盖后续内容；修正窄容器为自然高度，Canvas先显示，其他面板与时间线按顺序滚动。修正后根无横向溢出，timeline top与body bottom均约1928.33px（浮点差<0.001px），无实际覆盖。
- 本地页面CSP为 `default-src self; script-src self; style-src self; img-src self blob:`；只加载本地模块/样式，预览PNG来源为公开Blob；浏览器日志无error/warn。未添加unsafe-eval、远程图像或样式例外。

视觉fixture的10帧只有用于观察的相同角色图案，不冒充4idle+6attack生产Tool创作压力任务。未用它证明SQLite、Agent/Human往返、签名Frontend Loader或Electron下载落盘。未执行独立benchmark/stress或红队，integrated仍为false。后续Verification必须打包真实frontend三文件，替代Backend隔离stub进行完整验收。

构建脚本重新生成Music/Visualization vendor的Windows换行，保留为未暂存的非Pixel文件；未纳入本阶段提交。临时浏览器页面/示例不进产品或Git，任务结束关闭浏览器、恢复viewport并停止专用本地server。

## Director接续核验（2026-09-05）

Workbench Agent因账户额度停止在提交前，既有实现与记录保留。Director原样重跑工作台fixture：**27 passed，6.64秒**。随后将两处签名fixture改为复制真实frontend目录，并逐字节比较包内index.js/model.js/index.css与产品文件；完整后端、签名包激活和生产RunLoop集合 **33 passed，11.48秒**，测试Pyflakes通过。第7节的stub说明属于后端早期阶段，现行测试不再使用它。

这属于Director接续检查，不是独立Verification或红队；真实Electron、12类benchmark、4idle+6attack的生产Tool压力作品和独立终审仍未完成。由于三个子Agent均报告账户usage limit，下一独立角色暂未启动；不据作者检查改变integrated=false。
