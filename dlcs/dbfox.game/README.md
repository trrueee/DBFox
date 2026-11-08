# Game Studio

> 文档类型：能力使用说明
>
> 状态：当前
>
> 适用范围：`dbfox.game` 0.1.0，Extension API v2；作者候选已验证，独立与组合门禁待完成。

创建游戏后点击“添加狐狸生存示例”，即可直接编辑狐狸、史莱姆生成器、生命和 60 秒获胜规则。方向键/WASD 控制角色，播放/暂停/单步/重置用于本地预览；正式 Playtest 将实际输入和固定版本交给已安装 Phaser 执行器并保存报告。可下载的固定版本参考见 [示例 Game 包](examples/fox-survival.game.json)；当前以结构化操作编辑，不承诺整包 JSON 导入覆盖。

Game 保存可增量编辑的场景、实体、组件、行为、规则、变量和 RGBA 素材。完整领域合同与25项边界在 [架构](../../docs/architecture/game-dlc.md)，实际验证在 [质量证据](../../docs/quality/game-dlc-evidence.md)。[生成合同](contracts.schema.json) 来自实际注册模型，含 canonical、每个 operation 的输入/输出以及17个 Tool schema。

## 身份与编辑

每个 Host Project 有 `dbfox.game.library` Resource，初始 version=1；每个 Game 有独立 `dbfox.game.project` Resource，id 是 Game UUID，version 是严格整数。Scene/entity/component/behavior/rule/variable/asset 是内部 UUID 对象。组件保存 `{id,spec}`，行为和规则保存 `{id,enabled,spec}`；不是独立 Resource。UI selection、草稿、Phaser runtime state 与 playtest 终态均不写 canonical。

写入接受 `expected_version`、Human `request_id`；创建用 `expected_library_version`。Agent 还必须匹配 Host 冻结 Invocation ref.version。一次 apply 最多64个 typed operations；entity_create/transform/delete 每批最多128对象。一批最多64个唯一 creation refs，`{ref:"fox"}` 仅引用同批较早创建的对象，既有对象用 `{id:"UUID"}`。只提供结构化编辑，不接受整个 Game 替换。

人和 Agent 共用 SQLite/CAS/append-only revisions。普通 noop 保留自身 receipt、不推进 head；显式 undo 总是追加 revision，即使内容 hash 重复。tombstone 仍可发现并 undo；最多64 active/128 retained Games。一次 Game head 变化同事务推进 library version。每个请求身份只能搭配原始规范输入，断线或取消后不自动重放。

native strict Tool schema 将 nullable optional 字段也列入 required。因此仅声明 `default=None` 的输入字段将 null 归一为省略；必填/数值/boolean/未知字段不接受 null。完整 canonical Game 不接受显式 null，规范 JSON 不保存 null。

## 公共 operations

| Project operation | 输入要点 | 输出 |
| --- | --- | --- |
| `games.list` | offset/limit≤50；后续页必须固定首个 `version` | Page，含 library_version 与 game summaries，包括 deleted |
| `games.head` | game_id | game summary、当前 library_version |
| `games.get` | game_id + 固定 version，section 与 offset/limit | 固定 revision 的 Page |
| `games.create` | title、expected_library_version、request_id | Mutation |
| `games.apply` | game_id、expected_version、request_id、operations | Mutation |
| `games.undo` | game_id、expected_version、target_version、request_id | Mutation |
| `games.delete` | game_id、expected_version、request_id | Mutation |
| `assets.upload` | game_id/version/request_id、name、width/height≤512、rgba_base64 | Mutation，created_refs.asset |
| `games.revisions` | game_id、固定 version、offset/limit≤50 | 历史 Page |
| `games.diff` | game_id、from_version/to_version、offset/limit≤50 | 稳定 ID 和 changed fields Page |
| `games.export` | game_id、expected_version、request_id | 正式 ActionRun result |
| `games.playtest` | game_id、expected_version、request_id、seed、ticks、inputs | 正式 ActionRun result |

Mutation 含 `game` summary、`library_version`、`changed`、最多64个 `changed_ids` 与明确 truncated、`created_refs`，试玩额外含有界 `report` summary。ActionRun result 含 `session_id/run_id/artifact_ids/outcome`；在启动 Run 前预留32KiB owner result 额度。重复已完成身份返回原结果，未知身份拒绝重新创建 Run。机器 operations `playtest.attach/next/complete/detach` 只供 activation executor；精确 lease/proof 模型见 schema。

`games.get.section` 为 summary/scenes/entities/components/behaviors/rules/variables/assets/asset_bytes；对象页≤50且≤32KiB。asset_bytes 必须固定 version 和该 revision 内 asset_id，offset 是 raw byte，limit≤16384；返回 metadata.asset 的 hash/尺寸以及 rgba_base64、total/next_offset/has_more，支持重组后 SHA-256 校验。删除当前资产不影响历史版本的字节读取。

## Tools 与公开结果

17个 Tools：game_create、game_inspect、game_modify、game_diff、game_undo、game_delete、game_export、scene_create、entity_create、entity_delete、component_add、component_modify、behavior_create、rule_create、variable_create、playtest、asset_import。专用创建/组件工具的 `operation` 使用同一个 typed domain operation；game_modify 接受 operations 批次。game_inspect 不提供 raw asset bytes；context≤4000字符，常规 facts≤8KiB、显式检视 provider payload≤16KiB。

`dbfox.game.project-revision` Artifact 的 `dbfox.game.document.v1` Representation 提供 `page` JSON 和 `export` application/json；export 是包含同一固定 Game document、revision summary 与按 hash 去重 RGBA bytes 的 `.dbfox-game.json`。`dbfox.game.playtest-report` 的 `dbfox.game.playtest.v1` 提供 summary/events/entities/variables 页和 JSON report export。参数不能覆盖 Artifact locator 的 project/game/version/hash。

asset_import 只读取本 Run 中显式 Pixel revision Artifact 的 `dbfox.pixel.sprite.v1/frame`，按≤32×32页读取一个≤128×128 rectangle。每页核对相同 durable source version/fingerprint，再写 Game immutable RGBA BLOB 与 frame/rect/source provenance；结果显式 `DERIVED_FROM` 该来源并继承其 exact refs。不会把来源 refs 注入 Game Tool execution scope，不导入 Pixel store 或读取路径/URL。native image 文件由前端解码后走 assets.upload。

## 固定 Phaser 引擎

正式 pin `phaser@4.2.1`，官方 ESM source 仅构建 Canvas + Arcade，关闭 sound/WebGL/Matter。预览与 playtest 的同一个 scene update 调用一次公开 `World.singleStep()`；画布入口 Game.step、headless 入口 Game.headlessStep，只在渲染上不同。场景准备后停止自动 loop，规则只使用固定60Hz tick；3600 ticks 等于60秒。spawn runtime IDs、边沿触发与同 tick 优先级见权威架构。

Phaser 原版 VisibilityHandler 会残留 visibility listener 并覆盖 window.onblur/onfocus；构建对已核验上游 source hash 应用最小 DESTROY cleanup patch。完整构建来源/原改 hash/输出 hash 在 [provenance](frontend/vendor/provenance.json)，原样 MIT 许可证随 vendor 保存。工作台输入由本地受控 DOM adapter 提供，Phaser input managers 关闭。

```powershell
# 工作目录 dlcs/dbfox.game；依赖只装本 DLC，不安装共享 desktop/node_modules
npm.cmd ci --ignore-scripts --registry=https://registry.npmjs.org/
npm.cmd run build
# 仓库根
python dlcs/dbfox.game/generate_contracts.py
python -m pytest verification/tests/system/test_game_dlc.py -q --tb=short
```

5秒 activation lease、20秒单请求 deadline、25秒 Tool timeout；一次 playtest≤7200ticks/1024 input events/512 active runtime entities。超预算明确失败，不悄悄少模拟实体或步数。桥协议测试的模拟报告不证明真实 Phaser execution。当前完整 frontend、生产 Electron、capability bench/stress 和独立 Review 仍待完成。

## 具体作品标签

从游戏库选择或创建游戏会打开以游戏名称命名的独立 Dock 标签。Host 标签保存 Game Resource 定位及主选中实体/场景的 `target.locator`，切到报告或其他工件再返回时重新读取同一游戏和检查对象。定位不冻结编辑器版本，也不增加执行授权。UI 多选集合、未提交表单和播放状态仍为组件内状态；切标签或关闭工作区会沿用 Host 的卸载语义，不把这些内容写进领域数据库或镜像 store。
