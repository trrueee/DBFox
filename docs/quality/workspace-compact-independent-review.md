# 工作区 compact 与 Game 定位补丁独立审查

> 文档类型：独立审查
>
> 状态：当前
>
> 最后核验：2026-09-07

收尾记录：下文保留对原候选的独立发现。Root 随后以 `809fa7ea` 修复生产 TSX 测试排除范围，实际 `npm run build`、`npm run typecheck:test`、`npm run lint` 通过（5项原有 warning），两文件4项定向测试通过。真实 Electron 960/1440、导航、未保存草稿、20次Tab、320px键盘/拖动最小宽及Artifact→具体Game/狐狸返回验证通过，见 [原生收尾](game-independent-native.md#ui修复后的独立收尾)。原构建P1在该修订后关闭，不覆盖原失败证据。

独立角色：/root/host_fix_review。作者树：D:/Project/DBFox-worktrees/creative-game-host-fix。只读检查 8ebcf96b..60456cf9（4e21185c、60456cf9），未修改产品或共享 Git index，未启动原生应用。Root 另行执行实际 Electron 复验。

结论：架构与实现范围可接受，但原候选不能直接接受合入：新增 TSX 测试进入生产类型检查，造成生产构建门禁失败。修正生产测试文件排除边界并通过生产构建、测试类型检查，以及完成 root 的独立原生复核后，可对这两个补丁作限定验收；不代表 Game DLC 全部验收。

## 确认问题

P1 — 生产 tsconfig 未排除新增 TSX 测试。desktop/tsconfig.app.json 的 include 为 src，exclude 只有 **/*.test.ts 与 **/*.test.mjs。新增 dbfoxGameNavigation.test.tsx 导入 node:fs/promises、node:path 并使用 process、Buffer，生产配置只有 vite/client 类型。独立运行 `npx --no-install tsc -p tsconfig.app.json --noEmit` 返回 1，得到上述四处 TS2591。Root 的实际 npm run build 同样失败，作者文档“生产 build 通过”不能用于该候选的当前门禁结论。

修正方向：生产 tsconfig 的既有 exclude 增加 src/**/*.test.tsx。测试仍由 tsconfig.test.json 的 exclude:[]、Node/Vitest 类型检查。无需给产品加入 Node 类型或删除测试。该修正与其重验由 root 负责；本报告生成时尚未验证修正后版本。

## 实现与边界审查

- Game create/selection 使用既有 dockViews.open 打开 projectId + gameId 定义的具体作品 viewKey。target.object 与 authority 都保持 dbfox.game.project、相同 Game UUID。选中实体/场景只进入 DLC 私有 locator，未把子对象误当成独立授权资源，也未新增工具执行或授权路径。实际写操作仍调用既有 games.apply，传固定 game_id、expected_version 和 request_id。
- 原 Host workspaceStore 依 viewKey 更新已有标签；具体作品标签切换受 key={tab.viewKey} 与 Studio 的作品/工作台 scope key 隔离。Game 的 select 在本地更新选择并把主对象位置写入 Host 标签；从 Artifact 返回时初始状态由 locator 重建，读取后对实体存在性进行筛选并选择所属场景。库内创建/选择不再只依赖会随 editor 卸载丢失的 gameId 本地状态。未新增镜像 store。
- Locator 在此补丁中是 Game Studio 自己写入并恢复的主选择位置。没有新增通用外部 locator 导航协议；不能据此宣称任意其它来源的 locator 更新或多选集合都可恢复。表单草稿仍遵循既有关闭/切标签卸载语义。
- Host 根据 stage 实际 DOM 宽度派生 compact，而非外窗宽度；ResizeObserver 可覆盖导航栏改变 stage 宽度但外窗不变的情况。阈值 420+8+320 对应现有对话最小宽、真实 separator CSS 宽和 Dock 最小宽。
- compact/open 时对话 min/max=0，Dock min/max=100%；对话 inert + aria-hidden。compact/closed 时对话 min=0、Dock 固定44；wide/open 时对话 min420、Dock min320/max56%；wide/closed 时 Dock 固定44。宽度达到748时可同时满足两侧最小宽及8px separator。内容和 Panel 位置不变，仅 separator 条件显示，不为布局切换重建 DLC 状态。
- 阅读已安装 react-resizable-panels 4.12.2 的官方包 README 和实际 dist：数值尺寸为像素、百分号字符串为相对尺寸；Panel 约束变化在注册依赖内重新计算；preserve-pixel-size 允许 min/max 限制，且对话 Panel 保留默认 preserve-relative-size，满足库要求。Group elementRef 由既有 wrapper 正确转发。
- 初始 compact=false；useLayoutEffect 立即测实际正宽并更新，ResizeObserver 处理后续测量。零宽阶段被忽略，后续正宽可恢复，没有一次性只读 window.innerWidth 的过期状态。实际浏览器在首次异步注册/测量中的瞬时布局、焦点和渲染时序应由 root 原生复验确认，JSDOM 不能证明像素结果。
- 宽屏恢复是重新形成可调整分栏；并不保证精确恢复 compact 前的拖动像素或比例。原生全屏/关闭按钮与 fullscreen state 保留在原 WorkspaceDock；作者证据记录其成功，但本只读审查不将作者录像/测量算作独立执行。

## 独立验证

命令：`npm test -- --maxWorkers=1 src/features/appShell/__tests__/ConversationWorkspaceLayout.test.tsx src/features/appShell/__tests__/WorkspaceDock.test.tsx src/features/dlc/__tests__/dbfoxGameNavigation.test.tsx src/features/dlc/__tests__/extensionHost.test.ts src/stores/__tests__/workspaceStore.test.ts`。

结果：5 个文件、40 项通过，7.63 秒。覆盖 stage 改变、首测打开/关闭、可访问隐藏、separator 显隐、不卸载草稿，及既有 Dock 状态/标签和 extension host 注册边界。Game fixture 输出一条 React child key warning；测试通过不代表该警告已修复，也不代表真实 Phaser 运行。

另独立执行上述生产 tsc 命令，4.67 秒确认失败。没有重复全量测试、改依赖或启动原生窗口。

## 明确未测范围

本角色未执行实际 Electron 像素/拖动/键盘/全屏、DPI 跨屏变化、加载首帧截图、屏幕阅读器或长时 ResizeObserver 行为；这些不能由 mocked DOMRect 的 React 测试替代。未审查完整 Game backend 权限安全或完整 Phaser 运行质量。本候选没有新增 Core 运行时、SDK、数据库合同、依赖、兼容层；不以此推定所有 Creative DLC 达标。

参考材料：作者 docs/quality/workspace-compact-layout-verification.md、verification/testkit/game_studio/evidence/host-layout.json；已安装官方 node_modules/react-resizable-panels/README.md 与 dist 实现。没有将作者通过声明覆盖本轮实际构建失败。

## 追加：compact 的 inert DOM 层级（2026-09-07）

Root 实际 Electron 观察到 `.app-conversation-panel.inert === false`，请求本角色只读核对。已在独立验证树检查同版本库实际产物：Panel 的外层 div 接收 `...z`（含 inert/aria-hidden）、id、data-panel；className 则放在内层 div。故 `.app-conversation-panel` 是内层，读取其自身 inert 属性为 false 不等于缺少祖先 inert 约束。产品传参正确进入外层 `#conversation-workspace-panel`，不存在源码上丢弃/覆盖 inert 的问题。

建议原生取证使用 `document.getElementById('conversation-workspace-panel').inert` 和 `.app-conversation-panel.closest('[inert]')`，再观察真实 Tab 是否进入该子树。无需因内层自身属性为 false 添加 wrapper 或重复设置 inert。此角色没有操作窗口；真实 DOM 与键盘结果仍由 root 记录。
