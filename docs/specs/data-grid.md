# DBFox 数据网格与值查看规范

> 文档类型：产品与交互规范
>
> 状态：当前
>
> 最后核验：2026-08-21
>
> 适用范围：表数据预览、SQL 查询结果、Agent Result Artifact 与单元格值查看

关联文档：

- [前端架构](../architecture/frontend.md)
- [SQL 与结果架构](../architecture/data-sql-results.md)
- [错误边界合同](../architecture/error-boundary-contract.md)

## 1. 背景与问题

DBFox 已有 TanStack Table、SQL Result Gateway、分页、筛选、排序、CSV 导出、JSON 树和图片入口，但值查看能力曾分散在多个位置：

- 表数据预览自行处理选择、复制、JSON 对话框和日期显示；
- Result Artifact 在分页 Hook 中把所有值转为字符串；
- 图片、普通 URL、JSON 和长文本各自决定点击行为；
- `null` 在 Result Artifact 路径中被转换为空字符串，无法再区分 SQL `NULL` 与空文本；
- 二进制在 Engine 传输边界已变成 `<binary>`，前端却没有明确说明原始字节不可用；
- 远程图片直接下载需要通用网络和文件写入能力，不能由 WebView 临时拼接。

这些问题的根因不是缺少更多组件，而是缺少唯一、可验证的“单元格值呈现合同”。

## 2. 目标

1. 表数据预览、SQL 控制台结果和 Agent 结果表使用同一套值分类与查看语义。
2. 网格保持数据库工具所需的高信息密度，不在行内展开复杂内容。
3. `NULL`、空字符串、字符串 `"NULL"`、零和 `false` 保持不同语义。
4. JSON、长文本、URL、图片和二进制的可用操作可预测、可访问且安全。
5. 悬浮只提供快速查看，点击提供完整查看，复制、外部打开和下载是明确的次级操作。
6. 保留现有只读 SQL、Result Artifact、分页和导出架构，不创建第二套数据执行链。

## 3. 非目标

- 本阶段不实现单元格编辑、行新增、行删除或数据库写回。
- 不把数据库值转换为另一套持久化领域模型。
- 不根据列名猜测敏感性、图片或业务语义。
- 不恢复 Engine 已经丢弃的原始二进制字节。
- 不通过任意 WebView HTTP 权限、自建图片代理或 URL 参数改写实现下载。
- 不为每种数据库方言建立独立前端渲染器。

## 4. 设计依据

- [DataGrip View data](https://www.jetbrains.com/help/datagrip/tables-view-data.html) 使用紧凑表格、独立 Value Editor、图片查看和单记录视图，避免复杂值撑大主网格。
- [DataGrip Cells](https://www.jetbrains.com/help/datagrip/cells.html) 将完整长文本和与类型相关的快捷操作放在单元格的辅助查看层。
- [DBeaver Value Panel](https://dbeaver.com/docs/team-edition/desktop/Value-Panel/) 以统一 Value Viewer 承载 Text、JSON、Binary、Image 等专用展示和按类型动作。
- Electron 官方 `dialog`/`shell` 与 Node 标准网络/文件 API 能在 Main 边界实现原生能力。DBFox 不应为了下载一张数据库图片向 Renderer 暴露通用 HTTP 与文件写入权限。

DBFox 采用这些产品边界，但不复制其编辑器、插件系统或写回能力。

## 5. 唯一值呈现边界

### 5.1 输入

单元格呈现只接收当前真实边界已经拥有的信息：

```text
value            API 返回的序列化值，允许 string/number/boolean/null/object
columnName       列名，仅用于标题和无障碍描述
databaseType     可选的数据库列类型或 Result Artifact 列类型
transportState   可选的截断、脱敏或不可用标记
```

不得用列名、表名或 Provider 名称推断数据类型。`databaseType` 存在时优先；值形态只用于补充识别 URL、图片 URL、JSON 文本和长文本。

### 5.2 分类结果

前端分类结果只在渲染期存在，不持久化、不回传后端：

```text
null | boolean | number | datetime | json | image-url | url | binary-placeholder | text
```

这是 UI 边界的一次单向分类，不是 DTO、兼容 Mapper 或第二份事实来源。

### 5.3 分类优先级

1. `value === null || value === undefined`：`null`。
2. 值为布尔或列类型为布尔：`boolean`。
3. 值为数字或列类型为确定的数值类型：`number`。
4. 值等于 Engine 的受控二进制占位 `<binary>`，且列类型属于 binary/blob：`binary-placeholder`。
5. 列类型为 JSON，或值能完整解析为 JSON 对象/数组：`json`。
6. 值为合法 HTTPS 且符合受支持图片后缀或已知图片处理参数：`image-url`。
7. 值为其他合法 HTTPS：`url`。
8. 列类型为日期时间且值能按现有日期合同格式化：`datetime`。
9. 其他值：`text`。

未知或矛盾输入必须降级为文本，不抛出渲染异常。

## 6. 三层交互模型

### 6.1 网格摘要

网格始终保持单行和有界宽度：

| 类型 | 网格摘要 |
| --- | --- |
| NULL | 中性 `NULL` 标记 |
| 布尔 | `true` / `false`，不使用大面积彩色胶囊 |
| 数值 | 等宽数字、右对齐 |
| 日期时间 | 统一的本地显示格式 |
| JSON | `JSON · Object(n)` 或 `JSON · Array(n)` |
| 长文本 | 类型弱标签 + 单行摘要 |
| 普通 URL | 链接图标 + 省略文本 |
| 图片 URL | 图片图标 + 省略文本，不自动创建 `<img>` |
| 二进制占位 | `BINARY · 未加载` |

### 6.2 快速查看

- JSON、长文本和图片支持悬浮快速查看。
- 图片必须稳定悬浮约 400ms 后才创建 `<img>`；在延迟内移开不产生请求。
- 文本和 JSON 可使用较短延迟，但不得遮挡当前单元格和主要操作。
- 悬浮不是唯一入口；触控、键盘和减少动效环境仍可通过点击或 `Enter` 打开完整查看。
- 固定尺寸预览只控制布局，不代表减少网络下载量。没有服务端缩略图合同时，图片仍可能下载原始字节。

### 6.3 完整 Value Viewer

- `Enter` 或点击明确的值入口打开统一 Value Viewer。
- Viewer 标题显示列名、数据库类型和当前值类型。
- JSON 使用可折叠树；长文本保留换行并支持软换行；图片使用 `object-fit: contain`；普通 URL 显示完整地址；二进制占位解释“原始字节未进入当前结果合同”。
- Viewer 的关闭、焦点返回和键盘操作使用现有 Radix Dialog。
- 选中单元格与打开 Viewer 是两个状态：点击单元格空白区域只选择，点击值入口或按 `Enter` 才打开 Viewer。

## 7. 操作能力矩阵

| 操作 | NULL | 标量/日期 | JSON/长文本 | URL | 图片 URL | 二进制占位 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 选择单元格 | 是 | 是 | 是 | 是 | 是 | 是 |
| 复制原始文本 | 是 | 是 | 是 | 是 | 是 | 是（复制占位说明） |
| 完整查看 | 否 | 可选 | 是 | 是 | 是 | 是（说明页） |
| 浏览器打开 | 否 | 否 | 否 | 是 | 是 | 否 |
| 应用内图片预览 | 否 | 否 | 否 | 否 | 是 | 只有未来取得原始字节后才允许 |
| 保存到文件 | 否 | 可保存文本 | 可保存 `.txt` / `.json` | 否 | 见 7.1 | 只有未来取得原始字节后才允许 |

复制操作复制真实序列化值，而不是视觉摘要。CSV 导出继续由现有 Result Gateway 在后端生成，不读取 DOM，也不从当前页拼接“全量导出”。

### 7.1 远程图片保存

应用内“保存图片”是独立安全能力，不与预览点击混用。正式实现必须位于 Electron Main 边界，并满足：

1. 使用 Node 官方 HTTPS 客户端和 Electron 保存对话框；不向 Renderer 暴露通用文件写入或任意 HTTP 能力。
2. 只允许无用户名密码的 HTTPS URL。
3. DNS 解析结果和每次重定向目标均拒绝 loopback、link-local、private、multicast 和 unspecified 地址。
4. 限制重定向次数、连接/总超时、响应体大小和并发数。
5. 只接受受支持的 `image/*` MIME，并以实际内容或受控扩展名决定默认文件名。
6. 在用户目标目录创建临时文件并完成同步，再以原子持久化完成保存；失败删除半成品。
7. 不记录完整 URL 或查询参数；界面只展示固定、可公开的失败原因。

当前实现使用 Node `https`/`dns`/`fs` 和 Electron Dialog：限制为标准端口 HTTPS，逐跳校验 DNS 与重定向目标，禁用系统代理，限制为 2 个并发、3 次重定向、20 秒总超时和 20 MB，并校验 MIME 与文件签名。保存是完整查看器中的独立动作，不会替代“应用内预览”和“在浏览器打开”。

## 8. 表格级统一行为

所有 DBFox 数据网格至少遵守以下规则：

- 单击选择一个单元格；选中样式不改变数据颜色语义。
- `Ctrl/Cmd+C` 复制选中单元格的真实序列化值。
- `Enter` 打开可查看值；方向键移动焦点。
- 表头排序、筛选、隐藏、固定、复制列名走同一交互命名。
- 筛选和排序由 SQL Result Gateway 在后端编译与执行，不在当前页伪造全量结果。
- 搜索、分页和刷新保留上一批结果直到新结果就绪；错误不会清空仍可用数据。
- CSV 导出使用当前筛选和排序合同，并保留既有公式注入防护和脱敏血缘。
- 空状态、加载状态、错误状态和截断状态在表格容器内显示，不改变工作区信息架构。

### 8.1 Result Artifact 的表格与 SQL 视图

SQL 查询产生的 Result Artifact 在工件区保持一个工件身份，但允许在同一卡片内切换两种只读呈现：

- **表格**：默认视图，继续使用 Result Artifact ID 进行分页、搜索、排序、筛选和 CSV 导出。
- **SQL**：显示该 Result Artifact 通过 `sourceSqlArtifactId` 明确引用的来源 SQL Artifact，并提供复制和打开 SQL 控制台操作。

切换只改变前端呈现状态，不创建第二个结果工件、不复制结果数据、不重新执行查询，也不改变 Artifact、Evidence 或 Run 的身份与状态。前端只能按精确的 `sourceSqlArtifactId` 解析来源；引用缺失、类型不符或 SQL 为空时不显示 SQL 切换，禁止回退到“最近一条 SQL”或通过查询指纹猜测。

## 9. 传输合同与已知边界

当前 Engine `row_serializer` 会：

- 保留 `null`；
- 把 Decimal 和日期转换为字符串；
- 把 bytes 转换为 `<binary>`；
- 对超长单元格追加 `...`；
- 只在结果级记录是否发生过 cell truncation，不标记具体单元格。

因此本功能必须先保证前端不再把 `null` 转为空字符串。后续若要支持可靠的单元格截断标记、BLOB 图片查看或原始值下载，应扩展现有 Result Page 合同，而不是让前端根据 `...` 或 `<binary>` 猜测。

## 10. 实施阶段

### 阶段一：统一只读呈现

1. Result Gateway 保留 `unknown` 标量，不再全量字符串化。
2. 建立单一 `classifyCellValue`，由 `CellValuePreview` 和完整 Viewer 共同使用。
3. 表预览和 Artifact 结果表都传入 `databaseType`。
4. 统一 NULL、数字、日期、布尔、JSON、长文本、URL、图片和二进制占位显示。
5. 图片增加延迟悬浮预览；点击进入应用内完整预览；外部打开保持次级操作。
6. 删除 `TablePreviewPane` 中只处理 JSON 的独立详情状态和重复判断。

### 阶段二：统一选择与操作

1. [已完成] 统一两类表格的选择与键盘语义，不提取表格数据获取逻辑。
2. [已完成] Artifact 结果表不再“单击即复制”；单击只选择，复制由快捷键或明确操作触发。
3. [部分完成] Value Viewer 已统一复制与浏览器打开；文本/JSON 文件保存仍需单独产品需求确认。
4. [已完成] 统一单元格操作命名和无障碍标签；行级操作不在本轮范围。

### 阶段三：受控远程图片保存与二进制合同

1. [已完成] 单独实现并测试 Electron Main 下载能力及 SSRF/文件边界。
2. [部分完成] 已实现受控图片保存和确定性边界测试；真实 macOS/Linux 文件对话框与网络故障仍未验证。
3. [待产品确认] 如产品需要 BLOB，扩展 Result Page 为可回源的值引用，不把大字节直接注入普通分页响应。

## 11. 验收场景

### 11.1 数据语义

- SQL `NULL`、空字符串、字符串 `"NULL"`、`0` 和 `false` 显示和复制结果互不混淆。
- 数值列即使以字符串传输仍按列类型右对齐，但非数值字符串不被强制转换。
- 日期只在列类型和格式均成立时格式化；失败时显示原文。
- `<binary>` 只有在二进制列中显示为不可用占位，普通文本值 `<binary>` 保持文本。

### 11.2 复杂值

- JSON 对象/数组在两个表格入口均显示相同摘要和树形 Viewer。
- 长文本摘要不撑高行，Viewer 保留原始换行。
- 图片在未悬浮、悬浮不足 400ms 和普通浏览表格时不发起请求。
- 图片稳定悬浮后出现有界预览；点击后出现完整 Viewer；加载失败有固定错误状态。
- 普通 HTTPS URL 不被当作图片，且只有明确操作才打开系统浏览器。
- HTTP、`file:`、`javascript:` 和带用户名密码的 URL 不可打开、不可预览。

### 11.3 表格行为

- 表预览与 Artifact 表均支持选择、方向键、复制和完整查看，不发生点击动作冲突。
- 内部按钮点击不触发行选择、复制或外部跳转的其他动作。
- 排序、筛选、搜索、分页、刷新和导出仍由现有 Result Gateway 完成。
- 失败刷新保留上一批可用数据，错误状态可见。
- 带有效来源 SQL 的 Result Artifact 默认显示表格，可切换到精确来源 SQL；切换本身不触发新的结果请求或 SQL 执行。
- 缺失来源 SQL、错误类型引用或空 SQL 时不显示 SQL 视图，且不会展示同一 Run 中的其他 SQL。

### 11.4 工程门禁

- 分类器使用表驱动单元测试覆盖全部类型和矛盾输入。
- 两个真实网格分别有集成测试。
- CSP 仍只为图片放宽 `img-src https:`，不放宽通用 `connect-src`。
- 前端完整测试、类型检查、lint、设计合同和生产构建通过。

## 12. 复用与自研决定

| 能力 | 决定 | 原因 |
| --- | --- | --- |
| 表格与列状态 | 继续使用 TanStack Table | 现有实现成熟且已覆盖列宽、固定、排序和可见性；迁移大型 Grid 无直接收益 |
| 悬浮、对话框和菜单 | 继续使用 Radix UI 封装 | 已在项目中使用，焦点和无障碍边界清晰 |
| JSON 树 | 复用现有 `JsonTree`，补充有界展示 | 当前只读需求简单，引入大型 JSON 编辑器成本过高 |
| 值分类 | 在真实 UI 边界自行实现小型纯函数 | 数据库元数据与 DBFox 传输合同是项目特有输入；第三方库无法替代该判断 |
| CSV | 复用后端 Result Gateway 与现有 CSV 防护 | 避免 DOM 导出、全量内存加载和双轨 SQL |
| 外部打开 | 复用 Electron Main URL 校验 + `shell.openExternal` | 已有前后端双重 HTTPS 合同 |
| 图片下载 | 使用 Node 标准库 + Electron Dialog 的受控 Main 能力 | Renderer 通用 HTTP/FS 权限不满足安全边界；Main 可集中执行 SSRF、大小和格式校验 |

本设计不新增兼容层、双向 Mapper、第二套 Result Gateway 或第二套表格执行路径。
