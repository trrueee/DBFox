# dbfox.music / Piano Studio Capability DLC

> 文档类型：Capability DLC 架构设计
>
> 状态：当前
>
> 最后核验：2026-08-25
>
> 版本：0.2

## 目标与边界

`dbfox.music` 是默认启用的签名 System DLC。Conversation 表达创作、修订与转录意图；Piano Studio Dock 负责让作品可见、可听、可触碰。Core 不理解 Score、Note、Piano、MIDI 或 MusicXML。

DLC 自持 `ScoreDocument` 唯一规范模型、`state.sqlite3`、Music Resource、Tools、Artifacts、Completion、Operations、Connector、Renderer、Piano Studio、离线音色与转录模型。MIDI/MusicXML 仅能是未来的边界导出格式。

Core 只新增两个通用桌面 primitive：受扩展名和大小限制的 `nativeDialogs.pickFile()`，以及只读取同一进程内刚由用户选择且未发生变化的文件的 `nativeFiles.readPickedFile()`。文件选择不会扩大 Run authority，也没有 Music IPC。

## 耐久模型

```text
Project
  ├─ Music Library Resource (logical create authority)
  ├─ Score Resource / frozen head revision
  │    └─ immutable ScoreRevision → ScoreDocument JSON
  └─ Audio Resource / fingerprint + analysis revision
       └─ immutable AudioTranscription → note candidates + confidence
```

完整领域文档只进入 DLC 数据库。Core Artifact 只保存稳定引用、content hash 与有界展示元数据。创建新乐谱时，Artifact 的 `resource_refs` 仍绑定输入 Run 已冻结的 Library 或 Audio Resource，不伪造新 Score authority。

Score 写入采用 compare-and-swap：只有授权的 frozen head revision 仍是当前 head 才能产生下一个 revision。同一 creative edit Tool 只提交一个 revision；Run 内不会偷偷更新 authority。

新建乐谱以 Core `ToolInvocation.id` 作为 `creation_invocation_id`。`scores` 对该值建立唯一约束，`music_compose_piano` 使用 `reconcile` 恢复策略：若 DLC 已提交而 Core 尚未结算，恢复只查询同一 invocation 并返回原 ScoreRevision 与 Artifact，不重放创作写入。

模型创作输入不是完整 `ScoreDocument.notes[]`，而是每小节一个紧凑的 `PianoMeasurePlan`：旋律事件、和弦符号、和弦音与有限伴奏型。Music Tool 确定性展开左手伴奏并生成 canonical `ScoreDocument`。这样仍只有 Core Agent 的一次模型调用，没有隐藏 Music LLM，也不会让 16 小节双手逐音 JSON 长时间占据 Provider Turn。

## 音频转录

```text
用户选择音频
  → Electron 限界读取
  → Chromium AudioContext 解码 / 单声道 22.05 kHz 重采样
  → Spotify Basic Pitch 模型
  → immutable note candidates + confidence
  → DLC commit_transcription
  → Agent music_transcribe_piano
  → 量化、跨小节切分、钢琴音域校验
  → ScoreRevision
```

Basic Pitch 的音符候选是音频事实层；Agent 只能通过 Music Tool 提议结构化修复。LLM 不接收逐采样音频，也不通过文本猜音符。Piano Studio 显示整体/区间置信度，并提供 Original 与 Transcription A/B。

导入后的原音频副本由 DLC 持久化。当前公共前端 SDK 没有 DLC durable blob streaming seam，因此应用重启后仍可解析 Audio Resource、transcription 与关联 Score，但重新试听原始录音需要用户再次选择原文件。后续若平台增加通用、范围请求、权限隔离的 DLC blob view，应在真实二进制边界一次解决；本版本不使用 base64 operation 或 Music 特判绕过 1 MiB operation contract。

## 前端实现

- 乐谱：`ScoreDocument → VexFlow notation model → SVG`，无 MusicXML 镜像模型。`HarmonyEvent` 是一等领域事件并渲染为和弦符号；每个声部按 beat gap 和小节尾确定性补 rest，避免顺序排版抹掉节奏位置。
- Conversation 的通用 namespaced Artifact 接缝调用 DLC Renderer；Score Revision 显示轻量卡片。若同项目的空 Piano Studio 正在等待刚提交的创作，Music Renderer 将该空视图提升为新 Score；Core 不判断 Artifact 是否为乐谱。
- 播放：原生 WebAudio deterministic timeline；播放状态仅在前端内存。
- 音色：Salamander Grand Piano V3 velocity-8 的 30 个关键音 MP3，以播放速率插值覆盖 88 键，按样本懒解码并完全离线。
- 键盘：默认围绕作品音域展示约五个八度；Full 88 横向滚动。
- Transcription Mode：波形、进度、置信度、Original/Transcription A/B、钢琴键跟随。
- UI：一块连续 surface，支持亮/暗、窄/宽 Dock、键盘 focus 与 reduced motion。

## 调研与复用决策

调查范围包括仓库现有 Extension Host、Data/Workspace System DLC、浏览器音频平台、官方文档与成熟开源方案。

| 决策点 | 采用 | 未采用与原因 |
| --- | --- | --- |
| 乐谱 SVG | VexFlow 5.0.0，MIT | OpenSheetMusicDisplay 以 MusicXML 为输入，会为当前 JSON 事实源引入额外模型/转换层和更大体积。 |
| 播放/调度 | 原生 WebAudio | Tone.js 成熟但面向更广的交互音乐/DAW 能力；当前只需确定性 timeline、loop 与 sampler。 |
| 钢琴音色 | Salamander Grand Piano V3，CC BY 3.0 | oscillator 只适合作为占位，不能达到 Piano Studio 的产品质感。 |
| 转录 | `@spotify/basic-pitch` 1.0.1 浏览器包，Apache-2.0 | Python 包在 Python 3.12 与 TensorFlow 上限冲突；ByteDance checkpoint 约 628 MiB 且为 pickle/PyTorch 供应链，首版 Frozen Sidecar 成本过高。 |
| 解码 | Chromium AudioContext | FFmpeg 的构建配置、LGPL/GPL 合规和 Sidecar 体积不适合 MVP。 |

参考：[VexFlow](https://github.com/0xfe/vexflow/blob/master/README.md?plain=1)、[OpenSheetMusicDisplay](https://github.com/opensheetmusicdisplay/opensheetmusicdisplay)、[Tone.js](https://github.com/Tonejs/Tone.js/)、[Basic Pitch](https://github.com/spotify/basic-pitch/blob/main/README.md?plain=1)、[Basic Pitch Python 3.12 issue](https://github.com/spotify/basic-pitch/issues/159)、[ByteDance Piano Transcription](https://github.com/bytedance/piano_transcription)、[FFmpeg Legal](https://www.ffmpeg.org/legal.html)。

新增依赖只用于构建 DLC 自包含前端产物，不进入 Core UI bundle。`npm run build:music-vendor` 会固定版本、复制模型/音色、保留许可证并生成离线文件。退出路径是替换 `frontend/vendor-src` 的单一实现并重建 vendor；ScoreDocument 与 backend contract 不依赖这些供应商 API。

没有新增兼容层、双写、Music router 或领域镜像模型。边界转换只有 Basic Pitch note events 单向归一化为 ScoreDocument、紧凑 composition 单向展开为 ScoreDocument，以及 ScoreDocument 单向转换为 VexFlow tickables/WebAudio events。Core migration 仅退休已知历史 Agent Eval 表，不解释 Music 数据。

## 验证

- `verification/tests/system/test_dbfox_music_dlc_package.py`：签名包激活、公共 API、Resource、不可变 revision、紧凑创作展开、和弦移调、invocation reconciliation、audio transcription。
- `verification/bench/capabilities/dbfox_music/direct/`：schema、revision、transpose、edit locality。
- `verification/bench/capabilities/dbfox_music/transcription/`：pitch/onset/duration deterministic scorer。
- `verification/bench/capabilities/dbfox_music/agent/`：真实 provider 数据集与独立 human rubric。
- `verification/bench/composition/core_music/`：真实 RunLoop 的 Conversation → authority → Tool → Artifact → Completion。
- `output/playwright/piano-studio-*.png`：亮/暗/窄 Dock 浏览器 QA 证据，不属于生产包。

禁用 `dbfox.music` 后，其 Resource provider、Tools、Context、Artifact contracts、Completion support、Operations、Connector、Renderer 与 Dock contribution 一并消失；DLC 数据目录保留，重新启用后恢复。
