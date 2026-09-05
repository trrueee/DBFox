# Sidecar 标准输出持续消费验证

> 文档类型：质量证据
>
> 状态：当前
>
> 最后核验：2026-09-05
>
> 适用范围：Electron EngineSupervisor 的开发与打包 Sidecar 管道

Pixel 独立验收在真实 Electron 中两次观察到约500次请求后所有 API 挂起，进程仍存活。单独使用生产 EngineSupervisor 和真实子进程的4MiB stdout 探针证实：握手后 readableFlowing=false，子进程无法写完；测试仅恢复 stdout 消费后写入立即完成。这是 Host 活性缺陷，不是领域事务或 CAS 问题。

## 根因与决定

`waitForEngineReady` 在得到握手后关闭 readline；关闭动作暂停底层 stdout。NodeEngineHost 为子进程配置管道，但之后没有 stdout 消费者，最终阻塞子进程的输出。复用 Node 标准库 `Readable.resume()`，在关闭握手解析器后持续消费并丢弃后续字节。[Node 流消费](https://nodejs.org/api/stream.html#readableresume)、[readline 关闭](https://nodejs.org/api/readline.html#rlclose)。

修改仅位于[既有握手结束点](../../desktop/main/engine.ts)。不保留行缓冲、不把原始 stdout 写入公开日志、不改变 stderr、协议、Token、generation、重启或非幂等请求规则。该边界由 Electron Host 拥有，DLC 无法管理父进程管道；无需新增启动器、监控器、SDK 或 Core 领域逻辑。

## 验证

独立工程师提交的[真实子进程回归](../../desktop/main/__tests__/engine.stdout.test.ts)通过实际4MiB pipe验证生产Supervisor，不用模拟Readable状态。修前因果探针失败，修后无需测试干预即写完、flowing=true。`cd desktop; npm run test:electron`：11文件、33项通过，9.85秒，包括现有启动、失败、重启、退出和Main/Preload合同。

独立Pixel最终提交6ed057d0证明真实Electron连续1100次正式HTTP全部200（6.8735秒），同generation且没有重启。独立Voxel最终冷签名候选另验600次HTTP全部200（3.237秒），见[已集成对抗证据](../../verification/bench/capabilities/dbfox_voxel/evidence/adversarial-electron.json)。这些是超过原阻塞阈值的有限样本，不代表无限持续服务。Windows x64 的测试不代表其他平台或安装包已验证。
