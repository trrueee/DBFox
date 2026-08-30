# 桌面 UI 全面改造与 Harness 边界审计证据

> 文档类型：质量与发布证据
>
> 状态：当前
>
> 最后核验：2026-08-30
>
> 适用范围：桌面渲染层视觉系统、侧栏导航、模型服务、项目资源清单、Harness 边界

## 改造范围与提交

本记录覆盖 `bae0c37d..b238ca5d` 区间的桌面端改造，按主题分九批提交：
视觉 token 系统与共享原语（`c5e8208e`）、项目分组侧栏与安静壳层（`c992b58f`）、
安静时间线与工具行（`780ae38c`）、合同测试刷新（`7827347e`）、引擎 evidence/
模型列表合同（`2dee1ba2`）、DLC 打包工具（`5d3347a4`）、动态多厂商模型目录
（`96b8e50f`）、项目资源清单合同（`117361f8`）、桌面打包与工具更新
（`ffbcfca2`），以及 Harness 边界审计修复（`984607cd`、`b238ca5d`）。

## 验证结论

- 前端：94 个测试文件 / 468 个测试全部通过（Vitest，`--maxWorkers=1`）。
- 静态检查：`typecheck:test`、ESLint、`check-design-contracts.mjs` 零错误。
- 构建：入口 616,408 B（raw）/ 185,159 B（gzip），低于 650 KB / 200 KB 预算。
- 后端：`test_agent_api.py` + `test_agent_results_api.py` 共 14 项通过；
  `pyflakes` 与 `mypy` 对改动文件零告警。
- DLC：设计合同检查通过；`dbfox.data` / `dbfox.workspace` / `dbfox.github`
  前端 `node --check` 语法校验通过；`prepare_dev_system_dlcs` 重新签名成功。
- 视觉走查：浏览器双主题截图覆盖主页、会话时间线、设置、命令面板、项目管理页。

## 关键边界决定

- **证据语义**：DLC 在创建工件时以 `visibility = "primary"` 声明；Harness 的
  时间线保留/结果面板仅按 visibility 与载荷形状（`rowCount`）过滤，不枚举
  能力私有类型名。见 `architecture/runtime-dlc-platform.md` 的 Evidence Semantic 行。
- **SDK 导入门**：渲染层只允许经六个领域门导入 `sdk/frontend` 合同类型；
  `src/__tests__/sdkImportDoors.test.ts` 以 allowlist 守卫。
- **模型动态获取**：渲染层 CSP 不直连厂商；`POST /api/v1/agent/llm/models`
  由引擎代理访问 `/models`，凭据经租约机制，原始 Key 不回传。
- **资源清单**：`listResources` / `removeResource` 为 connector 可选钩子；
  Core 渲染清单框架，数据与移除语义归 DLC（数据/工作区/GitHub 已接入）。

## 已知边界（非缺陷）

- 网页开发预览（Vite）不装载 DLC 前端：扩展资源走 Electron 专有
  `dlc-asset://` 协议；DLC 界面（数据表格、SQL 控制台、连接管理）需在
  `npm run electron:dev` 下走查。
- 现有用户本地保存 `neutralTone: "neutral"` 时继续使用经典中性灰；
  仅新默认（`cool` 冷灰蓝）面向新配置。
