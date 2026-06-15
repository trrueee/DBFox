# DataBox Desktop

基于 **React 19 + TypeScript + Vite + Tauri** 构建的本地数据库工作台桌面客户端。

## 技术栈

| 层 | 技术 |
|---|---|
| 框架 | React 19, TypeScript |
| 构建 | Vite (dev), Tauri (desktop bundle) |
| UI | Radix UI, Tailwind CSS |
| 编辑器 | Monaco Editor |
| 图表 | ECharts, XYFlow (ER 图) |
| 测试 | Vitest, React Testing Library, Playwright (E2E) |

## 快速开始

### 1. 安装依赖

```bash
cd desktop
npm install
```

### 2. 启动开发模式

**浏览器模式**（纯前端开发，需要后端已启动）:

```bash
npm run dev
```

**Tauri 桌面模式**（完整桌面应用）:

```bash
npm run tauri dev
```

Tauri 是主要的桌面交付路径。`start.py` 和 `run_desktop.py`（仓库根目录）为遗留启动器，仅供快速体验。

### 3. 后端引擎

桌面客户端需要 DataBox 引擎后端运行在 `http://127.0.0.1:18625`。

```bash
# 在仓库根目录
pip install -r requirements.txt
python -m engine.main --reload
```

## 项目结构

```
desktop/
├── src/
│   ├── main.tsx          # 应用入口
│   ├── App.tsx           # 根组件 (workspace/tab router)
│   ├── features/         # 功能模块
│   │   ├── agentTask/    # Agent 任务流
│   │   ├── chat/         # 对话面板
│   │   ├── datasource/   # 数据源管理
│   │   ├── engine/       # 引擎 API 层
│   │   ├── query/        # SQL 编辑器 & 结果
│   │   ├── schema/       # Schema 浏览器
│   │   └── ...
│   ├── components/       # 通用 UI 组件
│   ├── lib/              # 工具库, API client
│   └── hooks/            # 通用 hooks
├── src-tauri/            # Tauri (Rust) 桌面壳
├── package.json
├── vite.config.ts
└── tsconfig.json
```

## 测试

```bash
npm test              # 单元测试 (Vitest)
npm run test:e2e      # E2E 测试 (Playwright)
npm run lint          # ESLint
npm run build         # 生产构建
```
