# CAD 内核部署与规范模型调查

> 文档类型：技术调查
>
> 状态：草案
>
> 最后核验：2026-09-07
>
> 适用范围：`dbfox.cad` Lead 的实现前选型；尚未选择或安装产品内核

原始目标仍是完整参数化 CAD：草图、约束、尺寸、特征、实体和装配构成可重算的规范操作树，支持 extrude/revolve/cut/boolean/fillet、检查和导出。78 mm × 10 mm 手机的65°支架及充电槽，在宽度改成82 mm后必须由同一参数树重算。预生成STL、修改外观比例或只提供架构文档均不满足任务。

## 已查项目与现有边界

Director先通过CodeGraph检查实际[应用协议](../../desktop/main/appProtocol.ts)和[DLC资产协议](../../desktop/main/dlcAssetProtocol.ts)，再核对其Git历史（ffbcfca2、8aa45686、dee40600、5c895613）。这些文件没有CAD领域接口或WASM特例。当前政策为 `script-src 'self' dlc-asset:`，未授权WASM编译；DLC单个资产上限20 MiB，`.wasm`没有专用MIME映射，返回application/octet-stream。现有[协议测试](../../desktop/main/__tests__/dlcAssetProtocol.test.ts)与[CSP合同](../../desktop/src/__tests__/csp-contract.test.ts)是必须保留的边界。

先前的[第二批调查](creative-dlc-next-wave-investigation.md)已比较JSCAD和Replicad/OpenCascade：后者发布内核单WASM为22,481,415或22,980,267 bytes，超过20 MiB；定制构建只可能解决体积问题，不能据此推断已满足CSP或完整草图约束。最终选型必须分别证明几何、约束、安装、许可和真实导出能力。

## 实际浏览器因果探针

Windows上使用独立Playwright CLI会话 `cad-csp-constraints`，HeadlessChrome152。任务专用本机HTTP服务从appProtocol.ts实际字符串数组读取完整CSP，用响应头原样施加，HTML只加载同源外部probe.js，不使用内联脚本、eval、CSP绕过或宽松浏览器启动参数。对照页只省略CSP头，其脚本与WASM字节完全相同。

WASM输入是合法空模块的8个字节 `[0,97,115,109,1,0,0,0]`，可以排除候选CAD库、内存规模和供应链因素。

| 执行 | 原样生产CSP | 无CSP对照 |
| --- | --- | --- |
| 同源普通JavaScript | 成功 | 成功 |
| WebAssembly.compile(bytes) | CompileError，违反script-src | 成功 |
| WebAssembly.instantiate(bytes) | CompileError，违反script-src | 成功 |
| instantiateStreaming，application/wasm | CompileError，违反script-src | 成功 |
| instantiateStreaming，application/octet-stream | CompileError，违反script-src | TypeError，MIME必须为application/wasm |

因此本次实测确认两个独立部署条件：现有CSP拒绝WASM编译；流式加载还要求正确MIME。把资产改为ArrayBuffer加载只绕开流式MIME要求，仍受相同CSP限制；不得将此称为兼容方案。官方说明见[script-src的WASM规则](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/script-src)和[instantiateStreaming](https://developer.mozilla.org/en-US/docs/WebAssembly/Reference/JavaScript_interface/instantiateStreaming_static)。

本探针是浏览器在生产等价策略下的最小因果证据，不是Electron签名包安装、OpenCascade运行或CAD作品验收。未下载WASM内核、未改Host政策或资产预算。临时脚本位于该工作树output/playwright/cad-csp-probe/server.py，未纳入产品；命名浏览器与测试服务已关闭。独立Lead需要在最终固定候选上重建正式证据。

## 当前复用决定与剩余调查

当前尚未选定几何内核，保持产品实现队列；不因能在开发机使用原生OCP而宣称Frozen Sidecar可部署。也不为采用Replicad静默提高资产上限、切片避限、放宽整个Renderer CSP或另建私有执行通道。

下一步应验证JSCAD等纯JavaScript成熟实现是否能在当前政策中提供需要的几何操作，并明确其倒圆角范围、健壮性、网格误差、实体检查和导出边界。草图约束与参数依赖应另外寻找成熟求解能力；若候选缺失需求，必须如实记录，不能用自写不完整求解器冒充通用约束。若最终只有WASM方案满足领域目标，应先形成明确的可审查通用平台扩展方案，说明执行范围、供应链、包大小、取消/代际隔离、许可和退出条件，再按现有Kernel/Host治理处理。

无论几何引擎如何选择，唯一规范模型由CAD owner SQLite持久化；派生网格和拓扑不是第二事实源。Tool与人类编辑使用同一操作合同、版本CAS和回执；正式Artifact固定文档版本/内容hash，跨DLC只通过公开Representation消费。领域几何、求解、特征依赖和尺寸规则不进入Core。


## 2026-09-07 继续调查：官方精简构建

重新核对 [OpenCascade.js 官方定制构建](https://ocjs.org/docs/app-dev-workflow/custom-builds)后，优先验证它的 YAML bindings 白名单和编译器 dead-code elimination，而不是分片或压缩包内资产来绕过单资产限制。该机制复用上游构建系统，可仅导出所需的建模、布尔、倒角、网格及交换格式接口；具体所需接口、最终未压缩字节和所有必需几何操作尚须实测。不能把自定义构建本身当作功能齐备的证据。

[官方体积说明](https://ocjs.org/docs/getting-started/file-size)中的网站示例曾使用 JS+WASM 合计约 7.1 MB 的定制构建。这证明定制构建有减小体积的实际先例，但它不是本 DLC 所需全部功能的当前测量，也不能用该值替代安装包验收。压缩传输大小与 DBFox 未压缩资产限制不是同一指标。不能为缩小文件而关闭所需几何异常处理，再把失败冒充成功。

[JSCAD 官方 primitives](https://jscad.app/docs/module-modeling_primitives.html)提供 roundedCuboid 等圆角基本体；基本体带圆角不能证明任意布尔结果上的边倒圆角、尺寸约束或可编辑 B-Rep。该方案仍需对原始功能逐项验收，不能以“纯 JavaScript 可加载”缩减原始 CAD 目标。

本机已有 Docker CLI，但本轮实际查询显示 Docker Desktop Linux engine 的命名管道不存在，尚无可用构建 daemon；没有因此宣布无法定制构建，也未安装新工具或更改系统启动设置。后续先恢复已安装的构建环境并固定上游镜像摘要，再做最小可重现建模内核。已确认的 CSP WASM 编译限制仍独立存在，定制构建不解决该限制；是否需要通用、受约束的 Host 扩展，须依据实际能力要求另作架构裁决。

## 2026-09-07 求解器实测：PlaneGCS 发布包不能直接进入产品

调查了 [PlaneGCS 浏览器封装](https://github.com/Salusoft89/planegcs)、[JSketcher 许可源文件](https://github.com/xibyte/jsketcher/blob/main/LICENSE)与 Emscripten 的官方构建选项。JSketcher 的许可含修改贡献与版权转让条款，不能按普通 MIT 依赖直接采用。PlaneGCS 复用 FreeCAD 数值约束求解，当前作为优先验证候选；它并不替代 OpenCascade 的实体建模。

从官方 npm registry 取得 `@salusoft89/planegcs@1.2.0`，校验 SHA-512 后只解包至忽略的输出目录，没有改 package.json/锁文件或执行 lifecycle scripts。对应上游 tag 为 `ee9b156da9827a91a56a888a53520f63d5cffaa6`。WASM 为 508,141 bytes，SHA-256 `039601df53b11cd06d0f8626cd2e9422b07aca31b18db9ba437b7d26cf5594c5`，满足现有单资产上限。npm 元数据写 LGPL-2.0-or-later，而该版本源码头写 2.1-or-later、LICENSE 为 2.1；分发前须固定对应源码、实际许可通知和重建办法，不能只抄 npm 标签。

[可复现实测](../../verification/testkit/cad_solver_probe/README.md)使用未修改的真实 WASM，在 Node 24.13.0 下通过五项数值检验：78×10 mm 约束矩形改成82×10，保留相同点与约束ID，再交替重算200次；65°线段；欠约束自由度为1；互斥78/82尺寸返回失败并定位两条冲突；边长3/4/10三角形返回失败但冲突列表为空。最后一项说明不能把“冲突列表为空”当作成功，失败时不得应用派生解或提交规范模型。

HeadlessChrome152 中又加载同一个发布包：原样 Host CSP 拒绝 WASM；仅在探针页面增加 `wasm-unsafe-eval` 后，WASM阶段可越过原限制，但生成的绑定继续触发 JavaScript `EvalError`，初始化仍失败。两个页面的普通动态求值控制均被拒绝。该结果推翻了“只加 WASM 指令即可使用发布包”的假设；本轮没有修改 Host CSP、SDK或Core。

[Emscripten 官方 DYNAMIC_EXECUTION](https://emscripten.org/docs/tools_reference/settings_reference.html#dynamic-execution)提供禁用动态求值的构建选项；其 Embind AOT 是可调查的编译期优化。下一步应在固定上游源上用正式编译选项重新构建，再复验浏览器，不得手改压缩后 JS、允许 `unsafe-eval`、启用 CSP bypass 或另建私有运行通道。定制几何内核仍需分别证明 extrude/revolve/cut/boolean/fillet、拓扑检查、导出、取消和资源上限。当前结论是“可复用算法已验证，部署候选尚未合格”，不是 CAD 完成。

本次尝试以隐藏方式启动本机已有 Docker Desktop，`docker version` 和 `docker desktop status` 都未返回可用状态，未拉取镜像或开始构建。随后 `docker desktop stop --timeout 30` 报告停止失败；仅终止了本轮启动、路径和启动时间已核对的 Desktop/backend 进程，另两条查询也已中断。未改 WSL、系统启动设置或安装新软件。上游固定源码已保存在忽略的 `output/cad-solver-probe/upstream`，其所需 bindings.cpp 还需按上游生成步骤构建；不把已取得源码或 Node 成功当作重建成功。

## 2026-09-07 禁止动态求值的求解器重建：浏览器候选通过

后续使用任务目录中的官方便携 emsdk 3.1.45 完成真实编译，没有再次启动 Docker。复用原 PlaneGCS 固定源码、上游 Tree-sitter/Nunjucks 绑定生成器和 CMake；只在构建副本中适配 Boost/Eigen 的 Linux 头文件路径，并增加官方 `-s DYNAMIC_EXECUTION=0`。未修改求解算法、生成后的 JS、Host CSP、SDK 或 Core。[重建指南](../../verification/testkit/cad_solver_probe/README.md)包含完整工具链版本、命令和[输入哈希](../../verification/testkit/cad_solver_probe/source-hashes.json)。

官方 emsdk tag 固定为 `c8dcb45665fec5e743336703f1d22a191810f2a8`，其编译器构建为 `2b7c5fb8ffeac3315deb1f82ab7bf8da544f84a1`；Eigen 3.4.0 固定提交为 `3147391d946bb4b6c68edd901f2add6ac1f31f8c`，Boost 1.74.0 tarball 已按官方 SHA-256 校验。上游绑定工具在 Node 24 下因 C++17/C++20 要求冲突失败，改用 SDK 自带 Node 16.20.0 和本机已有 VS2022 BuildTools 后完成生成。没有通过修改旧原生扩展、重新实现解析器或全局安装软件绕过问题。旧 emsdk 下载使用固定官方 HTTPS 地址，但自身未核验独立的发布者校验和；记录的编译器可执行文件哈希不能等同于签名工具链证明。

| 重建资产 | 原始 bytes | gzip bytes |
| --- | ---: | ---: |
| planegcs.js | 27,602 | 10,739 |
| planegcs.wasm | 508,141 | 173,175 |

WASM SHA-256 为 `af37e4c9228dafe008f636657a087b597305adf6beba11ebcfbe81f547023896`，gzip 使用 level 9、mtime 0；判断20 MiB资产限制仍使用原始字节。新的 WASM 与发布包大小相同但 hash 不同，不能把它们当作同一二进制。原 Dockerfile 的 apt 头文件版本并未固定，本轮明确固定 Boost/Eigen 后不宣称逐字节复现 npm 发布包。

[实际结果](../../verification/testkit/cad_solver_probe/rebuild-evidence.json)记录 Windows x64、Node 24.13.0 和 HeadlessChrome152：Node 五项通过；Chrome 原 Host 策略仍在 WASM 编译阶段失败；仅在本地探针响应中增加 `wasm-unsafe-eval` 后，同一份共享用例的五项检查全部通过，200次宽度重算保留原ID，65°、欠约束和互斥/不可解约束结果与Node一致。两个页面的显式 `new Function` 控制均报 `EvalError`，候选页面求解诊断为空。浏览器会话 `cad-independent` 与端口18846测试服务已经关闭。该证据表明本轮已消除发布包的动态JS绑定阻碍，但仍不满足未修改的Host政策。

采用决定是继续将此重建列为 CAD 草图求解候选，交由 Director 依据几何内核证据统一选择执行位置。没有新增兼容层、产品依赖、第二事实源或迁移债务。当前保留上游 Release 的异常、固定内存和未定义符号策略；五项通过不证明所有公开API、任意约束、取消或资源上限安全。LGPL版本文字差异、vendored FreeCAD与补丁对应、Eigen混合许可文件、完整通知与可重链接/重建分发安排仍待核验，不能据此宣称许可已获清理。几何特征、拓扑、导出、签名DLC安装及原始手机支架任务仍须另行完成。
