# DBFox Desktop

`desktop/` 包含 DBFox 的 React 工作区和 Tauri/Rust 桌面宿主。Rust 是生产 Sidecar 生命周期、端口、Token 与 generation 的唯一权威；React 不自行启动或猜测引擎配置。

## 当前技术栈

| 层 | 实现 |
| --- | --- |
| UI | React 19、TypeScript、Radix UI、Tailwind CSS |
| 状态与数据 | Zustand、TanStack Query/Table/Virtual |
| 图表与关系图 | ECharts、XYFlow |
| 构建 | Vite、Tauri 2、Rust 1.95 |
| 桌面插件 | `tauri-plugin-shell`、`tauri-plugin-log` |
| 测试 | Vitest、React Testing Library、axe、jsdom、Cargo test/clippy |

仓库当前不依赖 Monaco 或 Playwright，也没有 `test:e2e` 脚本。

## 安装与开发

```powershell
Set-Location desktop
npm ci
```

完整开发环境优先从仓库根目录启动：

```powershell
./dev.ps1
```

只启动前端开发服务器：

```powershell
Set-Location desktop
npm run dev
```

此模式要求 FastAPI 引擎已启动。开发环境默认使用 `127.0.0.1:18625`，并由根目录开发脚本生成一次性 Token。不要手工维护 `desktop/.env.local`。

运行完整 Tauri 开发模式：

```powershell
Set-Location desktop
npm run tauri -- dev
```

生产安装包不依赖固定端口：Tauri 启动 Frozen Sidecar 后，通过 IPC 向前端提供当前端口、Token、generation 和 Host 状态。

## 目录边界

```text
desktop/
├─ src/
│  ├─ App.tsx                 # 应用组合与懒加载边界
│  ├─ components/             # 共享 UI 基件
│  ├─ features/
│  │  ├─ appShell/            # 桌面工作区外壳
│  │  ├─ assistant/           # Agent 交互与运行投影
│  │  ├─ conversation/        # 会话与消息
│  │  ├─ datasource/          # 数据浏览工作区
│  │  ├─ datasource-management/
│  │  ├─ settings/
│  │  └─ workspace/
│  ├─ lib/                    # Transport、API、查询与通用工具
│  ├─ stores/                 # Zustand 客户端状态
│  ├─ styles/                 # 全局 token 与样式
│  ├─ test/                   # 测试基础设施
│  └─ types/                  # 生成类型与本地类型
├─ src-tauri/                 # Runtime Supervisor、命令、ACL、打包配置
├─ package.json
└─ package-lock.json
```

## 运行时合同

- 前端经统一 Transport 发送 authenticated HTTP，并通过 SSE cursor/snapshot 恢复事件。
- Runtime generation 变化后，旧端口和旧 Token 失效；非幂等请求不会自动重放。
- FastAPI 错误以 RFC 9457 Problem Details 呈现，UI 不直接展示未分类异常文本。
- Tauri capability/ACL 是桌面权限事实源；不要添加第二套 Sidecar 启动方式或 shell fallback。
- OpenAPI 类型由引擎合同生成；不要直接编辑生成文件。

重新生成 API 类型：

```powershell
Set-Location desktop
npm run generate:api
```

## 可用脚本

| 命令 | 用途 |
| --- | --- |
| `npm run dev` | Vite 前端开发服务器 |
| `npm run build` | TypeScript 检查并构建前端 bundle |
| `npm run lint` | ESLint |
| `npm run typecheck:test` | 测试 TypeScript 合同检查 |
| `npm test -- --maxWorkers=1` | Vitest 单元/组件测试 |
| `npm run test:watch` | Vitest watch 模式 |
| `npm run test:rust` | Tauri Rust 测试 |
| `npm run test:sidecar` | 已构建 Frozen Sidecar smoke |
| `npm run check:bundle` | 生产 bundle 内容合同检查 |
| `npm run tauri -- dev` | 完整桌面开发模式 |
| `npm run tauri -- build` | 构建平台安装包 |

## 提交前检查

```powershell
Set-Location desktop
npm run lint
npm run typecheck:test
npm test -- --maxWorkers=1
npm run build
npm run test:rust
```

涉及 Runtime、Token、capability、Sidecar 或发布配置时，还必须执行对应的 Rust、Frozen Sidecar 和真实安装态门禁。Windows 结果不能替代 macOS/Linux 的真实平台证据。

更多内容见[根 README](../README.md)、[前端架构](../docs/architecture/frontend.md)和[工程质量与发布门禁](../docs/quality/engineering-gates.md)。
