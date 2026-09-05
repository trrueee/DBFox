# Scene 控件生命周期回归

> 文档类型：验证记录
>
> 状态：当前
>
> 最后核验：2026-09-05

Voxel 独立验收发现的 OrbitControls 清理问题促使 Director 检查已集成的 Scene。新增作者回归证实两项缺口：React passive cleanup 执行时 viewport 已脱离原 document；按住 Control 卸载时，固定 Three 0.185.1 保留动态 document keyup。修改前 2 failed / 12 passed，原先的普通卸载与 GPU 释放证据没有覆盖这两个条件。

复用现有 viewport dispose，将其绑定改为 layout cleanup，确保 controls 在 DOM 移除前断开。[上游 r185 OrbitControls](https://github.com/mrdoob/three.js/blob/r185/examples/jsm/controls/OrbitControls.js)没有对应的公开 keyup 清理 API，调查时 dev 源码也保留此缺口。既有 DLC build.mjs 使用 esbuild 的 onLoad 在打包边界添加两行：移除该动态 keyup 并重置 Control 状态。不修改 node_modules、不访问运行时私有字段、不合成用户按键、不增加事件代理。

固定 Three 0.185.1、esbuild 0.28.2 与原 npm lock；补丁断言唯一源码位置，原始/修改后 source hash、bundle hash、负责人和退出条件记录于 vendor/provenance.json。升级到修复上游后删除此构建补丁，并要求原生监听器和 React DOM 生命周期回归通过。保留原 MIT 许可；不引入新依赖或持久化迁移。

修改后 14 项 Scene frontend fixture 通过（4.33 秒）。其中保留真实 Three hierarchy/geometry/controls，只替换 WebGL device；两个 Control 状态都验证注册过的原生 document 键盘监听器已移除。新 vendor 为 772,531 bytes，6 个官方 primitive 仍为 120,012 bytes，字节未变化。新的独立真实 Electron 复验尚待完成，本记录不替代该门禁；此前集成证据保留其原测试范围。
