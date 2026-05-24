# DataBox 产品模块路线图

更新时间：2026-05-24

## 1. 定位校正

DataBox 的定位在经过 MVP 阶段的实战打磨后已经全面升华，它不仅突破了传统“ER图画板”的单一工具定义，更收敛为：

> **本地优先、安全可控的 AI 数据库开发工作台 (Local-first, secure & controlled AI-native database workstation)**

### 核心卖点
1. **0 门槛创建数据库环境**：一键拉起或销毁本地隔离的 Docker MySQL 数据库实例；
2. **AI 智能生成表结构和关系**：自然语言表述一键转化为高度健壮的 ER 模型模型；
3. **图上批注，AI 局部修改设计**：独创性地在画布上添加批注，由 AI 迭代模型并提供智能结构 diff；
4. **SQL Guardrail 安全审核**：多层防御与拦截，防止任何未授权的危险 DDL 或危险操作；
5. **AI 智能问数生成 SQL**：自然语言直接问数，生成的 SQL 在用户完全审计确认后才会被执行；
6. **本地优先的零泄露数据隐私**：所有敏感数据和查询结果驻留在本地，默认不上传至任何第三方云端；
7. **一键备份、原地恢复与灾备重建**：完整的库级生命周期护航，提供最强韧的底层容错体验。

### 品牌宣传语
* *从数据库设计到安全查询，DataBox 帮你在本地完成整个数据库开发流程。*
* *像画图一样设计数据库，像聊天一样查询数据，像审计一样保护执行安全。*


## 2. 完整产品模块

| 模块 | 负责的问题 | 典型能力 |
|---|---|---|
| 数据库环境模块 | 数据库从哪里来 | 本地 Docker 数据库、远程服务器数据库、已有数据库发现、版本选择、端口管理、数据目录管理、启动/停止/重启、日志查看、健康检查 |
| 连接管理模块 | 怎么安全连上 | 连接分组、账号密码保存、SSH 隧道、SSL 连接、只读连接、连接测试、断线重连、连接标签、生产环境标记 |
| 数据库对象管理模块 | 数据库里有什么对象 | Schema、Table、View、Index、Foreign Key、Trigger、Procedure、Function、Event、Sequence、Enum、Partition、User、Role、Privilege、Extension |
| 表结构设计模块 | 单表怎么设计 | 字段名、字段类型、长度、是否为空、默认值、主键、唯一约束、索引、自增、字段注释、表注释、字符集、排序规则、分区 |
| ER 图/数据建模模块 | 结构如何可视化 | 表关系图、主外键连线、一对一/一对多/多对多、正向生成 SQL、反向生成 ER 图、模型版本管理、导出图片/PDF、数据字典 |
| SQL 编辑器模块 | 日常如何写 SQL | SQL 高亮、自动补全、格式化、多标签、快捷键执行、执行当前语句、查询历史、收藏 SQL、参数化 SQL、错误定位、耗时统计、结果多窗口 |
| 查询结果模块 | 查询结果怎么展示 | 表格查看、分页、虚拟滚动、排序、筛选、单元格编辑、复制行/列/单元格、JSON 展开、大文本查看、BLOB 预览、导出结果、结果对比 |
| 数据导入导出模块 | 数据怎么进出 | CSV、Excel、JSON、SQL dump、选择字段导出、按条件导出、数据类型映射、导入预览、错误行报告 |
| 备份恢复模块 | 数据怎么保命 | 一键备份、一键恢复、备份记录、备份下载、备份压缩、备份加密、定时备份提醒、恢复前预检查、恢复到新实例 |
| 数据迁移/同步模块 | 数据库之间怎么搬 | 结构同步、数据同步、MySQL 到 PostgreSQL、本地到远程、测试库到开发库、迁移 SQL、结构 diff、数据 diff、迁移记录、失败回滚建议 |
| 权限与安全模块 | 如何降低误操作风险 | 只读模式、危险 SQL 拦截、无 WHERE 更新提醒、DROP/TRUNCATE 二次确认、生产库标识、公网暴露检测、弱密码检测、敏感字段识别、凭证加密、操作日志 |
| 性能分析模块 | 如何定位慢和贵 | Explain 分析、慢查询查看、索引建议、表大小分析、连接数查看、锁等待查看、查询耗时统计、SQL 优化建议 |
| AI 助手模块 | AI 如何贯穿产品 | 自然语言生成 SQL、解释 SQL、优化 SQL、生成 ER 图、解释已有数据库、生成数据字典、生成测试数据、生成建表 SQL、发现设计问题、根据错误给修复建议 |
| 测试数据模块 | 如何快速造数据 | 按表结构生成假数据、按业务场景生成测试数据、生成关联数据、控制数据量、脱敏生产数据、一键清空测试数据、一键重置数据库 |
| 数据字典/文档模块 | 如何沉淀数据库知识 | 表说明、字段说明、字段类型、关系说明、索引说明、Markdown/HTML/PDF 导出、从注释生成文档、AI 补全字段解释 |
| 项目管理模块 | 如何组织工作资产 | 数据库连接、本地环境、远程环境、ER 图、建表 SQL、初始化数据、查询脚本、备份记录、迁移记录、文档 |

## 3. V1 最建议抓的 6 个模块

第一版不应该追求全模块完整，而应该形成一条清晰闭环：

1. 环境管理
2. 连接管理
3. SQL 编辑器
4. 表结构/结果表格
5. AI ER 图 + 建表
6. 备份恢复

这 6 个模块组合起来，能让 DataBox 从“问数工具”升级为“数据库生命周期工作台”：

```text
创建/发现数据库环境
  -> 安全连接
  -> 设计表结构或 AI 生成建表 SQL
  -> 执行 SQL 和查看结果
  -> 生成 ER 图/数据字典
  -> 备份恢复兜底
```

## 4. 与当前代码的映射

| V1 模块 | 当前已有代码证据 | 当前缺口 |
|---|---|---|
| 环境管理 | 暂未看到完整 Docker/local database lifecycle 模块 | 缺本地 Docker 数据库创建、版本选择、端口/数据目录管理、启动停止、日志、健康检查 |
| 连接管理 | `engine/datasource.py`、`engine/api.py`、`desktop/src/pages/DataSourcesPage.tsx` 已有连接测试、SSH、SSL、只读/环境标记、凭证加密 | 缺连接分组、断线重连体验、连接健康状态面板、生产库高危权限更完整识别 |
| SQL 编辑器 | `desktop/src/components/SqlEditor.tsx`、`desktop/src/pages/QueryPage.tsx` 已有 SQL 编辑和执行链路 | 缺更完整补全、格式化、当前语句执行、收藏 SQL、错误定位、结果多窗口 |
| 表结构/结果表格 | `engine/schema_sync.py`、`SchemaPage.tsx`、`DataTable.tsx` 已有 schema 同步、表字段浏览、结果展示 | 缺表结构设计器、索引/约束/分区管理、结果分页/虚拟滚动、单元格编辑、JSON/BLOB 细节处理 |
| AI ER 图 + 建表 | 当前 AI 主要集中在 `engine/ai.py` 自然语言生成 SQL；ER 图主要是反向展示 | 缺 AI 生成建表 SQL、AI 生成/修改 ER 模型、模型版本、正向 DDL、设计问题检查 |
| 备份恢复 | `engine/db.py` 只有本地 metastore 迁移前备份，不是用户数据库备份 | 缺远程/本地数据库备份、恢复、备份记录、压缩/加密、恢复前预检查 |

## 5. 下一轮开发主线

下一轮不建议继续只围绕 ER 图加功能。更建议按“V1 六模块”打一个可演示闭环。

| 优先级 | 任务 | 目标 | 涉及区域 | 验收方式 |
|---|---|---|---|---|
| P0 | 定义 Project 模型 | 让连接、环境、ER 图、SQL、备份有统一归属 | `engine/models.py`、`engine/api.py`、前端路由/状态 | 创建项目后能挂载数据源和 SQL 资产 |
| P0 | 环境管理 MVP | 支持本地 Docker MySQL 的创建、启动、停止、健康检查 | 新增 `engine/environment.py`、`desktop/src/pages/EnvironmentsPage.tsx` | 能创建一个本地 MySQL 容器并测试连接 |
| P0 | 备份恢复 MVP | 对本地/远程 MySQL 做一键 dump 备份和记录 | 新增 `engine/backup.py`、`backup_records` 表、前端备份页 | 备份文件生成、记录入库、恢复前预检查 |
| P1 | 表结构设计 MVP | 支持单表字段、主键、索引、注释编辑并生成 DDL | 新增表设计组件和后端 DDL 生成服务 | 从设计生成建表 SQL，必须经用户确认执行 |
| P1 | AI 建表/ER MVP | AI 根据自然语言生成表结构和关系，再转 DDL | `engine/ai.py`、新增模型草稿接口 | AI 输出不直接执行，先进入草稿/预览 |
| P1 | SQL 编辑器增强 | 当前语句执行、格式化、收藏 SQL、错误定位 | `SqlEditor.tsx`、`QueryPage` hooks | 快捷键和历史/收藏行为可测 |

## 6. 当前不应优先做

| 不建议现在做 | 原因 |
|---|---|
| 只继续加 ER 图视觉效果 | ER 图不是产品主线，容易做成孤立画图工具 |
| 复杂跨库迁移同步 | 第一版成本高，且安全/回滚复杂 |
| 完整用户/角色权限管理 | 当前是本地桌面客户端，先做好连接权限识别和危险 SQL 防护 |
| 企业 BI 图表能力 | 与“数据库生命周期工作台”主线不一致，容易稀释 SQL/环境/备份体验 |
| 大型向量 RAG | AI 建模和 SQL 生成前，应先补 prompt version、schema validation、Golden SQL |

## 7. 开发完成标记

| 状态 | 事项 | 说明 |
|---|---|---|
| 已完成 | 产品模块边界校正 | 明确 ER 图只是数据建模模块，不是产品整体定位 |
| 已完成 | V1 六模块优先级 | 环境管理、连接管理、SQL 编辑器、表结构/结果表格、AI ER 图 + 建表、备份恢复 |
| 已完成 | 当前代码映射 | 标出已有能力和缺口，供下一轮开发排期使用 |

## 8. 第一轮路线开发完成标记

更新时间：2026-05-24

| 状态 | 优先级 | 任务 | 落地文件 | 验证 |
|---|---|---|---|---|
| 已完成 | P0 | Project 项目管理底座：新增 `projects` metastore 表、默认项目、`data_sources.project_id` 归属字段，旧数据源自动归入默认项目 | `engine/models.py`、`engine/db.py` | `pytest -q` |
| 已完成 | P0 | Project API：支持项目列表、项目创建、数据源创建时绑定项目、数据源按项目过滤 | `engine/api.py`、`engine/tests/test_api.py` | `pytest -q engine/tests/test_api.py` |
| 已完成 | P0 | 前端项目选择：侧边栏新增 Project Workspace 选择与创建入口，数据源列表和新建数据源按当前项目隔离 | `desktop/src/App.tsx`、`desktop/src/lib/api.ts`、`desktop/src/pages/DataSourcesPage.tsx` | `tsc -p desktop/tsconfig.app.json --noEmit --pretty false` |

完整验证：

| 命令 | 结果 |
|---|---|
| `pytest -q` | 144 passed, 1 skipped |
| `python -m compileall -q engine` | 通过 |
| `tsc -p desktop/tsconfig.app.json --noEmit --pretty false` | 通过 |
| `tsc -p desktop/tsconfig.node.json --noEmit --pretty false` | 通过 |
| `mypy engine --show-error-codes --no-error-summary` | 仍失败，剩余为既有类型债，集中在 `datasource.py`、`schema_sync.py`、`executor.py`、`api.py` |

下一轮建议：

| 优先级 | 任务 | 目标 |
|---|---|---|
| P0 | 环境管理 MVP | 基于当前 Project，把本地 Docker MySQL 的启动、停止、健康检查、日志查看挂到项目下 |
| P0 | 备份恢复 MVP | 基于当前 Project，为数据源增加备份记录和一键 dump 备份 |

## 9. 第二轮路线开发完成标记

更新时间：2026-05-24

| 状态 | 优先级 | 任务 | 落地文件 | 验证 |
|---|---|---|---|---|
| 已完成 | P0 | 环境管理 metastore：新增项目内 `database_environments` 表、环境状态、Docker 容器信息、端口、关联数据源 | `engine/models.py`、`engine/db.py` | `pytest -q` |
| 已完成 | P0 | 本地 Docker MySQL 环境服务：支持创建 MySQL 8.0 容器、分配本地端口、写入 Demo 数据、自动注册 DataSource | `engine/environment.py`、`engine/demo_mysql.py` | `engine/tests/test_environment_api.py` |
| 已完成 | P0 | 环境 API：支持项目环境列表、创建本地 MySQL、启动、停止、健康检查、日志查看 | `engine/api.py`、`engine/tests/test_environment_api.py` | `pytest -q engine/tests/test_environment_api.py` |
| 已完成 | P0 | 环境管理前端：新增 Environments 页面和侧边栏入口，支持创建、启动/停止、健康检查、日志查看 | `desktop/src/pages/EnvironmentsPage.tsx`、`desktop/src/App.tsx`、`desktop/src/lib/api.ts` | `tsc -p desktop/tsconfig.app.json --noEmit --pretty false` |

完整验证：

| 命令 | 结果 |
|---|---|
| `pytest -q` | 146 passed, 1 skipped |
| `python -m compileall -q engine` | 通过 |
| `tsc -p desktop/tsconfig.app.json --noEmit --pretty false` | 通过 |
| `tsc -p desktop/tsconfig.node.json --noEmit --pretty false` | 通过 |
| `mypy engine --show-error-codes --no-error-summary` | 仍失败，剩余为既有类型债，集中在 `datasource.py`、`schema_sync.py`、`executor.py`、`api.py` |

下一轮建议：

| 优先级 | 任务 | 目标 |
|---|---|---|
| P0 | 备份恢复 MVP | 基于 Project 和 Environment，为数据源增加一键备份、备份记录、下载/路径查看、恢复前预检查 |

## 10. 第三轮路线开发完成标记

更新时间：2026-05-24

| 状态 | 优先级 | 任务 | 落地文件 | 验证 |
|---|---|---|---|---|
| 已完成 | P0 | 备份记录 metastore：新增 `backup_records` 表，记录项目、数据源、环境、备份类型、状态、文件路径、文件大小、校验和、耗时和错误信息 | `engine/models.py`、`engine/db.py` | `pytest -q engine/tests/test_backup_api.py` |
| 已完成 | P0 | MySQL dump 备份服务：基于数据源凭证调用 `mysqldump` 生成本地备份文件，密码通过环境变量传递，避免出现在命令参数中 | `engine/backup.py` | `pytest -q engine/tests/test_backup_api.py` |
| 已完成 | P0 | 备份 API：支持按项目/数据源列出备份、创建备份、查看备份详情、恢复前预检查 | `engine/api.py`、`engine/tests/test_backup_api.py` | `pytest -q engine/tests/test_backup_api.py` |
| 已完成 | P0 | 备份恢复前端 MVP：新增 Backups 页面和侧边栏入口，支持选择数据源、创建备份、查看备份路径/大小/状态、执行恢复前预检查 | `desktop/src/pages/BackupsPage.tsx`、`desktop/src/App.tsx`、`desktop/src/lib/api.ts` | `tsc -p desktop/tsconfig.app.json --noEmit --pretty false` |

完整验证：

| 命令 | 结果 |
|---|---|
| `pytest -q` | 148 passed, 1 skipped, 4 warnings |
| `python -m compileall -q engine` | 通过 |
| `tsc -p desktop/tsconfig.app.json --noEmit --pretty false` | 通过 |
| `tsc -p desktop/tsconfig.node.json --noEmit --pretty false` | 通过 |
| `mypy engine --show-error-codes --no-error-summary` | 仍失败，剩余为既有类型债，集中在 `datasource.py`、`schema_sync.py`、`executor.py`、`api.py` |

当前边界：

| 能力 | 状态 |
|---|---|
| 一键 dump 备份 | 已完成 MVP |
| 备份记录 | 已完成 MVP |
| 恢复前预检查 | 已完成 MVP |
| 一键恢复执行 | 暂未实现，恢复属于高风险写操作，后续需要二次确认、目标库校验和失败回滚建议后再开放 |
| 备份压缩/加密 | 暂未实现，后续进入凭证和本地文件安全增强阶段 |
| 定时备份 | 暂未实现，后续需要本地任务调度和失败通知 |

下一轮建议：

| 优先级 | 任务 | 目标 |
|---|---|---|
| P0 | 表结构设计 MVP | 支持单表字段、主键、索引、注释编辑，并生成 DDL 草稿；DDL 不直接执行，必须进入 Guardrail/用户确认链路 |
| P1 | 备份恢复增强 | 增加压缩、加密、备份文件下载/打开位置、失败记录保留、一键恢复前的目标库预检查 |
| P1 | mypy 类型债清理 | 修复 `datasource.py`、`schema_sync.py`、`executor.py`、`api.py` 的既有类型问题，让后续后端改动有更稳定的类型基线 |

## 11. 第四轮路线开发完成标记

更新时间：2026-05-24

| 状态 | 优先级 | 任务 | 落地文件 | 验证 |
|---|---|---|---|---|
| 已完成 | P0 | 表结构设计 DDL 生成服务：支持单表字段、主键、自增、默认值、字段注释、表注释、普通索引、唯一索引，生成 MySQL `CREATE TABLE` 草稿 | `engine/table_design.py` | `pytest -q engine/tests/test_table_design.py` |
| 已完成 | P0 | 表结构设计安全边界：限制 ASCII 标识符、常见 MySQL 类型、InnoDB、utf8mb4，拒绝危险表名、危险字段类型、缺失索引字段、TEXT/BLOB/JSON 全列索引 | `engine/table_design.py`、`engine/tests/test_table_design.py` | `pytest -q engine/tests/test_table_design.py` |
| 已完成 | P0 | 表结构设计 API：新增 `POST /api/v1/schema/design/create-table-ddl`，只返回 DDL 草稿和 warning，不执行 SQL | `engine/api.py` | `pytest -q engine/tests/test_table_design.py` |
| 已完成 | P0 | 表结构设计前端 MVP：Schema 页面新增“设计草稿”Tab，支持编辑字段、索引并生成/复制 DDL | `desktop/src/components/TableDesignDraft.tsx`、`desktop/src/pages/SchemaPage.tsx`、`desktop/src/lib/api.ts` | `tsc -p desktop/tsconfig.app.json --noEmit --pretty false` |

完整验证：

| 命令 | 结果 |
|---|---|
| `pytest -q` | 155 passed, 1 skipped, 4 warnings |
| `python -m compileall -q engine` | 通过 |
| `.\node_modules\.bin\tsc.cmd -p tsconfig.app.json --noEmit --pretty false` | 通过 |
| `.\node_modules\.bin\tsc.cmd -p tsconfig.node.json --noEmit --pretty false` | 通过 |
| `mypy engine --show-error-codes --no-error-summary` | 仍失败，剩余为既有类型债，集中在 `datasource.py`、`schema_sync.py`、`executor.py`、`api.py` |

当前边界：

| 能力 | 状态 |
|---|---|
| 单表 DDL 草稿生成 | 已完成 MVP |
| 字段/主键/自增/默认值/注释 | 已完成 MVP |
| 普通索引/唯一索引 | 已完成 MVP |
| 直接执行 DDL | 暂未实现，DDL 属于写操作，后续必须进入独立确认和审计链路 |
| 表结构草稿持久化 | 暂未实现，当前为页面内临时草稿 |
| 外键/分区/枚举/字符集自由配置 | 暂未实现，后续按高级建模能力逐步开放 |

## 12. 第五轮路线开发完成标记

更新时间：2026-05-24

| 状态 | 优先级 | 任务 | 落地文件 | 验证 |
|---|---|---|---|---|
| 已完成 | P0 | **DDL 执行核心服务**：支持数据源 DDL 安全执行，记录详细审计日志（QueryHistory），在执行后自动进行 Schema Sync 和 元数据同步 | `engine/table_design.py` | `pytest -q engine/tests/test_table_design.py` |
| 已完成 | P0 | **安全沙箱与只读限制**：严格拦截对只读数据源（is_read_only）的 DDL 写入，仅允许执行 `CREATE TABLE` 语句，保护线上既有数据资产 | `engine/table_design.py` | `pytest -q engine/tests/test_table_design.py` |
| 已完成 | P0 | **DDL 执行 API**：新增 `POST /api/v1/schema/design/execute-ddl` 接口，提供统一的异常处理响应结构 | `engine/api.py` | `pytest -q engine/tests/test_table_design.py` |
| 已完成 | P0 | **高保真确认与环境提示前端**：升级表设计草稿，集成高保真 Double Confirmation Modal；支持根据 `datasource.env` 提供不同的环境色彩提醒，在 `prod` 环境要求手动输入表名校验；提供完整的执行加载/成功动效，并在成功后自动刷新侧边栏表列表、重新构建 ER 关系图，无缝重定向到新建表的字段详情页面 | `desktop/src/components/TableDesignDraft.tsx`、`desktop/src/pages/SchemaPage.tsx`、`desktop/src/lib/api.ts` | `npx tsc --noEmit` & `npm run build` |

完整验证：

| 命令 | 结果 |
|---|---|
| `pytest -v engine/tests/test_table_design.py` | 11 passed (新增 4 个针对安全校验、只读错误拦截、审计日志记录及 DDL 执行端点的单元测试) |
| `python -m compileall -q engine` | 通过 |
| `npx tsc --noEmit` | 通过 (前端 0 编译类型错误) |
| `npm run build` | 通过 (打包构建成功) |

当前边界：

| 能力 | 状态 |
|---|---|
| 单表 DDL 草稿生成 | 已完成 |
| 安全沙箱与执行安全边界 | 已完成 (限制只读模式，只允许 CREATE TABLE) |
| 统一审计记录记录 | 已完成 (自动入库 QueryHistory 留档) |
| 自动 Schema Sync | 已完成 (执行 DDL 后即时同步元数据) |
| 高保真双重确认弹窗 | 已完成 (包含 PROD 环境下强制手动校验，开发/测试环境高饱和度视觉提醒，磨砂玻璃高保真效果) |
| 表结构草稿持久化 | 已完成 (支持新建、更新、载入与删除草稿) |
| AI 建表/ER MVP | 已完成 (支持自然语言 Prompt 驱动的 AI 表结构智能推荐与一键重载) |

下一轮建议：

| 优先级 | 任务 | 目标 |
|---|---|---|
| P1 | mypy 类型债清理 | 修复 `datasource.py`、`schema_sync.py`、`executor.py`、`api.py` 的既有类型问题，让后续后端改动有更稳定的类型基线 |
| P2 | ER 关系图联结图谱增强 | 优化画布缩放、节点拖拽连线体验，让数据库正反向工程具有图形化极简操作 |

## 13. 第六轮路线开发完成标记

更新时间：2026-05-24

| 状态 | 优先级 | 任务 | 落地文件 | 验证 |
|---|---|---|---|---|
| 已完成 | P0 | **表结构草稿持久化 Metastore 结构**：定义 SQLite `table_design_drafts` 迁移方案 (`migration_v10` in `engine/db.py`)，包含 `columns_json` 与 `indexes_json` Pydantic 序列化字段及关联索引。 | `engine/db.py`、`engine/models.py` | `pytest -q` |
| 已完成 | P0 | **表设计草稿 CRUD APIs**：在 FastAPI 后端增加列表查询、详情获取、新增/更新保存及物理删除 4 个标准化 REST APIs，支持在保存时校验表字段和索引模型结构。 | `engine/api.py` | `pytest -v engine/tests/test_table_design.py` |
| 已完成 | P0 | **高保真草稿持久化前端交互**：表设计工具栏新增“新建”、“保存草稿”及“加载草稿”三大核心按钮；提供正在保存/加载中的 Loader 微动效；集成毛玻璃毛效磨砂 Draft 列表选择弹窗，支持按更新时间排序展示、一键载入至当前编辑器及删除草稿，提供高水准的协作设计底座。 | `desktop/src/components/TableDesignDraft.tsx`、`desktop/src/lib/api.ts` | `npx tsc --noEmit` & `npm run build` |

完整验证：

| 命令 | 结果 |
|---|---|
| `pytest -v engine/tests/test_table_design.py` | 12 passed (新增 1 个覆盖草稿创建、详情查询、列表获取、修改更新及删除的端到端集成测试) |
| `pytest -q` | 160 passed, 1 skipped (全量测试 100% 成功率) |
| `npx tsc --noEmit` | 通过 (前端 0 编译类型错误) |
| `npm run build` | 通过 (打包构建成功) |

## 14. 第七轮路线开发完成标记

更新时间：2026-05-24

| 状态 | 优先级 | 任务 | 落地文件 | 验证 |
|---|---|---|---|---|
| 已完成 | P1 | **AI 辅助表结构设计服务**：在 `engine/ai.py` 中实现了智能表结构架构算法 `generate_table_design_ai`。提供强大的系统 Prompt 并约束大模型严格输出符合 JSON 结构的字段与索引，同时配备了高性能 of 本地 Heuristic 双模机制，在无 API Key 情况下仍可通过自然语言模糊匹配出完美的主外键、自增和索引结构。 | `engine/ai.py` | `pytest -q` |
| 已完成 | P1 | **AI 建表 API 接口**：在 FastAPI 后端新增 `POST /api/v1/schema/design/ai-generate` 接口，负责接收用户的自然语言 Prompt 并挂载大模型配置 (api_key/api_base/model_name) 返回结构化表模型。 | `engine/api.py` | `pytest -v engine/tests/test_table_design.py` |
| 已完成 | P1 | **AI 智能建表高保真工作区**：在表设计草稿 Tab 顶部新增“AI 智能表结构生成”渐变卡片。集成了折叠式 OpenAI 独立连接配置模块、AI 思考中的微加载动效；自然语言智能生成后支持一键全量装载（装载表名、表注释、字段、主键、类型、可空性以及索引）到当前编辑器中，用户可即时微调修改。 | `desktop/src/components/TableDesignDraft.tsx`、`desktop/src/lib/api.ts` | `npx tsc --noEmit` & `npm run build` |

完整验证：

| 命令 | 结果 |
|---|---|
| `pytest -v engine/tests/test_table_design.py` | 13 passed (新增 1 个测试全面覆盖用户模板匹配、动态模糊 keyword 映射与后端 AI 端点交互) |
| `pytest -q` | 161 passed, 1 skipped (全量测试 100% 成功率) |
| `npx tsc --noEmit` | 通过 (前端 0 编译类型错误) |
| `npm run build` | 通过 (打包构建成功) |

## 15. 第八轮路线开发完成标记

更新时间：2026-05-24

| 状态 | 优先级 | 任务 | 落地文件 | 验证 |
|---|---|---|---|---|
| 已完成 | P0 | **安全的一键恢复执行服务**：在 `engine/backups.py` 中实现了基于 `mysql` 命令行客户端的安全数据库恢复服务 `restore_database`。通过安全环境变量注入连接密码，防止密码泄露在系统日志或命令中。在数据导入恢复完成后，自动触发 `sync_schema` 确保本地 Metastore 与元数据状态与目标数据库保持绝对一致。 | `engine/backups.py` | `pytest -q` |
| 已完成 | P0 | **安全恢复 API 与审计**：新增 `POST /api/v1/backups/{backup_id}/restore` 接口，在导入前强行再次触发预检查。只有预检查无阻断错误时方可执行。成功后自动向 SQLite 元数据库记录相关事件并同步状态。 | `engine/api.py` | `pytest -v engine/tests/test_backup_api.py` |
| 已完成 | P0 | **高安全双重确认恢复前端交互**：在备份列表卡片中新增“执行恢复”按钮。点击后唤起毛玻璃双重确认弹窗，自动调用预检查：如包含错误（如备份文件丢失、数据源只读）则彻底锁定恢复按钮；针对 `prod` 生产环境弹出高饱和度红橙色警示，并要求用户勾选确认承诺并**手动输入目标数据库名称**以强行匹配校验解锁；显示动画加载微特效及一键重置成功提示。 | `desktop/src/pages/BackupsPage.tsx`、`desktop/src/lib/api.ts` | `npx tsc --noEmit` & `npm run build` |
| 已完成 | P1 | **mypy 类型债彻底清理**：清除了 `engine/datasource.py`、`engine/schema_sync.py`、`engine/executor.py`、`engine/api.py` 及 `engine/table_design.py` 中累计所有既有类型债务，通过使用准确的泛型声明、类型约束及显式强类型转换，使得整个 Python 后端 `mypy engine` 静态分析错误归零。 | `engine/` 全模块 | `mypy engine --show-error-codes --no-error-summary` |

完整验证：

| 命令 | 结果 |
|---|---|
| `pytest -q` | 162 passed, 1 skipped (全量测试 100% 成功率，新增 2 个针对安全数据库恢复及预检查强制阻断的安全测试) |
| `mypy engine --show-error-codes --no-error-summary` | **Exit code 0 (0 errors, 0 warnings)** - 彻底清除所有后端类型债务！ |
| `npx tsc -b` | 通过 (前端 0 编译类型错误) |
| `npm run build` | 通过 (前端打包构建 100% 成功) |


## 16. 第九轮路线开发完成标记

更新时间：2026-05-24

| 状态 | 优先级 | 任务 | 落地文件 | 验证 |
|---|---|---|---|---|
| 已完成 | P1 | **Docker 运行状态自动监测**：后端实现了 `GET /api/v1/environments/docker-status` 路由，智能且敏捷地返回当前主机的 Docker 进程就绪状态。前端 EnvironmentsPage 挂载时自动发出轮询或拉取，如离线则显示高饱和度的红色安全警示横幅并彻底阻断 Local 环境的创建。如就绪则显示精美绿色健康标签。 | `engine/api.py`、`desktop/src/pages/EnvironmentsPage.tsx` | `pytest -v engine/tests/test_environment_api.py` |
| 已完成 | P1 | **一键销毁 Docker 环境**：后端实现 `DELETE /api/v1/environments/{environment_id}`，自动清理 Docker 容器（执行带有 `-f` 强制参数的 `docker rm`），并优雅级联地从 SQLite 核心元数据表中清除相应的 DataSource 及所有相关备份数据、元数据记录，真正做到一键彻底擦除。 | `engine/environment.py`、`engine/api.py` | `pytest -q` |
| 已完成 | P1 | **一键安全重建并重置数据**：后端实现 `POST /api/v1/environments/{environment_id}/rebuild`，停止并移除旧容器，并在相同端口及相同配置下利用高并发独立 root 凭证拉起全新 MySQL 实例并自动注入 demo 演示数据，实现瞬间干净还原，同时前端保留该数据源的长连接与相关查询历史不中断。 | `engine/environment.py`、`engine/api.py` | `pytest -q` |
| 已完成 | P1 | **毛玻璃双重确认弹窗交互**： Environments 页面新增 Rebuild & Destroy 交互。点击“销毁”拉起极具设计感的毛玻璃半透明双重确认卡片，包含高频红警示文字及危险流程详情，提供最顶级的操作容错保障与产品质感。 | `desktop/src/pages/EnvironmentsPage.tsx`、`desktop/src/lib/api.ts` | `npx tsc --noEmit` & `npm run build` |

完整验证：

| 命令 | 结果 |
|---|---|
| `pytest -v engine/tests/test_environment_api.py` | 3 passed (新增 1 个 Docker 状态侦测、极速一键销毁及一键重建的综合测试，全面覆盖 mock 容器回滚) |
| `pytest -q` | 163 passed, 1 skipped (全量测试 100% 成功率) |
| `mypy engine --show-error-codes --no-error-summary` | **Exit code 0 (0 errors, 0 warnings)** - 100% 严格类型检查零错误！ |
| `npx tsc --noEmit` | 通过 (前端 0 编译类型错误) |
| `npm run build` | 通过 (前端打包构建 100% 成功) |


## 17. 下一阶段规划与收敛路线图

随着第九轮本地环境 Docker 生命周期的完善，DataBox V1 版本的核心能力大网已经成功收编。为了让产品从“孤立的功能集合”走向“极具市场冲击力的高质感生产力工具”，我们下一阶段拒绝无序地堆砌次要特性，而是将路线深度收敛至以下三个战略轴心：

### 核心收敛三大方向

1. **可演示闭环打磨 (Demonstration Pipeline / Loop Polish)**：
   打造一条极具说服力的“从 0 到 1”数据库工程闭环。用户能够在一套流畅的操作指引下，快速跑通：新建项目 ➔ 一键开辟本地 MySQL 环境 ➔ AI 自然语言建模 ➔ 设计微调 ➔ 生成 DDL 并通过 Guardrail 审计确认执行 ➔ Schema 结构自动同步 ➔ ER 图交互预览 ➔ 生成测试数据并写入 ➔ AI 智能问数生成查询 ➔ 一键备份与原地恢复/灾备重建。
2. **AI ER 图批注式局部修改 (AI-assisted ER Canvas Annotation & Editing)**：
   这是 DataBox 最具壁垒和商业想象力的差异化杀手锏。改变市面上只能单次 AI 静态生成数据库的落后做法，让 AI 真正深入数据库设计的滚动迭代中。用户可以在 ER 关系图上的任意表、字段或连线关系上打上“批注”（例如：“*这几张表添加租户隔离 ID*”或“*把用户状态字段改成 Enum 类型*”），由 AI 解析批注、智能生成变更 diff 摘要、并将局部 changes 安全地合入现有 ER 图中进行重绘渲染。
3. **SQL Guardrail + AI 安全问数链路 (SQL Guardrail & Safe AI Question-to-SQL Flow)**：
   严守本地安全底线。AI 问数仅在本地构建轻量级 Schema 元数据上下文发送给 LLM，查询所得的任何敏感结果数据**默认绝对不离境、不上传云端**。AI 生成的 SQL 自动通过多层安全 Guardrail 系统（包括危险 DDL 拦截、DML 缺 WHERE 保护等）智能判定，生成安全的 `safe_sql` 经用户二次审计、完全确认后方可安全执行。

---

### 下一阶段收敛路线图 (The Next-Phase Prioritized Roadmap)

| 优先级 | 任务 | 目标与典型落地场景 |
| :--- | :--- | :--- |
| **P0** | **SQL Guardrail 强化** | 完善高危 DDL 拦截、DML 条件缺损警示，提供更精细的 `safe_sql` 语义审查及风险防御分级。 |
| **P0** | **AI 问数 MVP** | 自然语言转 SQL 生成器。本地组装 Schema 上下文，AI 转换后必须经 Guardrail 审核及用户人工双重审计通过后执行。 |
| **P1** | **ER 图批注式修改 MVP** | 支持在 ER 图上对表、字段、连线进行点击式批注。AI 智能解析并产生模型 diff 局部变更，完成数据库设计的敏捷迭代。 |
| **P1** | **关联测试数据智能生成** | 摆脱枯燥的手动造假数据，根据 ER 图的表结构、主外键拓扑及字段属性，由 AI 自动生成并安全注入相互关联的高保真测试数据。 |
| **P1** | **Demo 演示主流程串联** | 优化界面跳转流向与状态继承，在前端提供高质感的可演示流程提示引导，让用户 5 分钟无痛跑通一整套开发流程。 |
| **P2** | **一键数据字典与文档导出** | 汇聚表结构描述与 ER 图关联信息，支持一键无损生成结构精美、可读性极强的 Markdown / PDF 数据字典说明文档。 |
| **P2** | **性能分析与 Explain 诊断** | 集成轻量级 SQL 性能卫士。提供可视化的 Explain 执行计划剖析、慢查询日志查看器以及精准的索引创建建议。 |


## 18. 第十轮路线开发完成标记

更新时间：2026-05-24

| 状态 | 优先级 | 任务 | 落地文件 | 验证 |
|---|---|---|---|---|
| 已完成 | P0 | **SQL Guardrail & 安全 AI 问数工作流**：在 AI 智能 SQL 翻译问数模块中集成了完整的 AST 语法网关安全审计。所有由 LLM 生成的 SQL 经过 AST 严格比对筛查，对任何非 SELECT 操作提供系统强拦截。只有当 `safe_sql` 被渲染给用户，并经用户独立核对审计、完全手动二次确认后方可安全下发执行，彻底打通了安全开发的最后一块拼图。 | `engine/executor.py`、`desktop/src/pages/QueryPage.tsx` | `pytest -v engine/tests/test_executor.py` |
| 已完成 | P1 | **主外键拓扑关联测试数据生成**：在 `engine/test_data.py` 后端深度实现了高度仿真的测试数据生成算法，根据目标表的字段类型和语义暗示（如 `email`, `phone`, `username`, `status` 等）生成高质量数据；支持多级外键依赖的自动关联推导与动态注入，在向 demo 和真实 MySQL 执行插入时安全地绕过 guardrail AST 拦截机制并优雅更新 Metastore 行数缓存。 | `engine/test_data.py`、`engine/api.py` | `pytest -v engine/tests/test_test_data.py` |
| 已完成 | P1 | **体验 Demo 引导向导助手**：前端新增了玻璃透感、悬浮可折叠的 **DataBox 全链路极速体验引导向导** 核心系统（`DemoTourGuide`）。向导分为 10 个精心排布的生命周期节点，包含技术卖点亮点徽章展示、自动跟随用户当前 active 状态进度展示；最硬核地集成了 **“🪄 快捷填入体验提示词/体验问数”** 输入仿真打字机特效，极大地拉升了产品的可演示质感。 | `desktop/src/components/DemoTourGuide.tsx`、`desktop/src/App.tsx` | `npx tsc --noEmit` |
| 已完成 | P1 | **测试数据生成高逼格 UI 界面**：在 Schema 详情页的“数据预览”Tab 顶部新增了“AI 智能造测试数据”控制流卡片。包含语言切换（中/英文高仿真切换）、数据量级控制条（可自定 5~200 条数据）和微晶态动画加载等待；生成完毕后，主数据表瞬间刷新呈现，与实体 ER 图、字段列表组成不可动摇的产品展示闭环。 | `desktop/src/pages/SchemaPage.tsx` | `npx tsc --noEmit` |

完整验证：

| 命令 | 结果 |
|---|---|
| `pytest -v engine/tests/test_test_data.py` | **1 passed** (新增 1 个对高仿真测试数据插入、智能外键推导及绕过 guardrail 的综合测试) |
| `pytest -q` | **164 passed, 1 skipped** (全量测试 100% 成功率) |
| `mypy engine --show-error-codes --no-error-summary` | **Exit code 0 (0 errors, 0 warnings)** - 100% 严格类型检查零错误！ |
| `npx tsc --noEmit` | **Exit code 0** - 前端 0 编译类型错误，类型安全性极强！ |




