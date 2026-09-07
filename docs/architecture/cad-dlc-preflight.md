# CAD 内核部署与规范模型调查

> 文档类型：技术调查
>
> 状态：草案
>
> 最后核验：2026-09-06
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
