# Comic / Storyboard Studio

状态：当前。实现为作者候选，独立审查、红队及根分支组合验收由主任务执行。

`dbfox.comic` 提供可编辑的漫画页面与分镜工作台：页面、面板布局、镜头参数、角色视觉位置、对白、字幕和视觉注释。页面视图与分镜视图编辑同一份有版本的作品。角色使用可调整姿态的示意人形，适用于分镜规划；本版本不包含插画生成、导入照片或 Story 人物事实库。

从项目资源打开 Comic Studio，新建或选择作品。添加页面与面板，拖动移动或调整大小，方向键微调（Shift 加大步长），Escape 取消当前拖动。检查器支持对白、字号、说话角色、姿态、镜头与页面属性。先保存或取消草稿再执行其他修改。历史区域比较版本，或把旧内容恢复为新版本。选择对象后可交给 Agent。

项目菜单的查看入口通过公开 `onOpen` 直接进入作品库；文档引用通过已声明的 `objectKinds` 打开具名
作品标签。入口与 Dock 使用 Host 标准文档图标，不以字符符号充当图标。

导出工件通过 Host ActionRun 生成固定版本 Artifact；其页面预览、HTML 与 JSON 下载不会随之后的编辑改变。HTML 使用生产工作台相同的浏览器渲染器，不加载外部字体、网络资源或脚本依赖。HTML 中所有对白按纯文本处理。浏览器负责中英文和 emoji 排版；文字超过框内空间会在编辑预览提示，应放大对象或缩小字号。

角色名使用带白色描边的深色文字，保证深色分镜中的辨识度；工作台与导出共用此渲染规则。

## 公开边界

- 资源：`dbfox.comic.library`（Project ID）、`dbfox.comic.document`（Comic ID + 修订版本）。页、面板与元素是内部对象，不能扩大授权。
- 工具：原始八项 `page_create`、`panel_create`、`panel_layout`、`shot_set`、`character_place`、`bubble_create`、`caption_create`、`panel_reorder`，以及 `comic_create`、`comic_inspect`、`comic_diff`、`comic_undo`、`comic_delete`、`comic_export`、`note_create`、`element_update`、`page_reorder`、`object_delete`、`page_update`、`panel_update`。
- UI operations：`comics.list/get/diff/create/apply/undo/delete/artifact`。操作仅作用于实际 Project；写入必须提供 `request_id`，修改必须提供 `expected_version`。
- Artifact：`dbfox.comic.revision` schema 1。Representation：`dbfox.comic.document.v1`，支持固定 `summary/pages/page/export_json/export_html`。

完整合同、25 项设计依据、上限与恢复规则见 [Comic 架构](../../docs/architecture/comic-dlc.md)。示例为 [灯塔归途](examples/lighthouse.json)。固定 HTML 可以在浏览器打开或打印；不宣称所有矢量编辑器支持 SVG foreignObject，也不提供 PDF/PNG 生产导出接口。

## 验证

从仓库根使用已安装锁文件依赖的 Python：

```powershell
python -m pytest verification/tests/system/test_comic_dlc.py -q --tb=short
python -m verification.bench.capabilities.dbfox_comic --output <外部证据目录>
python -m pyflakes dlcs/dbfox.comic verification/bench/capabilities/dbfox_comic verification/tests/system/test_comic_dlc.py
python -m mypy --follow-imports=skip dlcs/dbfox.comic/backend --no-incremental
```

实际 Electron 作者夹具使用完整签名包、真实 Main/Preload/Sidecar 与 public operations；只将文件保存对话框目的地固定到隔离目录。先构建 `desktop` 的 `npm run build:electron-host`，再从仓库根：

```powershell
$env:DBFOX_COMIC_PYTHON='<已安装项目依赖的 Python 绝对路径>'
node verification/bench/capabilities/dbfox_comic/browser-launch.mjs <全新外部目录>
npx --yes --package @playwright/cli playwright-cli -s=comic-native attach --cdp http://127.0.0.1:19233
npx --yes --package @playwright/cli playwright-cli -s=comic-native run-code --filename verification/testkit/comic-native-ui.cjs
```

夹具固定本地端口 5187/19233；运行前确认未占用。Ctrl+C 关闭自己启动的 Electron 与 Vite；`--reuse` 保留同一已安装签名包和作品验证重启，不能用于验证更新源码。`DBFOX_COMIC_NARROW=1` 使用 Host 允许的 960×840 原生窗口。截图写入命令当前目录，运行 UI 证据脚本时应选择外部证据目录并传入脚本绝对路径。

作者证据与尚未通过的共享窄 Dock 布局问题见 [验收记录](../../docs/quality/comic-author-candidate.md)。本 DLC 新增生产依赖为零；标准浏览器 API 与项目既有 Python/Pydantic/SQLite 由现有锁文件及许可证管理。Konva 仅是调研探针，不打包。

2026-11-07 在当前根工作区使用签名包与真实模型，实际从 Story 两章制作一页三格、修订内容，并通过
编辑器调整两处字幕框与一处对白位置，并独立打开固定 v8 HTML 核验排版。模型任务仍发生输入
预算拒绝，当前在线请求已确认受余额不足限制，不能记为自主交付通过。
固定成果导出、冷启动恢复和对应共享链路修复的独立记录见[连续使用记录](../../docs/quality/continuous-product-use-20261107.md)。
