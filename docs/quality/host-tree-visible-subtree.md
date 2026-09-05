# Host Tree 折叠子树修复

> 文档类型：质量与验证
>
> 状态：当前
>
> 最后核验：2026-09-05

## 问题与决定

Scene 独立验证在正式签名包与 Electron 中测得：10,000对象层级折叠后只有1个可见行，
DOM仍有10,000个 treeitem、60,357个元素，出现899ms长任务。证据位于Scene工作区
`docs/quality/scene-dlc-independent-verification.md`及其browser-evidence；这不是GPU帧率问题。

CodeGraph 检查现有 `Tree` / `TreeNode` 后确认：可见节点少于100时走递归分支，它不判断
expanded便映射所有children，只依赖Zag生成的hidden属性。当前已安装
`@zag-js/tree-view 1.43.3`和TanStack Virtual，Git历史`c5e8208e`实现了原通用树。
[Zag官方Tree合同](https://zagjs.com/components/react/tree-view)及本地connect/machine源码
确认展开、集合、焦点和选择均由Zag管理；节点状态提供expanded，branch content只设置hidden。

修复在既有Host渲染边界上按expanded挂载children与branch footer，仍保留branch/group元素、
Zag collection与全部键盘事件。大规模展开继续使用现有TanStack虚拟列表。未新增SDK、
依赖、领域分支、缓存、可写状态、分页协议或迁移；没有自行实现Tree状态机。折叠会卸载
自定义子行内容；领域持久内容和Zag展开/选择状态不依赖这些组件挂载。

## 回归与验证

`Tree.test.tsx`新增10,000节点折叠→展开→折叠检查，直接计数DOM（含隐藏节点），验证
折叠只有1个treeitem，展开窗口少于80行，且没有inline style。另一测试用实际键盘事件
折叠及展开父分支，验证嵌套展开、controlled selection、footer与焦点导航仍有效。
保留原异步子节点读取、失败重试、换根抛弃晚到结果、行按钮隔离和大列表测试。

定向7项通过（2.28秒）。全量前端96文件、513项通过（138.82秒）；测试类型检查通过，
lint为0 errors、5个既有warnings。尚未将本修复标为生产验收。
独立Scene验证员将复测相同10,000对象作品的DOM与长任务；没有以单测声称实际性能改善幅度。
