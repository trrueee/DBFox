# Story 资源授权入口修复

> 文档类型：质量证据
>
> 状态：当前
>
> 最后核验：2026-09-07

独立 Story→Comic 组合在两个完整签名包安装、通过公开 operations 建好世界与章节后，进入生产 `authorize_project_resources` 时失败：`WorldDescriptor` 缺少 `to_scope_ref()`，尚未请求模型。问题来自 Story 自建资源描述类型与已存在的公开 SDK 合同不一致。

## 决策与改动

调查了 Story 当前实现与历史 HEAD、`dbfox_dlc_api.ProjectResourceDescriptor`、Core 资源授权调用以及 Music 等 DLC 的同类用法。删除 Story 私有 `WorldDescriptor`，在 `StoryStateStore.list_resources` 直接返回公开 `ProjectResourceDescriptor`，保留 kind/id/version/name/is_default 的现有值。

不增加 Core fallback、mapper、兼容别名或第二资源模型；不新增依赖，不改 SDK、数据库或资源授权语义。主要风险是旧调用方依赖私有类名，项目内检索没有发现外部引用；资源 discovery 与原生产 admission 的真实组合将负责防回归。

## 验证

根工作区执行 `python -m pytest verification/tests/system/test_story_dlc.py -q --tb=short`，12项通过；修改文件 pyflakes 通过。独立组合原失败证据由 `creative-comic-verification` 的 `test_story_comic_composition.py` 保留，修复后的组合结论待独立验证员回传，不预报通过。

Story store 原有496行新增/59行删除的未提交改动保持原样。此次只对 HEAD 中也已存在的资源描述类型作精确 index 补丁（3行新增/16行删除），没有把既有章节持久化工作一并提交。修复前完整文件备份在任务外部 recovery 目录，可逐项核对。
