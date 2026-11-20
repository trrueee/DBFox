# 电脑工作台实现与验收

> 文档类型：质量与发布证据
>
> 状态：当前
>
> 最后核验：2026-11-18
>
> 适用范围：Windows 11 x64，本机普通交互桌面；源码、Frozen Sidecar、Electron 与本地视觉模型

## 实际交付

在已有通用文件和托管执行底座上，增加 Host 电脑目标授权、Windows UIA 窗口观察与输入、
独立 Edge 浏览器、原生模型图片输入、逐次操作审批、截图/操作成果、HTTP API 和对应工作台。
新任务和已有对话均可进入；默认仅观察，控制需要明确选择，支持期限、重选、停止与结束共享。

前端沿用现有 Apple 设计令牌、字体、图标、Radix 和 Dock；增加分段选择、权限卡、实际状态、
浏览器地址与页面、带采集时间的预览、审批详情、成果视图和固定接管入口。没有新增 Agent
循环、Job 数据库、审批系统、供应商分支或前端耐久执行状态机。决定与限制详见
[架构](../architecture/computer-use.md)及[交互合同](../specs/computer-workbench.md)。

## 分层验证

以下结果分别记录，不将重复集合相加，也不将脚本模型边界当作真实模型。

| 验证 | 结果 | 本机记录 |
| --- | --- | --- |
| System 确定性回归，排除外部/迁移/工程/平台 markers | 1,347 通过，143 排除 | `.tmp/computer-system-regression-02.log` |
| Agent Core 确定性回归 | 379 通过，2 排除 | `.tmp/computer-core-regression-02.log` |
| 迁移与工程合同 | 85 通过 | `.tmp/computer-migrations-06.log` |
| 最后改动的构建/manifest/授权/取消/媒体回归 | 53 通过 | `.tmp/computer-final-targeted-07.log` |
| Edge 与 Win32 真实平台合同 | 5 通过 | `.tmp/computer-platform-final-10.log` |
| 前端完整串行回归 | 772 通过，123 文件 | `.tmp/computer-frontend-final-09.log` |
| Electron Main/Preload | 40 通过，13 文件 | `.tmp/computer-electron-tests-final.log` |
| 生产 Python pyflakes / mypy | 无错误；mypy 269 源文件通过 | `.tmp/computer-pyflakes-final.log`、`.tmp/computer-mypy-final.log` |
| 前端 lint / 测试类型 / 生产 build | 通过；lint 保留 20 条已有警告，无错误；入口 gzip 约 121 kB，预算与生产 Token 检查通过 | `.tmp/computer-lint-final-10.log`、`.tmp/computer-typecheck-final-10.log`、`.tmp/computer-electron-package-final-05.log` |
| Frozen 真实窗口和新建空白浏览器 | 两个实际 PNG、独立 profile、停止后均 paused、继续预览 409 | `.tmp/computer-frozen-probe-07/proof.json` |
| 最终 Frozen Data / Artifact / 恢复 / DLC 生命周期冒烟 | 通过 | `.tmp/computer-sidecar-smoke-final.log` |
| 最终 Electron Host / Preload / 五个系统 DLC / 资产 403 与加载 | 通过 | `.tmp/computer-electron-smoke-final-05.log` |

平台测试的 RunLoop 用例只替换模型传输边界，实际使用生产装配、正式工具、三次 Approval、
真实 Edge 与图片；逐次对照 Artifact 图片 SHA-256，数据库 Context/Observation 不保存 base64。
取消屏障测试使用合成驱动验证停止时序，本身不证明 OS 输入。真实窗口测试另验证独立文件
结果、字面量输入、实际 UIA 和停止后拒绝操作。

## 真实本地模型

使用已安装的 `qwen3.5:9b-q4_K_M` 和视觉投影，不调用付费 API，原有默认 4B 配置未修改。
生产 RunLoop 在全新专属浏览器中访问本机夹具；任务要求读取 canvas 中的随机文字、填写、
点击保存、观察成功状态并交付截图。随机文字不进入用户任务、DOM 文本或元素名称。
独立 HTTP 服务器核对实际提交值，测试仅为此目标及有限动作解决正式 Approval。

最终记录 `.tmp/computer-real-model-05/`：一次任务输入、三次审批、零次修复，70.35 秒；
实际提交 `FOX-706`，独立校验为真，Run completed，最终 completion_disposition 为 complete，
交付选择 `artifact_23a12c43e3f4445ba776510293173b48`，保留三张实际 PNG 与结构化证据。
这证明此本机夹具任务成功，不代表任意网页/桌面任务的通用成功率或不同模型的能力。

## 桌面交互核验

用本轮 `win-unpacked/DBFox.exe`，独立 Electron 用户配置与运行目录，实际检查：

- 新任务点击“电脑”建立草稿但不发送；目标、仅观察/控制、期限与目标过期提示可见。
- 新建浏览器采用单独 profile 和空白页，活动状态与地址、停止、旧图移除及重启中断一致。
- 只选择本次唯一标题的 Win32 夹具；面板实际显示编辑框、按钮和状态的 PNG，采集时间可见。
- 浅色、深色、约 340 px 的窄 Dock，目标状态和按钮换行；顶部停止入口保持可用。
- `Ctrl+Alt+Shift+Esc` 实际触发 Host 认证停止请求，面板随后显示已停止，旧预览被移除。
- 后端未确认时保留错误，不提前显示成功。恢复面板的共享成功反馈与跨对话输入隔离另有回归。

这里只操作专用夹具和空白浏览器，没有拿用户其他应用内容充当测试数据。

## 验收中修复的问题与环境影响

1. 所有者资源发现不应再次查询另一份 Session 存在性；删除重复门槛，保留实际读取/副作用的
   对话校验。初次 System 回归的十处 Conversation/附件失败已修复，完整重跑通过。
2. 浏览器启动的 DevToolsActivePort 可能暂时被锁或尚未写完；只在启动就绪边界等待有效内容，
   不重放点击/输入。初次本地模型启动失败保留在 `.tmp/computer-real-model-01/`。
3. 原生可执行路径使用 Win32 官方 QueryFullProcessImageNameW；Frozen 的 GetProcessTimes
   另动态导入 win32timezone，已在构建边界显式收集，并在发布探针实际执行身份原语。
   依据 [PyInstaller 官方 hidden-import 说明](https://pyinstaller.org/en/latest/when-things-go-wrong.html#listing-hidden-imports)。
4. 桌面 CSP 起初遗漏临时 Blob 图片地址，HTTP 成功但预览破图；修复 img-src 并测试
   script/connect/default/object 指令不会因此接受 Blob。复用浏览器原生 Object URL 生命周期，
   没有增加图片代理或持久镜像。依据 [MDN img-src](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/img-src)。
5. 恢复旧 Dock 后，共享成功应更新该面板；输入引用仍只进入当前对应对话。修复把局部反馈
   错放在当前对话检查之后的问题，并增加跨对话成功回归。
6. 首轮前端回归的 Dock 枚举与图标尺寸合同不匹配已修复；迁移测试的旧 head 断言已同步，
   同时核对新授权表与级联外键。未通过删测试或放宽安全合同获得绿灯。
7. C 盘耗尽曾使 PyInstaller 解压 node.exe 失败。后续临时目录移到 D 盘，仅删除五个已核对
   源码哈希、精确路径且进程结束的本轮解压目录。此为环境事件，不将磁盘错误解释成模型失败。
8. 真实模型验收最初误把可选 phase 当成终态唯一依据；已改读权威 RunItem 的
   completion_disposition 与 Run.result 的 selection_suggestion。保留失败记录，最终用例通过。

## 最终产物与未覆盖范围

构建解释器 CPython 3.14.6 / python-build-standalone 20260804，使用带哈希的
`requirements-build.lock`。源码哈希 `0b3af778ac23ab4cf95ff34a25e0b27c547c9ef659fd4fdcfca6efaeea899f90`；
Sidecar SHA-256 `6ad11d500d01601c53f93c124f94c60d86a37621a5474eec1e63cabd0a27a2b0`。
生产源码、构建清单与桌面资源中的二进制一致，记录在 `.tmp/computer-final-release-proof.json`。

本地安装产物 `desktop/release-electron/DBFox-1.0.4-win-x64.exe`，约 203 MiB，未作 Windows
代码签名，未安装、未公开发布。第一方 DLC 包签名不能替代 Windows 安装包签名。

本轮没有远程 CI 成功记录，没有 macOS/Linux/其他 Windows 版本的电脑操作证明，也未验证
安装升级、任意第三方应用、密码/安全桌面、个人浏览器接管、上传下载或跨应用拖放。
独立 profile、授权围栏和 Job Object 不是 OS 安全沙箱。既有文件/执行能力的上一阶段证据见
[通用开发底座收敛](development-foundation-convergence.md)。
