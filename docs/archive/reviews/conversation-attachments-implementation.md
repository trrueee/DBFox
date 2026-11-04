# 对话附件第四阶段实施记录

> 文档类型：开发与验证记录
>
> 状态：历史
>
> 最后核验：2026-10-27
>
> 适用范围：Excel 对话附件增量实现

本文件保留第四阶段当时的实施和测试事实。用户随后授权第五阶段；当前安装包、真实模型、旧库兼容与交付结论以[第五阶段验收记录](../../quality/conversation-attachments-acceptance.md)为准。下文“仍需验证”是第四阶段结束时的状态。

## 审核依据和开发基线

用户已审核右侧工作簿原型，并于2026-10-27授权收口问题、进入第四阶段。采用 [已接受架构](../../architecture/conversation-attachments.md)。Git HEAD 为 `6cf4f6c6c499d3a7fc98119256f7d11b000cd557`，工作区已有43项其他改动；编码前已在会话外部目录保存状态、原有 diff 和文件哈希。不回退或提交这些改动。

## 先验证的技术问题

- 保留鼠标诊断 Hook 可复现 revoked Proxy 错误；移除该可选 Hook 后，真实 Electron 的鼠标、只读键盘、查找、切表、十次关闭重开及共享 React 检查通过。三份预览样本继续通过，原始失败记录保留。
- 候选生产依赖仅保留 FortuneSheet Core/React 和 Host React；Core 的 uuid 精确 override 为11.1.1。npm 官方 registry 对该锁定集合的审计为零已知漏洞；这不是无限期安全保证。
- 复用现有 Operation 的独立响应预算，每表8 MiB、按表加载；不增加兼容层或通用传输协议。超限明确说明，分析与预览范围分别验证。

## 文件级计划

任务A：携带一份文件完成可靠分析，同时保留稳定身份和必要来源。

| 范围 | 预计文件 |
| --- | --- |
| Host 附件 | 新增 `engine/attachments.py`、`engine/api/attachments.py`；修改 `engine/models.py`，新增 Alembic migration，注册 API 路由 |
| 接纳和资源范围 | `engine/agent/resource_refs.py`、`references.py`、`repositories/session.py`、`context.py`、`tool_dispatcher.py`、`engine/api/conversation_commands.py`、`engine/runtime_composition.py` |
| 公开可选合同 | `engine/dlc/api.py`、`host.py`、`compiler.py`、`snapshot.py`、`dbfox_dlc_api.py`、`sdk/frontend/index.d.ts` 与 API surface 快照 |
| Data | 新增 `workbook.py`、`workbook_tools.py`、`workbook_view.py`；修改 `contracts.py`、`store.py`、`connection.py`、`database.py`（以实际模块为准）、`tools.py`、`result_view.py`、`contributions.py` |
| Desktop | Composer、消息引用、对话 repository、附件 API 与 Dock 打开；新增 Data 工作簿视图与 vendor 构建脚本；API 合同变化后重新生成 client |
| 依赖 | requirements 输入与生成锁文件，desktop package/lock、vendor 构建与打包；不手改生成锁文件 |

任务B：同会话再次上传、同名文件区分和基于历史文件追问。复用A的身份与范围，补充有界历史目录、成功分析证据、重启与输入边界验证，不新增 active_file_id 事实源。

## 验证计划

先跑受影响的确定性单元/集成测试：上传幂等和并发边界、首次输入原子关联、跨会话和未来输入拒绝、原件缺失/版本变化、工作表与类型诊断、精确聚合、公式限制、完整 SQL Artifact 链、结果分页与导出授权、历史选择和取消。前端验证附件状态、点击 Dock、切换表、卸载、只读与超限反馈。

随后运行 Core 回归、DLC conformance、工程合同、lint/typecheck/build 和相关 Electron 检查。真实模型语义、生产 Sidecar 和安装包结果单独标明，未执行即不宣称通过。阶段四完成后保留实际 diff、命令和结果，等待人工审查，不能直接标记阶段五验收完成。

## 实际实现与检查

第四阶段已形成可审查的增量实现，等待人工代码审核；尚未进行第五阶段产品验收。

### 实际代码落点

| 边界 | 实际文件与行为 |
| --- | --- |
| Host 接纳 | `engine/attachments.py`、`engine/api/attachments.py`、`engine/models.py`、`engine/migrations/versions/f7a8b9c0d0ed_conversation_attachments.py`；不可变快照、ID/哈希、容量、上传重试键、首次输入原子关联、24小时未发送清理 |
| 输入和历史 | `engine/api/conversation_commands.py`、`engine/agent/repositories/session.py`、`engine/agent/run_item.py`；消息保留附件引用，同上传键不同字节/同输入键不同内容拒绝；每条输入仅一份新文件，同名不覆盖 |
| 范围 | `engine/runtime_composition.py`、`engine/agent/context.py`、`context_fragment.py`、`repositories/artifact.py`、`loop.py`、`tool_dispatcher.py`、`engine/tools/runtime/resource_context.py`、`engine/tools/builtin/project_resources.py`；目录、精确 Invocation、历史 Artifact 共用当前 Run 可见边界；已消费补充输入与队列输入分开 |
| SDK | `dbfox_dlc_api.py`、`engine/dlc/api.py`、`host.py`、`compiler.py`、`snapshot.py`、`engine/agent/resource_refs.py`、`sdk/frontend/index.d.ts`；可选 session provider/退役回调、session Operation、附件只读句柄、格式声明与 Dock 会话范围 |
| Data 读取 | `dlcs/dbfox_data/backend/workbook.py`、`workbook_tools.py`、`contracts.py`、`store.py`、`contributions.py`；openpyxl/defusedxml、全量受检类型、源行、Decimal、币种域、缺值/非法值/公式诊断、不可变派生 DuckDB |
| Data 计算 | `workbook_query.py`、`connection.py`、`database_selection.py`、`tools.py`、`artifact_contracts.py`、`result_view.py`、`catalog_tools.py`、`preview_tool.py`、`workbench.py`；复用数据库句柄和 SQL/Artifact/Representation，未创建伪网络连接配置；SQL 校验结果现在明确投影给模型 |
| Dock | `workbook_view.py`、`dlcs/dbfox_data/frontend/workbook.js`、`workbook.css`、`index.js`、`vendor-src/`、生成的 `vendor/`；按工作表懒加载、只读、原格式、缓存公式说明、源单元格定位，控件样式隔离并使用 Host 主题令牌 |
| Desktop | `useAttachmentInput.ts`、`attachmentRepository.ts`、`attachmentDock.ts`、Composer/ConversationCenter/SmartQueryHome/UnifiedComposer/AgentTimeline、WorkspaceDock 与 workbench store；草稿会话、原生授权、上传错误/显式重试、点击预览、作用域迟到响应隔离、首问后提升原草稿 scope |
| 结果读取 | `engine/api/agent_results.py`、`engine/api/dlc_operations.py`、前端 `agent.ts`、ArtifactViewHost、artifactEnvelope、useArtifactTableData；所属会话传递及服务端复核，历史结果分页/导出不跟随当前新文件 |
| 依赖和构建 | `requirements.txt`及3份生成锁、`desktop/package.json/package-lock.json`、`desktop/scripts/build-workbook-vendor.mjs`、`build_sidecar.py`；补充许可证文本和受检证据，未手改生成 API 或锁文件 |

原计划中的 `database.py` 只是候选落点；实际没有新增该文件。读取/连接边界采用现有 `connection.py` 和 `database_selection.py`。前端 API 已运行 `npm run generate:api` 重新生成。

### 实际测试结果

以下计数对应各次命令，集合有重叠，不能相加为独立测试总数。

| 验证 | 结果 | 原始记录文件名 |
| --- | --- | --- |
| 附件定向后端：5个测试文件，含迁移、HTTP上传、签名 DLC、真实隔离 worker、生产 RunLoop、Data SQL 与结果读取 | **26 passed** | `attachments-final2.txt` |
| 最终受影响集合：上述附件测试、既有 Data、结果 API 与 runtime composition | **65 passed** | `affected-final.txt` |
| Core 加两个已修复系统回归文件 | **350 passed, 2 deselected**（其中 Agent Core 341项） | `core-and-regression-fixes.txt` |
| 工程合同与许可证治理最终复核 | **51 passed** | `governance-final2.txt` |
| 前端完整串行回归 | **108 files, 653 passed** | `frontend-all-final.txt` |
| Electron Main/Preload | **11 files, 33 passed** | `electron-tests.txt` |
| `npm run typecheck:test`、`npm run build` | **通过**；构建含 tsc、vendor、Host、生产 Token 与 bundle 检查 | `typecheck-test2.txt`、`build2.txt`、`vendor-build-final.txt` |
| pyflakes（含本次 Data 与新增测试）、mypy | **通过**；mypy检查239个源文件 | `pyflakes-final.txt`、`mypy-final.txt` |
| 系统确定性全量首次回归 | **1168 passed, 2 failed, 135 deselected**；两项随后修复并复核通过，未重复整套18分钟运行 | `system-core.txt`、`core-and-regression-fixes.txt` |
| `npm run lint` | ESLint完成（有既存warning）；设计令牌检查仍失败，**88项均为未修改的 `dlcs/dbfox.comic/frontend/index.css`**；本次附件/vendor样式无剩余报告 | `lint2.txt`、`design-contract-final.txt` |

真实产品链路的 Provider HTTP 边界使用脚本模型，仍走原生 Responses SDK、生产 composition factory、工具注册、隔离 Python worker、真实 XLSX、DuckDB、安全/SQL/结果 Artifact、完成条件及持久化。测试依据独立 oracle，初次十月 CNY 已完成商品明细销售额 **1030.30**，无新附件的家居追问 **380.30**；结果分页与 CSV 导出绑定同一会话和原件。缺少/错误会话拒绝；原件移除后结果重新读取返回来源不可用。脚本测试不证明真实模型一定正确消歧。

另验证精确 `0.10 + 0.20 = 0.30`、并列第一、无匹配与零值、非法金额定位/授权排除、多个工作表、空表、同名文件不同ID、未来输入不可见、已消费追问引用更新、关闭会话清理回放、原始公式缓存只预览、派生文件重建及超大合并区域预先拒绝。原生选择器通过桥接测试控制结果，未宣称已完成真实操作系统文件对话框的人工验收。

### 修复过程与重要取舍

1. 完整链路抓到 Host `.blob` 存储与 openpyxl 文件扩展名检查冲突。改为把受检字节流交给同一个读取库，未添加第二套读取 fallback。
2. 运行中补充附件最初仍显示原 Input 引用；改为读取最新已消费且携带引用的补充输入，排队文件保持不可见。
3. 历史 Artifact 原先只和初始 Input refs 比较，屏蔽了未重复添加文件的追问。产品链路注入既有 Run 资源目录，继续校验精确版本、生产者、会话与顺序；SQL执行仍需当前 Run 的新校验 Artifact。无可变 active_file 或双写镜像。
4. SQL校验默认观察缺少 `can_execute`，现由原有工具公开投影校验结论；计算仍通过原有执行工具。
5. FortuneSheet上游按原格式显示，DBFox只读视图不开启自动重算或诊断 Hook。没有复制厂商源码、修改 CSP 或注入另一份 React。预览规模不代表分析规模，超限拒绝而不截断。
6. DuckDB限制 `<2`，锁为1.5.6，避免功能开发夹带2.0迁移；SQLGlot因原人工输入与旧锁不一致同步锁定，回归通过。openpyxl3.1.5、defusedxml0.7.1；运行/开发锁按Python3.12、构建锁按生产固定3.14.6生成，安装使用哈希校验。此处不代表已在3.14.6运行或构建Frozen Sidecar。
7. jstat1.9.6实际发布包的 `licenses[]` 为MIT，且附完整文本，npm锁未记录旧字段。采用[精确版本及文本哈希的许可证证据](../../../scripts/dependency-license-evidence.json)，只补充外部元数据；版本或文本变化重新失败，未知许可证与拒绝名单照常失败，不改锁文件绕过检查。最终vendor收集全部实际打包依赖许可证。

### 供应链与既有问题

候选查看器精确闭包重新通过官方registry审计：**0项已知漏洞**。完整desktop的官方同源重查：编码前基线锁和当前锁均为 **17项（13 high、4 moderate）**，告警包集合相同；不是“整个产品零漏洞”。早期记录6项来自不同时间的审计，不作为同源差异结论。当前项目已有依赖告警和Comic样式问题未在本功能中批量升级或改写。

### 用例到验证的对应

| 场景/用例 | 已有代码与开发验证 | 第五阶段仍需核验 |
| --- | --- | --- |
| UC-01 携带xlsx首次提问 | 原生桥、HTTP上传、原子接纳、完整真实工具计算链及结果证据 | 真实模型选列/统计口径、真实业务报表、原生文件选择器 |
| UC-02 基于已发送文件追问 | 无新附件的真实RunLoop复算、稳定来源、同名多次文件身份、输入边界与跨会话隔离 | “第一个/之前的/这个”及多候选时澄清的真实模型体验 |
| 附件与来源预览 | 输入框/消息/SQL来源入口、session Operation真实HTTP、原始样式与公式缓存表示、独立Electron交互和十次重开证据 | 集成到DBFox后完整Dock切换/全屏/重启/连续关闭重开、与本机Excel对照 |
| 错误/恢复/边界 | 无效类型/必要值/工作表、版本、原件缺失、超大合并、派生重建、清理重放、超时/取消检查接入原Runtime | 代表性大表耗时、进程终止/断电恢复、实际取消后界面感受、各受支持平台 |

第一版不提供跨文件join、Excel编辑/回写、公式重算、图表/图片完整渲染、CSV/PDF分析。扩展格式时由DLC新增读取工具/预览contribution，沿用Host附件ID、会话、输入引用与生命周期。

### 人工审核与证据位置

本阶段尚未提交Git commit、推送或发布。原有43项工作区修改保持保留，未删除原有文件；本功能在其中14个文件上继续增量修改，其余原有文件与编码前字节一致。会话交付目录 `stage4-work` 中保存编码前哈希和原diff、各次真实测试日志、依赖审计及相对该基线的本功能差异清单。差异共129个文件，包含生成API、查看器vendor/许可证及合成fixture；审阅补丁由独立临时Git索引对比编码前内容生成，文本换行为LF、二进制保留Git binary patch，不修改工作区Git索引。失败记录保留供追溯。正式验收不能把上述开发测试或独立查看器PoC等同于完整桌面安装包验收。

用户已授权进入第五阶段，按第二阶段场景开展安装态和真实模型验收；详见后续记录。用户对实施路线的授权不代表已经逐行审查代码或签署最终产品验收。
