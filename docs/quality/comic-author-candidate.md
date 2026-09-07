# Comic 作者候选验收记录

> 文档类型：质量证据
>
> 状态：当前
>
> 最后核验：2026-09-07
>
> 适用范围：creative/comic 作者验证；不是独立审查或发布结论

## 验证范围

在 `D:/Project/DBFox-worktrees/creative-comic`（基线 `dffeb603`）实现完整 `dbfox.comic`。原有用户 dirty baseline 未修改。生产新增依赖为零；没有 Core/SDK 修改。实现、公共界面和 25 问合同见 [架构](../architecture/comic-dlc.md)，操作说明见 [README](../../dlcs/dbfox.comic/README.md)。

| 门禁 | 作者结果与限制 |
| --- | --- |
| Comic 后端 | 24 passed（最后一次 8.00 秒）：canonical/restart/exact receipt/reconcile、八工具、非法输入/引用、CAS 并发、提交前取消、no-op/undo/delete、ID 不复用、历史分页/diff/Project 隔离、链/hash/producer 损坏、真实 ToolRuntime 授权、固定 Artifact、签名完整包停启；4096 元素与 diff offset>4096、128 页和文字上限。 |
| Capability benchmark | 13/13，完整签名 DLC + 实际默认 `build_product_run_loop`，仅模型输出 scripted；默认 32768 未改变。最终连续压力含澄清结束第一个 Run、明确回答启动第二个 Run，15 次工具调用；prompt 峰值 20490。 |
| Python 静态检查 | Comic backend mypy 6 文件通过；Comic/backend/bench/test pyflakes 通过。 |
| JS 语法 | `node --check` index.js/render.js 通过。 |
| Electron Host 构建 | `npm run build:electron-host` 通过，未修改 Main/Preload。 |
| 工程合同 | 44 passed / 1 failed：既有 Visualization vendor manifest 796160 bytes，对比当前 Windows checkout 796175 bytes。HEAD blob=796160、CRLF=15，换行归一后完全一致；不是 Comic 变更，未改该文件。 |
| 独立 reviewer / adversarial | 未执行，由主任务安排。 |
| 当前根 Host 多 DLC 组合 | 未执行，不用单 DLC scripted 分数替代。 |
| 原生 960px 非全屏 Dock | 失败，详见下文。 |

## 真实原生路径

夹具是签名完整 `dbfox.comic` + 真实 Electron Main/Preload/EngineSupervisor + FastAPI Sidecar + Project-scoped operations + Artifact ActionRun。工具 runtime 和 operations 没有前端 stub。为了自动验证文件下载，只把 Electron 的系统保存对话框目标固定到隔离 runtime/downloads；HTML/JSON 仍经原生产 Representation stream、Blob 与下载链接。

最终产品代码对应原生隔离目录 `D:/Project/DBFox-worktrees/creative-program/comic-native-author-3`，已安装包 digest 为 `64712877e30b8d1211727b2d5855e9dc11ec3f4963a9a723ed9c5003edb58b97`。之后只增加 README/设计/作者证据与验证夹具，产品 backend/frontend/manifest 未再修改。最终完整 benchmark 签名包的 digest 仍为同一值，确认可执行 payload 一致。

可复验源脚本：`verification/testkit/comic-native-ui.cjs`；夹具入口在 `verification/bench/capabilities/dbfox_comic/`。作者实际完成：

1. 打开两页四面板“灯塔归途”v3，在对白编辑器输入中文和显式换行，保存到 v4。
2. 导出并打开真实固定 v4 Artifact；两页预览加载正常，无业务 alert。
3. 返回作品 tab（Host 带资源 authority 的稳定作品 ID），方向键移动到 v5，鼠标拖动到 v6。
4. 分镜视图编辑同一角色到 v7；页面属性修改到 v8。
5. v4 工件仍显示旧页名与旧内容；第二页切换正常。
6. 历史区域比较 v4/v8 并恢复为新 v9。
7. 在 v9 拖动过程中 Escape，然后 mouseup；等待被动刷新，仍为 v9。切换 resize 完成一次拖动产生 v10。
8. 选择对象后“交给 Agent”调用公开 onAsk，未触发模型运行或付费调用。
9. v9 的 HTML 与 JSON 实际写入隔离 downloads，分别 8254/3002 bytes；HTML 在独立浏览器经本地只读静态服务器重开，两个页面由同一生产 renderer 渲染。浏览器唯一 console error 是缺省 favicon.ico 404，页面脚本没有错误。JSON/HTML 内容固定 v9。
10. 关闭自己启动的进程后，同一 runtime `--reuse` 重启，作品 v9 和历史工件保留；没有重新运行 UI 编辑请求。

原生 renderer console：0 errors、1 条开发环境 Electron CSP warning。不要把开发 warning 当作已打包生产安全检查结果。

## 截图与可重开 Artifact

以下均在 `D:/Project/DBFox-worktrees/creative-program/`，作者已打开逐张核对：

- `comic-native-storyboard.png`：宽窗口原生分镜，镜头卡片与角色/对白检查器，v7。
- `comic-native-artifact-v4.png`：固定 v4 的第二页，后来修改未覆盖历史。
- `comic-native-960-dark.png`：真实 960×840 原生窗口、工作区全屏、深色；Comic clientWidth/scrollWidth 均 960。
- `comic-native-narrow-dark.png`：真实 960×840 非全屏失败证据，不能列为通过截图。
- `comic-export-reopened.png`：实际下载 HTML 的浏览器重开。
- `comic-renderer-probe.png`：HTML/Konva 中英文/emoji 实测。
- `comic-native-author-3/downloads/comic-comic-75756a0ff459492bbeae93b8d398474d-v9.html` 和同名 `.json`：真实下载文件。
- `comic-bench-author-final-2/`：最终 README 已包含的完整签名包 13 case 作者报告；其 package digest 记录在 trials.json。

截图中的角色是分镜占位人形，不是生成插画。作品内容和 UI 字体均可读，页面有滚动容器；截图不声称展示整个作品的全部页面。

## 未决：共享 Host 窄 Dock 布局

960px 窗口下，主导航展开、聊天首页和右 Dock 同时存在时：document scrollWidth=960；workspace stage width=696、x=264；Dock 的 Resizable child width=44、x=916、flex=`6.395 1 0px`；workspace-dock clientWidth=43/scrollWidth=72；tabpanel/body-slot/dlc-slot/Comic 实际宽度均约 43.333px，Comic scrollWidth=125。这使内容无法正常编辑。

工作区全屏时同一窗口与同一包可正常显示，Comic clientWidth=scrollWidth=960。作者尚不能据此确定共享布局根因，也不能假定根分支修复过通用 Host 问题。主任务已安排独立只读定位；不在 Comic 中强制改 Host width、不覆盖共享布局规则。当前根 Host 非全屏窄窗必须继续复验。

## 作者边界与剩余门禁

没有真实模型创作质量评估、第三方矢量软件兼容测试、PDF/PNG 生产导出或 GPU 渲染。未知未来数据库 schema 明确拒绝；当前无旧 Comic schema 迁移需求。Project 删除后缺公共 data-GC hook，遗留数据保持不可重新授权，见架构第 17 问。尚未保存的 view 草稿不跨视图卸载持久化。

独立验证应重点攻击：full artifact producer/authority、跨 Project 与停启的迟到响应、no-op 回执/容量、写后断线 reconcile、Host 窄 Dock、真实 Agent 与直接编辑交错。主任务安排独立 reviewer 和红队后才能发布，不以本作者自测替代。
