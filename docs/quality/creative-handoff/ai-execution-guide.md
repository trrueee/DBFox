# 接手 AI 的执行与验收指南

> 文档类型：工程指导
>
> 状态：当前
>
> 最后核验：2026-09-06
>
> 适用范围：Creative DLC 后续实现者、验证者、红队和集成人

## 可直接复制的通用启动指令

```text
你接手 DBFox Creative DLC 的一个有界任务，不负责擅自扩大到整个计划。
先读 docs/quality/creative-program-handoff.md 和用户指定的 task packet。
用户最后决定因额度有限停止原自动工厂，转交其他 AI；请只执行用户分配的范围。
核查实际 git/worktree/dirty 状态，不把交接中的旧 SHA 当成当前 HEAD。
保留用户 baseline，不重写已完成的 Scene/Voxel/Pixel/Shader，不重复实现共享修复。
先做与问题规模匹配的现有实现/依赖/官方方案/历史调查，再编码。
代码、验证、红队必须区分角色；作者测试不能冒充独立验收。
如果有 subagent 能力且用户允许，分配独立任务；没有则明确记录阶段身份和独立性缺口。
工作应产生可审查代码、实际证据和精确提交，不能停在路线图。
不要购买或使用付费 API，不要发布/推送/发外部消息，不要兑换额度。
遇到真实环境限制，保存失败与未验证项；不要修改测试或扩大预算掩盖问题。
```

## 开始前的最小调查

读取根 `AGENTS.md`、`CONTRIBUTING.md`、`docs/architecture/implementation-map.md`、`docs/architecture/core-kernel-constitution.md`、DLC platform/SDK/authority 合同及目标 DLC 当前架构。

根有 `.codegraph/`：理解/定位源码先用 `codegraph explore` / `codegraph node` 或对应 MCP。其他工作树没有该目录时跳过，不自行初始化索引。CodeGraph 不覆盖文档/配置或结果过时，才用文件读取补充。普通搜索优先 `rg`。

通用能力必须检查项目内已有实现、当前依赖/标准库、官方文档/成熟方案和历史否决记录。重要决定记录：采用什么、为何其他方案不适用、依赖/许可证/维护/性能/退出风险、是否产生迁移债务。已有 preflight 是起点；换方案或版本时重新核对官方信息。

## 不可破坏的边界

- Core 不认识 Scene、Voxel、Pixel、Shader、Game entity、Comic panel 等领域概念。领域 canonical model 和业务逻辑只在 owner DLC。
- 后端 DLC 只经 `dbfox_dlc_api`，前端只经正式 `sdk/frontend` 与 Host 注入合同。不得导入 Engine/Renderer/其他 DLC 私有模块或读其数据库。
- SQLite 是持久事实源。UI 草稿、选择、缩放是投影，不驱动 RunLoop 或持久状态机。
- Tool 注册和执行走现有 Runtime：物化、policy、approval、invocation authority、执行、观察、Artifact、恢复。禁止另造调度器。
- Input admission、当前 Project 发现、Invocation 冻结权限、Artifact producer/lineage 是不同事实。发现某工具或对象不代表获得私有资源权限。
- Agent 与人类编辑共用 CAS 业务入口；无效/stale/no-op 不推进版本。取消/断线/代次变化后不自动重放非幂等请求。
- 历史 Artifact 固定 owner、Project、document/version/hash 与 producer；Representation 参数不能覆盖这些身份。
- 结果有明确总量、单页、单次操作和模型观察预算。不能将完整大型作品塞入 Context。
- 模型使用原生 Responses function calling，不解析 Thought/Action/Observation 文本。
- 秘密只存 OS 凭据库；不进 .env、业务数据库、日志、公开错误、localStorage。不要提交运行时数据库、二进制安装包或测试密钥。
- 冻结 Kernel/公开 SDK 的改变必须逐项回答宪章七问，并有至少两个真实能力或明确 Core 正确性问题支撑；优先最小已有接入口。

## 每个新 DLC 的完整交付

1. **领域合同**：Resource、Object、Selection 分开；冻结 canonical model、稳定 ID、坐标/时间/顺序、版本/undo、配额、schema 和引用规则。
2. **后端**：创建、增量编辑、检视/分页、删除/恢复、diff、不可变发布与表示。禁止“局部改动→整文档替换”。
3. **Workbench**：真实视觉工作区、鼠标/键盘直接编辑、明确草稿、冲突处理、历史固定视图、引用 Agent、导出；只显示 JSON 不算成品。
4. **人机协作**：真实人类操作后由正式模型工具继续局部修改；下一步 ID/version 从正式工具输出取得。
5. **验证**：持久化、stale、no-op、取消、超时、提交前后故障、停启、乱序/迟到响应、权限负例、规模与逐字节/逐像素成果检查。
6. **benchmark**：至少 12 类场景，复杂作品连续 10 类修改，局部修改保持其余内容；与生产装配和默认预算一致。
7. **独立门禁**：非作者 Verification 和另行红队的明确范围与结论，修前反例和修后复验。
8. **文档/状态**：当前架构、API/schema、使用说明、例子、证据、机器状态、精确 commit。

新模型必须主动回归既往教训：严格 nullable schema 与运行验证一致；历史正整数连续性；pass/frame/page 顺序出现在 diff；receipt 摘要绑定原事实；完整文档内容 hash；提交前最后取消检查；CodeMirror/Phaser/Three 生命周期释放；窄 Dock 用实际容器宽度；独立 UTF-8 日志不共享残字节状态。

## 减少无效验证成本

- 先在原失败边界保存最小反例，再改源头，原样复验。
- CSS 改动用真实浏览器/原生宽窄尺寸和截图；无需重跑全部后端/实际 GPU。
- Schema 改动必须验证实际物化 schema，不只验证手写最小参数。
- Runtime/权限/恢复改动再跑相关 Core、System、工程与真实 composition，不以作者手工工厂替代产品工厂。
- 测试通过且没有新的改动/疑点后停止扩大复跑。把未测范围写清楚。
- 模拟驱动/受控模型只证明该边界，不称作真实 GPU 或自由模型创作智能。失败夹具与产品失败分开记录。
- 长任务保存结果和公共 RunItems 后再排查；异常不能先重放成功过的写入。

## 本机命令

PowerShell，Python 3.12 环境已在 `D:/Project/DBFox/.venv/Scripts/python.exe`。根隔离 fixture 实际位于 `verification/conftest.py`；pytest 从对应仓库根运行。独立临时脚本若必须加载 Engine，先安排同等隔离，不能碰用户运行库。

```powershell
# 从目标 worktree 根运行，按改动选择测试，不默认全量重跑
D:/Project/DBFox/.venv/Scripts/python.exe -m pytest verification/tests/system/test_shader_dlc.py -q --tb=short
D:/Project/DBFox/.venv/Scripts/python.exe -m pytest verification/tests/system/test_engineering_contracts.py -q
D:/Project/DBFox/.venv/Scripts/python.exe -m pytest verification/tests/agent_core -q --tb=short -m "not e2e and not integration and not real_llm"
D:/Project/DBFox/.venv/Scripts/python.exe -m pyflakes engine build_sidecar.py scripts
D:/Project/DBFox/.venv/Scripts/python.exe -m mypy --no-warn-unused-configs --follow-imports=skip engine build_sidecar.py --no-incremental

# frontend：必须单 worker
Set-Location desktop
npm test -- --maxWorkers=1 src/features/dlc/__tests__/dbfoxShaderFixture.test.ts
npm run typecheck:test
npm run lint
npm run test:electron
npm run build
```

`npm run build` 会执行 Music/Visualization vendor 构建，某些工作树已有这些派生文件的 dirty 状态，不能混入本任务。部分 worktree 的 `desktop/node_modules` 是指向根的 junction；不要同时安装、删除或大范围重写它。当前没有 Rust，旧文档的 test:rust 不可用。

Python 依赖使用 `pip install --require-hashes -r requirements-dev.lock`；前端安装使用对应目录 `npm ci`。不手改锁文件。FastAPI 合同变化需要 `npm run generate:api`；仅 DLC 自有 Pydantic schema 改动通常不改变 Host OpenAPI，使用注册模型生成自有快照，不手写生成 JSON。

开发启动 `./dev.ps1 backend|frontend|both`；正式后端模块入口 `python -m engine.main`。脚本会安排共享开发 token；不要将 token 打印或复制入交接文档。启动后台 Windows helper 用隐藏窗口；清理只关闭自己创建的进程。

## 独立验证指令模板

```text
你是非作者 Verification Engineer。目标是证明用户功能和正式运行路径，而不是增加测试数量。
先核对精确候选、签名包源码字节、Host/DLC版本和工作区基线。
只从公共 Tool/Operation/Artifact/Representation 得到下一步事实，不从私有库补回模型状态。
覆盖真实编辑、Agent继续、保存/重开、历史表示、规模、取消和卸载；GUI证据必须实际截图与操作。
发现问题交作者修复；你保留原反例，只在夹具确实错误时调整，并记录原因。
模拟边界与真实设备证据分开。所有测试使用默认产品工厂和预算。
交付正式报告、精确新增测试清单、源码SHA/包digest、通过及未验证项。只提交自己的文件。
```

## 独立红队指令模板

```text
你未实现该 DLC。假设其版本、取消、权限和生命周期有隐藏缺陷，从零选择攻击。
检查schema/type/nullable、引用、正整数history、head/parent、receipt/producer、ABA、配额、分页、
跨Project/Run/Session、停用升级、迟到结果、COMMIT前后故障、真正局部修改和历史成果保持。
先保存可重复失败和公共入口影响，不能只列假想问题，也不能把另一人的测试改名计数。
报告风险等级、具体源位置、最小步骤、预期/实际、修复后原样复验、残余限制。
负驱动回执不是GPU证明；可重写所有事实的本地管理员不是签名包声明的安全边界。
无未解P1/P2只针对你的实际范围，不替代其他验收门禁。不要未经要求修产品。
```

## 交付模板

```text
任务 / 角色：
工作树 / 分支 / 基线：
本次提交 SHA（或明确未提交文件）：
解决的具体用户行为：
canonical / Resource / Artifact / Representation 边界：
调查与复用选择、未采用方案：
实际验证命令、数量、耗时、候选与设备范围：
独立验证/红队：已完成或缺口，不能省略：
已知问题与环境限制：
用户 baseline 是否保持：
后台进程/临时数据是否清理或保留于何处：
下一位 AI 的第一个动作：
是否满足该任务门禁；谁可作集成决定：
```
