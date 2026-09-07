# Animation capability verification

> 状态：当前

作者编写的12类确定性bench。真实签名完整DLC、迁移后的metadata、production RunLoop/ToolRuntime/冻结资源/Artifact；只有模型边界是ScriptedProvider。统计值反映此数据集执行合同，不是模型准确率或真实创作评估。

`python -m verification.bench.capabilities.dbfox_animation --output output/animation-bench-new`，输出目录必须尚不存在。复用shared framework的SuiteManifest、TrialOutcome、report writer，Animation事实判断只在本suite/scoring.py。12类包括简单创建、增量、多阶段、非法恢复、先inspect、stale、no-op、歧义、大作品、有界上下文、人类后Agent与负向任务。单测另包含12步连续修改、race、cancel、receipt/restart、undo/diff、历史下载与Scene公开表示。

实际Electron：先 `cd desktop; npm run build:electron-host`，再从根运行 `node verification/bench/capabilities/dbfox_animation/browser-launch.mjs <全新外部runtime目录>`。端口Vite5191、CDP19241；`--reuse` 保留已有signed runtime。fixture真实生成3key和2048key作品，使用真实Main/Preload/EngineSupervisor。仅关闭由本launcher启动的窗口；没有付费API或账号凭据。

浏览器截图和开发原始记录在output/playwright/；可提交的有限证据在docs/quality/evidence/animation-author/。最终作者质量说明和独立验收界限见docs/quality/animation-author-verification.md。
