# 质量与发布

> 状态：当前质量导航
> 最后核验：2026-08-06

- [工程质量门禁](./engineering-gates.md)：本地与 CI 的 Python、前端、Rust、迁移、Frozen Sidecar 和依赖策略。
- [Agent 生产评测方法](./agent-evaluation-methodology.md)：分层 Harness、数据集角色、Grader、统计门禁与脱敏 Trace 合同。
- [DBFox AgentBench](./agentbench-implementation.md)：60 场景数据集、评分器校准、真实 RunLoop、故障注入、CLI 和 CI。
- [供应链安全](./supply-chain-security.md)：锁文件、OSV、npm audit、RustSec、SBOM 和许可证边界。
- [发布验证矩阵](./release-validation-matrix.md)：平台、Runner、产物和人工验收的证据要求。

质量文档中的“通过”只对注明的 commit、平台、产物和命令有效。未执行的真实 Provider、数据库、安装、签名、公证或 GUI 场景必须明确写为未验证。
