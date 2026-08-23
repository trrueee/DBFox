# Data、SQL 与结果链

> 文档类型：架构说明
>
> 状态：当前
>
> 最后核验：2026-08-24
>
> 代码边界：`dlcs/dbfox_data/`、`engine/agent/artifact_view.py`、`engine/api/agent_results.py`

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

## 4. 结果与 Artifact View

完整结果保留在 Data DLC 的 durable result store，模型只拿有界 Observation/Artifact 摘要。Core 的 Artifact View API 按 active Runtime snapshot 调用 capability provider，并返回通用字段：

- `resourceVersion`：产生结果时冻结的资源版本；
- `sourceFingerprint`：capability 提供的来源指纹；
- `consistency`：当前只接受 `durable_snapshot`；
- columns、rows、pagination 和 export locator 等通用 view envelope。

Data 内部仍可使用 `queryFingerprint` 等领域字段，但只能在 Data → Core view 这一条真实边界单向映射；Core ORM、Evidence 和 API 不保存 Data 专用副本。分页、profile、chart 和 export 都读取已保存结果，不重新执行 SQL。

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
| durable result/view | `result_tool.py`、`result_view.py`、`result_analysis.py` |
| backup | `backup.py` |
| Workbench | `workbench.py`、`frontend/` |
| generic view dispatch | `engine/api/agent_results.py` |

## 7. 验证

Data 单元与 package 合同位于 `verification/tests/system/`；真实数据库、网络和 provider 边界位于 `verification/tests/integration/`。跨 Core + Data 的闭环测试必须走签名 package → snapshot → resource discovery → server authorization → production RunLoop，不能把 Data fixture 写回 Core ORM。
