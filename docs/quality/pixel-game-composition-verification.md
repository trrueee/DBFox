# Pixel → Game 生产组合独立验证

> 文档类型：验证报告
>
> 状态：当前
>
> 最后核验：2026-09-07
>
> 适用范围：两个真实签名 DLC 的耐久素材组合；不是完整 Game 独立验收

## 结论与精确基线

本组合门禁通过。由未参与 Game 产品实现的 Director 在独立工作树完成，未修改 Game/Pixel 产品或 Core。根分支 `94294767` 提供当前原生 tool search；Game 作者源提交 `f54950ca`、`737a1f1c`、证据目录修复 `031a5f11` 分别接入验证树为 `34a8b08f`、`7a76c658`、`194b6590`。验证树为 `D:/Project/DBFox-worktrees/creative-game-verification`，分支 `codex/game-verification`；根产品分支尚未集成 Game。

根工作区39个原有用户修改文件已逐字节复制到验证树，作为同一运行基线，不纳入本次提交。新 checkout 把10个既有 Music/Visualization vendor 文本变成CRLF，其中Vega包大小因此不匹配；这些文件只在验证树恢复成根工作区原字节，没有重新构建或修改其他 DLC 产品。此环境问题与 Game 的证据目录错误分别处理。

## 实际执行与断言

[组合测试](../../verification/tests/system/test_pixel_game_composition.py)冷签名并通过正式 DLC service 信任、安装、启用完整 Pixel 和 Game 包。使用迁移后的元数据库、正式资源授权、Session admission/lease、生产 `build_product_run_loop`、真实 AsyncOpenAI/Responses adapter。仅远端模型 HTTP 被 `httpx.MockTransport` 控制；不注入 owner store、工具结果、Artifact 或 Representation。

同一 Run 的8次工具调用完成：创建48×40 Pixel文档、填充图像、创建Game、从固定Pixel Artifact导入、检查Game、创建引用该素材的实体、局部修改Pixel、导出Game。9次HTTP请求，默认32768 prompt预算下峰值估计16544，没有提高预算。模型只从先前工具的可见输出取得ID、版本和Artifact引用。

独立内容断言从公开Representation读取四个真实Pixel有界图块，重组7,680字节RGBA，与Game导出包内素材逐字节及SHA-256比较。实体Visual确实引用该素材ID；素材保存原Artifact ID、source_version=2和原fingerprint。后来Pixel版本3在(31,31)处像素已不同，但Game导出保持旧字节。停用Pixel后，Game完整导出仍逐字节相同，说明导入结果由Game拥有，不依赖源DLC内存或私有store。

导入Artifact具有真实 `DERIVED_FROM` 关系，并保留来源Artifact的完整ResourceRef；对应Invocation只冻结本次被授权的Game资源，没有因读取公开成果扩大私有资源权限。所有8个Invocation成功且package_digest匹配实际安装包，Run正式结算为completed。

## 验证结果与修复记录

- 独立复跑作者后端32项与新增组合1项：33 passed，15.66s。
- 最终增加精确来源关系/Invocation scope断言后重跑组合：1 passed，5.70s；输出到忽略的 `output/pixel-game-independent.xml`，xunit1下无warning。
- 独立复跑Game前端fixture：7 passed，1.15s。
- 最终工程合同：45 passed，3.58s。

初版独立测试错误地把Game Selector写成裸ID，正式Tool Runtime正确拒绝；测试改成公开合同要求的 `{id: ...}` 后继续。新增审查断言也曾误用Invocation字段，已改用生产持久化的provider_call_id定位，不构成产品缺陷。最终通过结果来自真实执行，没有屏蔽失败或放宽合同。

工程合同发现作者将7份JSON放在不允许的docs目录，作者修复 `031a5f11` 将它们原字节移至 [Game testkit evidence](../../verification/testkit/game_studio/evidence/)，同步引用，未修改工程规则。

## 尚未覆盖

这里的模型回复为确定性脚本，不证明在线模型检索效果、创作质量或实际token费用。这里没有启动Phaser或Electron，不把素材字节组合等同于原生渲染验收。作者原生Studio、下载、3600 tick试玩和精确撤销证据仍是作者证据；完整非作者原生复验、独立红队、打包发布与最终跨能力作品验收继续保留。Game completion仍为false。
