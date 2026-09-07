# 工作区窄窗与分栏验证

> 文档类型：验证证据
>
> 状态：当前
>
> 最后核验：2026-09-07
>
> 适用范围：ConversationWorkspaceLayout 作者修复；不代替独立验收。

## 根因与复用决定

原布局要求对话最少420px、Dock最少320px、分隔条8px。960px窗口扣除导航后只有696px；`react-resizable-panels` 可以自动将collapsible Dock缩成44px，而Host store仍为open，DLC只拿到约43px。

调查现有Host组件、WorkspaceDock卸载语义、库4.12.2随包TypeScript说明及[官方组件文档](https://react-resizable-panels.vercel.app/)。采用既有Panel动态min/max约束、标准ResizeObserver测实际stage；宽度模式为派生状态，不持久化。compact时保持Panel与内容树，仅对话为0且inert；宽屏非collapsible，拖动/键盘到320px停止。既有Host按钮是唯一收起入口。因此无需onResize→store→imperativePanel双向同步、包装层、新依赖或DLC分支。Core运行/权限/SDK没有变化。

## 实际Windows Electron作者矩阵

使用生产Main/Preload/EngineSupervisor、production renderer、原Host CSP和完整签名Game包。Main验证入口只在独占profile监听白名单window-size.json并调用真实BrowserWindow.setSize；记录getBounds，renderer测量实际innerWidth；没有viewport emulation。外窗高度受Windows缩放舍入，getBounds记录901，renderer实际900。Renderer5196/CDP19246，未使用其他任务端口。

| 场景 | 实测 | 结果 |
| --- | --- | --- |
| 960、导航264、Dock开 | stage696.01、Dock696.01、对话0 | compact、无separator |
| 1440、导航264、Dock开 | stage1176、Dock654.08、对话513.92 | split恢复 |
| 960、收起导航 | stage912、Dock484、对话420 | 同外窗恢复split |
| 宽屏键盘End | Dock320 | 不错误collapse |
| End后ArrowLeft | Dock379.60 | 键盘可扩大 |
| 宽屏拖到最右 | Dock320 | store和完整Dock保持open |
| 960、Dock关闭 | Dock44、对话675.99、stage719.99 | 对话与展开入口可达 |
| 960、全屏 | 退出按钮x896/width28 | 退出及全屏收起均成功 |

`Unsaved layout draft`从960→1440→960→收导航→展开导航→全屏退出→宽屏键盘和拖动均保留。测试结束主动放弃草稿后测试收起/展开；不声称Host既有关闭或切标签卸载可保留草稿。所有采样document.scrollWidth等于innerWidth，Studio自身scrollWidth不超过clientWidth。真实截图：[窄窗和草稿](../images/game/host-960-open.png)、[宽屏最小Dock](../images/game/host-wide-drag-min.png)。机器测量在 `verification/testkit/game_studio/evidence/host-layout.json`。

新增React回归通过真实组件验证stage变化、conversation accessibility、separator显隐和草稿组件不重挂载。生产build及typecheck:test通过。全量ESLint零error、5个既有warning；设计合同检查受本工作树未复制的根Story既有dirty CSS修复影响，失败均为Story命名空间/影子令牌，未改这些他人文件。菜单首次打开观察到已有Radix style-src-elem CSP拒绝（操作仍成功）；本补丁不放宽CSP、不把其列为已修。

## 复验入口

`browser-launch.mjs`可通过GAME_QA_RENDERER_PORT、GAME_QA_CDP_PORT选择独立端口。`browser-electron.mjs`在任务profile接收JSON `{ "width": 960, "height": 900 }`，仅允许960/1024/1440宽和900高，输出window-bounds.json。生产Main、renderer IPC未暴露该能力。

用Playwright CLI附着真实Electron：`playwright-cli -s=<session> attach --cdp=http://127.0.0.1:<port>`。每阶段运行 `--raw run-code --filename=verification/testkit/game_studio/browser-host-measure.cjs`，该脚本只读取DOM并断言布局。用现有UI切导航、全屏、工作区收起和separator键盘/拖动。任务结束点击应用“关闭”，所有测试控制面随此进程退出。
