# DBFox Desktop

> 状态：Current
>
> 最近更新：2026-08-21

`desktop/` 是 DBFox 的桌面客户端：React 负责工作区与交互，Electron Main/Preload 负责原生窗口、最小系统能力和 Sidecar 生命周期。业务 API、Agent 与数据库工具仍由 Python Sidecar 提供。

项目总览见根目录 [`README.md`](../README.md)，全局开发流程见 [`CONTRIBUTING.md`](../CONTRIBUTING.md)。

## 技术栈

- React 19 + TypeScript
- Vite 8
- Electron + TypeScript
- TanStack Query / Table
- Zustand
- Radix UI
- 项目内轻量 SQL 编辑器
- ECharts
- Vitest + Testing Library

## 职责边界

| 层 | 负责 | 不负责 |
| --- | --- | --- |
| React | 工作区、交互状态、HTTP/SSE Transport、结果与错误呈现 | Sidecar 进程真相、凭据持久化、业务数据访问 |
| Electron Main/Preload | 原生窗口、窄化 IPC、Sidecar 启停与 generation、短期 Runtime Token、系统凭据库 | Agent 业务策略、第二套 HTTP Client 或 SQL 执行链 |
| Python Sidecar | API、会话、Agent、工具、SQL 安全、结果制品和耐久事件 | 桌面窗口生命周期与长期保存明文秘密 |

关键合同：

- TypeScript `EngineSupervisor` 是 Sidecar 生命周期的唯一权威。
- 前端只通过正式 Transport 使用当前 generation 的 endpoint 与 token。
- Runtime 刷新只重试明确安全的请求；非幂等请求不会自动重放。
- SSE 使用 cursor/snapshot 恢复，不以组件内存作为事件事实来源。
- Renderer 保持 sandbox、context isolation 和禁用 Node；只通过具名 preload 方法访问系统能力。

详见 [`docs/architecture/frontend.md`](../docs/architecture/frontend.md) 和 [`docs/architecture/runtime-foundation-decisions.md`](../docs/architecture/runtime-foundation-decisions.md)。

## 本地开发

要求 Node.js `>=22.18.0`（以 [`package.json`](package.json) 的 `engines` 为准）。完整桌面开发和打包不需要 Rust 工具链。

```powershell
Set-Location desktop
npm ci
```

仅运行前端开发服务器：

```powershell
npm run dev
```

运行完整桌面应用：

```powershell
npm run electron:dev
```

也可以从仓库根目录运行 `dev.ps1`，同时启动前端和 Python API 开发服务。

## 常用命令

| 命令 | 用途 |
| --- | --- |
| `npm run dev` | 启动 Vite 开发服务器 |
| `npm run build` | TypeScript 检查并构建前端产物 |
| `npm test -- --maxWorkers=1` | 运行前端测试 |
| `npm run lint` | 运行 ESLint |
| `npm run typecheck:test` | 检查测试与测试辅助类型 |
| `npm run test:electron` | 运行 Electron Main/Preload 合同测试 |
| `npm run electron:dev` | 启动 Electron 开发应用 |
| `npm run electron:package` | 构建当前平台候选安装包 |
| `npm run electron:release` | 构建 Frozen Sidecar 和候选安装包 |

完整质量门禁见 [`docs/quality/engineering-gates.md`](../docs/quality/engineering-gates.md)。

## 目录结构

```text
desktop/
├── src/
│   ├── components/       # 页面与可复用 UI
│   ├── hooks/            # 交互和数据流 hooks
│   ├── lib/              # Transport、查询与共享基础能力
│   ├── stores/           # 客户端交互状态
│   ├── types/            # 前端权威类型
│   └── test/             # 前端测试基础设施
├── main/                 # Electron Main、EngineSupervisor 与原生能力
├── preload/              # sandboxed renderer 的窄化 bridge
├── build-resources/      # 平台图标资源
├── package.json
└── vite.config.ts
```

## 修改前端时

- 优先复用现有组件、设计 token、TanStack 与 Radix 能力，不创建重复 UI 基础设施。
- 颜色、字号、圆角和语义状态应使用现有 token；组件 CSS 主要表达布局与局部行为。
- API 类型和运行时数据必须服从正式合同，不能在 UI 中添加字段猜测、静默 mapper 或旧协议 fallback。
- 任何 Runtime、Token、SSE、工具审批或非幂等行为变更，都需要相应合同测试。
- 测试辅助、开发 Token、本地日志、安装包和生成二进制不得进入生产源码提交。
