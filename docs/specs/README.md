# DBFox 规范导航

> 文档类型：规范导航
>
> 状态：当前
>
> 最后核验：2026-08-06

`specs/` 描述用户可见行为、领域词汇和验收条件，不重复实现细节。实现所有权和调用链以 [`architecture/`](../architecture/README.md) 为准。

当前规格：

- [Agent 产品与运行规范](./agent.md)：Session、Run、Turn、工具、上下文、记忆、Artifact、Evidence、完成、错误和前端过程体验。

新增规格必须写明状态、适用范围、不可变行为和验收场景。尚未决定的方案标记为草案；被替代后移动到 `archive/designs/` 或明确标记 superseded。
