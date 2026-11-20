# 电脑工作台

> 文档类型：产品交互与 API 合同
>
> 状态：当前
>
> 最后核验：2026-11-18
>
> 适用范围：Windows 11 x64，支持图片输入的模型，普通交互桌面

## 使用流程

1. 在新任务或对话输入框点击“电脑”。新任务先建立对话草稿，不会自动发送任务。
2. 选择受控浏览器或具体窗口。默认仅观察；需要点击、输入时明确选择“观察与控制”。
3. 选择共享期限，确认范围后开始。浏览器采用独立 Edge 配置，不继承个人登录信息。
4. 直接用自然语言描述任务。输入引用保留目标身份；面板中选择活动目标也可作为后续输入
   的可见工作对象。切换对话不会把共享对象带入另一对话。
5. 审批卡显示目标、动作、元素、地址/文字/按键和观察时间。批准只针对这一次动作。
6. “电脑”面板显示实际共享状态、浏览器地址/页面和按需刷新预览；成果中可打开正式观察
   与操作证据。预览时间不代表之后画面没有变化，操作记录也不代表任务已经完成。
7. 随时使用固定的“全部停止并接管”，或对单一目标停止/结束共享。快捷键注册成功时显示
   `Ctrl+Alt+Shift+Esc`；被占用或非桌面环境会明确提示不可用。关闭面板仅改变展示。

暂停、到期、重启或目标失效后需要重新共享并观察；不会自动恢复。观察权限不能用于控制，
控制共享也不能代替逐次审批。密码与登录由用户手动处理。不要分享不希望发送给当前模型的内容。

## 入口

所有 HTTP 均位于现有 `/api/v1` 下，使用同一短期 Token、来源校验和 Problem Details。

| 方法与路径 | 行为 |
| --- | --- |
| `GET /computer/targets` | 返回短期、不透明的目标选择 ID，不能提交猜测的 HWND |
| `GET /conversations/{id}/computer` | 读取此对话的共享记录与后端状态 |
| `POST /conversations/{id}/computer` | 明确选择观察/控制、期限及是否替换，同意后建立共享 |
| `GET /conversations/{id}/computer/{target}/preview` | 读取无缓存 PNG 预览，不生成执行证据 |
| `GET /conversations/{id}/computer/{target}/browser` | 读取所共享浏览器的当前地址和页面状态 |
| `POST /conversations/{id}/computer/{target}/stop` | 暂停该目标，先阻断后续输入 |
| `DELETE /conversations/{id}/computer/{target}` | 结束该共享 |
| `POST /computer/stop` | 用户紧急停止所有电脑共享 |

共享和动作请求在断线、取消或引擎代次变化后不自动重放。UI 保留未确认错误，并重新读取后端
状态；不会先把状态改成“已停止”或把旧截图当成新结果。

## 实现和验证入口

后端为 `engine/computer/` 与 `engine/api/computer.py`，由 `runtime_composition.compose_computer`
和 Main lifespan 装配。图像通用合同在 `ToolObservationProjection.media`、Representation 的
`model_media`、`agent/model_media.py`；公开 SDK 是兼容新增。

前端为 `features/computer/`，复用 React、TanStack Query、现有 Button/状态组件、Dock 和
Apple 设计令牌，覆盖键盘焦点、浅/深色、窄面板与减弱动态。没有新增前端耐久状态机。

确定性授权验证：`test_computer_store.py`、`test_computer_cancellation.py`、`test_model_media.py`。
交互桌面验证：`test_computer_browser.py`、`test_computer_native.py`，标记 `platform_contract`。
本地视觉模型验证：`test_computer_real_llm.py`，标记 `real_llm`，只使用已有本地模型配置；
通过 `DBFOX_COMPUTER_TEST_PROFILE` 指定，`DBFOX_COMPUTER_EVIDENCE_DIR` 保存独立夹具证据。

能力边界、复用决定和媒体合同变更依据见[架构说明](../architecture/computer-use.md)。
源码、真实本地模型、Windows 桌面及 Frozen 产物结果见
[验收记录](../quality/computer-workbench-verification.md)。
