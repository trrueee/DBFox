# 持久取消信号的即时复查修复

> 文档类型：质量验证
>
> 状态：当前
>
> 最后核验：2026-09-07
>
> 适用范围：Core RunControl；基线 `d434be82`，Windows / Python 3.12.7；作者修复，独立复验另行记录。

模型 HTTP 请求期间已经提交取消请求时，快速返回的工具调用可能仍然写入 owner revision 和 receipt。根因在 `RunControl.is_cancel_requested()`：它把最近一次 False 保留 100ms，导致原有 checkpoint 和传给工具的取消回调暂时不读取耐久事实。本修复移除 False 缓存，保留已观察到的 True；不修改 DLC、provider、Repository、Tool Runtime 或终止结算协议。

## 调查与最小决策

- 当前调用链是 `RunRepository.request_cancel → commit → RunLoop._cancellation_requested → RunControl → checkpoint / Tool cancellation callback`。Loop 的 probe 每次创建短生命周期 Session；Repository.get 已有 `populate_existing=True`，无需在 ORM 再加 refresh/expire 或建立缓存失效通知。
- `git log -S _last_probe -- engine/agent/control.py` 与 `75df80a9` 源码证明该限频缓存来自既有通用 Runtime，并非 Animation 新增。`164beaea`、`edc00760` 的后续重构保留了它。当前 [Kernel 宪章](../architecture/core-kernel-constitution.md)允许修复 Runtime 自身正确性问题；本次恢复既有耐久取消语义，不扩展 Kernel 职责或公开 SDK。
- [Python 官方取消说明](https://docs.python.org/3/library/asyncio-task.html#task-cancellation)中 asyncio 取消在后续调度机会生效，属于协作式机制。它不能直接取代跨 HTTP 请求、线程和重启存在的数据库取消事实。[SQLAlchemy Session 文档](https://docs.sqlalchemy.org/en/20/orm/session_basics.html#expiring-refreshing)提供 refresh/expire/populate_existing；项目已有 fresh Session 与 populate_existing，问题发生在调用它们之前。
- 直接复用现有 callback，并删除负缓存；不新增 Event、后台轮询线程、provider 分支、兼容层、DLC 对 Core DB 的访问或新依赖。正缓存仍保留，使已观察取消不会恢复执行；lease loss 优先级、deadline、provider retry 等待间隔保持原合同。

## 确定性反例与回归

在修改生产代码前，新增 Core 参数化反例固定 monotonic 为同一值：先读 False，再令取消事实为 True，不等待 100ms，分别检查 checkpoint 和外部 boolean callback。原代码两项稳定失败（未抛取消 / 仍返回 False）；补丁后通过，并验证已观察 True 不回退。

原独立 `test_cancel_during_model_http_prevents_owner_write` 保持全部断言不变。本作者在新工作树的修复前单次运行碰巧通过，因此不把该时序敏感样本冒充稳定红灯；确定性 Core 反例给出可复现的修复前失败，独立 HTTP 测试保留生产边界与无 owner 写入的验收合同。

验证命令（仓库根）：

```powershell
python -m pytest verification/tests/agent_core -q --tb=short -m "not e2e and not integration and not real_llm"
python -m pytest verification/tests/system/test_animation_independent_redteam.py -q --tb=short
python -m pytest verification/tests/system/test_tool_runtime.py verification/tests/system/test_engineering_contracts.py -q --tb=short
python -m pyflakes engine/agent/control.py verification/tests/agent_core/test_run_control.py
```

当前结果：Core 341 passed、2 deselected；独立 Animation 红队原集合 10 passed；改动文件 pyflakes 通过。Tool Runtime 与工程合同共 68 passed，唯一失败为已知 Visualization bundle 的 CRLF 差异（796175 bytes 对 manifest 796160），不属于本补丁；未改该 bundle 或工程断言。

## 成本与准确边界

每次尚未取消的检查现在执行原有数据库 probe，增加短只读查询；取消后的检查仍短路。此次没有用未测量的吞吐量收益抵消正确性，也未引入新的轮询源。若以后需要减少查询，应证明副作用检查仍读取最新取消事实，不能恢复 False 的时间缓存。

取消仍是合作式检查，不能原子撤销已经提交的领域写入，也不保证取消提交与最后一次检查之后的外部副作用之间具备跨库事务原子性。该补丁消除已确认的 100ms 人为盲区，不重设计事务或自动重放。独立验证员需在其隔离树应用修复提交后复跑原失败断言；未使用真实模型、付费 API 或发布操作。
