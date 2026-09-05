# 已选中资源的再次打开

> 文档类型：验证记录
>
> 状态：当前
>
> 最后核验：2026-09-05

Voxel 独立 Electron 验证发现：关闭世界标签页后，资源树仍选中该世界，再点击同一叶节点不能重新打开。Host 把 `onItemSelect` 完全绑定到 Zag 的 `onSelectionChange`，而相同选择不产生变更通知。

已检查当前安装的 `@zag-js/tree-view` machine/connect 实现和 [Zag 官方 Tree View 文档](https://zagjs.com/components/react/tree-view)。继续复用它的选择、焦点、展开和键盘状态；Host 在普通和虚拟叶节点上补充已选中项的主键点击与 Enter 激活。初次选择仍由原通知触发，`onSelectedIdsChange` 不产生虚构变更。行内操作保持独立，分支行为保持既有合同。没有新增依赖、公开 SDK 字段、持久化状态或兼容层。

修改前新增的普通/虚拟列表回归均失败于第二次点击只有一次回调；修改后 Tree 的 9 项测试通过（1.97 秒），测试类型检查通过。覆盖重复点击、Enter、首次回调不重复、选择通知不重复、行内按钮隔离，并保留异步加载、根切换与一万节点折叠回归。真实 Electron 关闭标签页再打开由独立验收补证。

完整 Lint 为 0 errors、5 条既有 warnings。首次完整构建在既有 Music vendor 文件写入处遇到 Windows `UNKNOWN` 文件错误；未改权限或构建检查，原命令重跑完成 Main/Preload、TypeScript、Vite、生产 Token 与 bundle 预算检查，入口 gzip 186,162 bytes。
