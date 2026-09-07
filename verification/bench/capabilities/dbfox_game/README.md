# Game capability benchmark

> 文档类型：测评说明
>
> 状态：当前
>
> 最后核验：2026-09-07

运行 `python -m verification.bench.capabilities.dbfox_game --output <新目录>`。输出使用公共 Bench reporting/TrialOutcome，失败返回非零退出码。`cases.json` 定义 12 类单能力要求和 1 个十次创意请求 stress；评分只属于本 suite。

每次隔离安装完整签名 Game DLC，迁移真实 metadata SQLite，用生产 `build_product_run_loop` 执行；仅模型边界 scripted，无预算 override。现有实现不是 Scene bench 的私有引用，也没有新 RunLoop。产品狐狸/史莱姆 preset 是唯一示例操作来源：普通 case 为完整生存游戏，large case 为 128 实体，stress 为 27 实体。检查真实持久 Invocation、Artifact provenance、ID 保持、CAS/no-op/拒绝后的不变状态、明确无修改回答和十个独立用户请求。

`evidence/author-acceptance/` 记录 13/13 作者通过。它不是真实 LLM 创造力分数，不证明 Pixel 组合；实际 Phaser、键盘和原生 Artifact 的证据位于 `docs/quality/evidence/game-author/`。需在集成后的 Core 和独立审查中继续验证。
