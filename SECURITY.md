# 安全政策

## 支持版本

DBFox 当前处于持续开发阶段。只有通过规范仓库 [`trrueee/DBFox`](https://github.com/trrueee/DBFox) 的正式发布工作流生成的最新 GitHub Release（当前为 Windows x64）受到安全修复支持；`main` 的历史提交、未发布构建、fork 和第三方重打包产物不在支持范围内。

## 什么属于安全漏洞

请报告以下类型的问题：

- 绕过 SQL 只读执行链、方言校验或参数绑定，执行任意/写操作；
- 泄漏或越权访问数据库凭据、模型 API Key、运行时 Token、DSN、会话内容或查询结果；
- 绕过 Electron preload/IPC sender 校验、CSP、Sidecar 鉴权或系统凭据库边界；
- 绕过升级器、安装包或构建来源（Attestation/Authenticode）的完整性校验；
- 依赖供应链问题（恶意依赖、锁文件或哈希校验绕过）。

## 什么不属于

- 依赖过时提示、普通 bug、UI 问题或功能建议（请走普通 Issue）；
- 需要数据库管理员权限、系统管理员权限或已修改本地安装的攻击场景。

## 如何私下报告

**请勿在公开 Issue 中粘贴 API Key、DSN、Token、数据库 dump、原始日志或可利用细节。**

使用 GitHub Security 标签页的「Report a vulnerability」私密通道，或通过 [`AUTHORS.md`](AUTHORS.md) 列出的维护者渠道联系。报告请尽量包含：

1. 受影响版本或 commit；
2. 脱敏后的复现步骤；
3. 影响评估（数据、凭据、完整性或可用性）。

维护者会在 7 天内确认收到，并在修复发布前对报告内容保密。

## 处理承诺

- 确认的问题按严重程度在正式 Release 中修复，并在修复发布时通过 Release Notes 披露；
- 不接受「先公开再修」或「不披露」的要求；
- 报告者可在修复发布后获得公开致谢（如愿意）。

## 安全边界说明

- 数据库密码、模型 API Key 和 SSH Secret 只进入操作系统凭据库；
- 正式前端与安装包不得包含开发 Token；
- Agent 数据访问默认经过受约束工具，SQL 必须先校验再执行；
- 日志、错误、事件和诊断包使用统一的公开错误与脱敏合同。
