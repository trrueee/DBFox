# Data、SQL 与结果链

> 文档类型：架构说明
>
> 状态：当前
>
> 最后核验：2026-08-28
>
> 代码边界：`dlcs/dbfox_data/`、`engine/representation.py`、`engine/api/agent_results.py`

## 1. 所有权

Data 是随产品签名发布、默认启用的 System DLC，不是 Agent Core 的内置领域。Core 只拥有 Project identity、冻结的 `ResourceScopeRef`、Tool/Policy/Approval 生命周期和 Artifact/View envelope；连接、数据库、Catalog、SQL、结果、备份与 Data Workbench 都由 `dbfox.data` 拥有。

```text
Project
  └─ dbfox.data project binding
       └─ ConnectionProfile
            ├─ DatabaseResource
            └─ DatabaseResource
                 └─ schema/table/column objects
```

`ConnectionProfile` 表示如何到达服务器，`DatabaseResource` 才是 Agent authority。Schema、Table 和 Column 是 provider object，不扩张为 Project Resource。Data durable state 位于 DLC 自己的 `state.sqlite3`；Core 数据库不镜像连接、Catalog 或查询历史。

## 2. 资源授权

Data Connector 通过公开 resource provider 暴露 Project 内的数据库 identity。发送消息时，Conversation intent 与本条显式选择交给 Core admission；服务端发现 Project resources、校验 identity、附加 canonical version，并把冻结 refs 写入 `AgentSessionInput.resource_refs_json`。

Tool 只能从 `ExtensionToolRunContext` 读取已授权资源。多个数据库同时被授权时，Tool 必须接收明确的 `database_id`；不得读取左栏 focus、active datasource、Project membership 或任何 fallback。

## 3. SQL 唯一执行链

```text
model SQL
  → dbfox.data.sql_validate
  → immutable validation Artifact
  → Core generic tool admission / approval
  → dbfox.data.sql_execute_readonly
  → durable Data result + Core Artifact envelope
```

`sql_validate` 使用 Data DLC 的 SQLGlot parser、bound-parameter fingerprint、只读 guardrail 和 provider-specific EXPLAIN/permission probe。执行端只接受验证 Artifact，不接受原始模型 SQL。跨数据库语法是否可用由具体 Data provider 决定，Core 只知道多个 `(kind, id)` 资源已被授权。

## 4. Result、Snapshot 与 Representation

普通 `dbfox.data.result_view` 是 reference-only Artifact。它保存已经校验的 SQL Artifact、绑定参数、数据库
ResourceRef、generation、查询指纹、原始观察时间和有界摘要，不把完整结果行复制进 Core 或 Data 元数据
库。打开表格、筛选、排序、profile 或导出时，Data DLC 在同一只读安全链上实时重执行来源查询。

用户或 Agent 明确要求冻结值时，Data DLC 创建独立的 `dbfox.data.snapshot` Artifact。Snapshot 才拥有
耐久值，读取时返回 `durable_snapshot`；普通 Result 返回 `live_reexecution`。来源 generation 或指纹变化
时读取必须 fail closed，不能静默改读旧 rows，也不能把快照当作 Result 的 fallback。

Core 只提供通用 Representation（同一 Artifact 的按需结构化表示）路由：

```text
GET  /api/v1/artifacts/{artifactId}/representations
POST /api/v1/artifacts/{artifactId}/representations/{representationType}/read
POST /api/v1/artifacts/{artifactId}/representations/{representationType}/stream
```

Data 为 Result 和 Snapshot 提供公共 `dbfox.dataframe.v1`。分页、排序、筛选、计数和 CSV 导出由同一
Provider 处理；返回值包含 `source_version`、`source_fingerprint`、`original_observed_at`、`read_at`、
`read_id`、`warnings` 和 `notices`。Core 不理解 SQL、列或 DataFrame，也不提供 `/page`、`/chart-data`
等领域特例。

模型只接收有界 Tool Observation 和 Artifact 引用。需要查看更多值时，通过 Data Tool 或
Representation 读取；Conversation、RunItem、Evidence 和前端 Store 都不保存完整 Result rows。

## 5. 备份、凭据与生命周期

凭据值由 Core Credential Broker 和 OS 凭据库保护，Data state 只保存 opaque reference。DLC 只能通过窄化 Host service enrollment/resolve 自己的 credential。SQLite backup 使用官方 online backup API；其他 provider 未固定官方、可验证格式前，不增加私有 dump 协议。

历史 Core Data 表由 Alembic 单向导入 DLC state，验证后删除。迁移代码是唯一允许认识旧表的边界；生产 Core 不提供双写、兼容 API、旧路径 re-export 或 Data fallback。

## 6. 主要实现入口

| 能力 | 入口 |
| --- | --- |
| package contributions | `dlcs/dbfox_data/backend/contributions.py` |
| durable domain state | `dlcs/dbfox_data/backend/store.py` |
| connection/resource | `connection.py`、`database_selection.py`、`resource_kind.py` |
| Catalog | `catalog_reflection.py`、`catalog_tools.py`、`inventory.py` |
| validation/execution | `tools.py`、`sql_admission.py`、`backend/sql/` |
| Result/Snapshot 与 DataFrame | `result_tool.py`、`result_view.py`、`result_analysis.py`、`backend/sql/sql_backed_view.py` |
| backup | `backup.py` |
| Workbench | `workbench.py`、`frontend/` |
| generic Representation dispatch | `engine/representation.py`、`engine/api/agent_results.py` |

## 7. 验证

Data 单元与 package 合同位于 `verification/tests/system/`；真实数据库、网络和 provider 边界位于 `verification/tests/integration/`。跨 Core + Data 的闭环测试必须走签名 package → snapshot → resource discovery → server authorization → production RunLoop，不能把 Data fixture 写回 Core ORM。
