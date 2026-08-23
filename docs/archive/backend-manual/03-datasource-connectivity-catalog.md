# 卷三：数据源、凭据、连接与 Catalog

> 文档类型：实现指南
>
> 状态：当前
>
> 最后核验：2026-08-16
>
> 适用范围：数据源、系统凭据库、连接管理和数据库目录
>
> 权威合同：[数据、SQL 与结果链](../architecture/data-sql-results.md)、[后端架构](../architecture/backend.md)
>
> 核心入口：[`engine/connectivity/`](../../engine/connectivity/)、[`engine/security/credential_vault.py`](../../engine/security/credential_vault.py)、[`engine/environment/schema_catalog_sync.py`](../../engine/environment/schema_catalog_sync.py)

## 1. 从“保存连接”到“可查询资源”

用户在 UI 新建数据源后，后端不是简单拼出一个 DSN 并永久缓存连接。完整链路包含：

```text
API request
  → 严格 Datasource schema
  → 规范化 ConnectionProfile
  → 凭据正文写入 CredentialVault
  → metadata 保存 datasource + credential reference
  → connectivity lifecycle checkout generation
  → driver/pool/tunnel resource
  → health probe
  → authoritative schema introspection
  → Catalog sync
  → SQL/Agent tools 只通过正式资源访问
```

这条链把“配置事实”“秘密”“运行资源”“Schema 投影”分开管理。

## 2. 数据源配置模型

### 2.1 API Schema 与领域 Profile

API 输入模型位于 [`engine/schemas/datasource.py`](../../engine/schemas/datasource.py)，连接领域模型位于 [`engine/connectivity/profile.py`](../../engine/connectivity/profile.py)。

`ConnectionProfile` 是连接边界的规范模型，负责表达：

- datasource kind/dialect；
- host、port、database、username 等非秘密属性；
- SQLite/DuckDB 文件位置；
- SSL/TLS 配置；
- SSH tunnel 配置；
- credential reference；
- 可计算的 fingerprint/resource key。

API DTO 不应一路透传到 driver。边界只做一次规范化，后续组件共享同一 Profile 语义。

### 2.2 fingerprint 与 generation

fingerprint 表示影响连接资源的配置身份。generation 表示当前资源世代。

配置更新时：

1. 生成新规范 Profile；
2. fingerprint 变化则旧资源不可继续作为当前资源；
3. Lifecycle 创建/切换到新 generation；
4. 活跃旧资源按策略 drain/retire；
5. Agent Run 绑定启动时 datasource generation；
6. 恢复时若 generation 不匹配，不能偷偷复用旧上下文或结果。

## 3. 凭据边界

### 3.1 `CredentialVault`

[`engine/security/credential_vault.py`](../../engine/security/credential_vault.py) 封装系统凭据库。基本合同：

- password、API key、secret 等正文只写入系统凭据库；
- metadata 保存稳定引用、用途和状态，不保存正文；
- API 读接口不返回秘密；
- 更新使用显式 rotate/replace 流程；
- 删除要考虑引用、资源回收和失败恢复；
- 日志、事件、诊断包不记录正文。

### 3.2 `CredentialLeaseSaga`

[`engine/security/credential_lease.py`](../../engine/security/credential_lease.py) 解决系统凭据库与 SQLite 无法原子提交的问题。

典型创建/替换流程：

1. `issue`：在 metadata 记录待执行意图；
2. 写入系统凭据库；
3. `claim`：声明当前流程正在完成对应 lease；
4. 更新 datasource 的 credential reference；
5. `commit_claim`：标记 Saga 完成；
6. 异常时 `release` 或由下次启动 `reconcile`。

Reconciliation 必须是幂等的：重复执行不应删除已被正式引用的新 secret，也不应永久保留无主临时 secret。

### 3.3 禁止的凭据做法

- 把密码放进 SQLAlchemy URL 后写日志；
- 将 password/API key 写进 metadata JSON；
- 在错误消息中回显 DSN；
- 数据源健康检查失败时返回 driver 原文；
- 用 `.env.local` 作为正式用户凭据存储；
- 为避免 keyring 失败而新增明文 fallback；
- 导出外观/工作区设置时顺带导出凭据。

## 4. `ConnectionFactory`

[`engine/connectivity/factory.py`](../../engine/connectivity/factory.py) 是从 Profile 到具体连接资源的正式边界。它集中处理：

- 从 Vault 按引用读取秘密；
- MySQL/PostgreSQL/SQLite/DuckDB 的 driver 参数；
- SQLAlchemy Engine/Connection；
- 原生 client；
- 文件型 datasource；
- SSL 参数；
- tunnel endpoint；
- 资源作用域和关闭。

为什么集中：如果 health、Catalog、SQL executor、测试数据生成器分别拼 DSN，就会出现 SSL、超时、编码、路径和凭据处理不一致。

### 4.1 连接作用域

Factory 提供的是有清晰生命周期的资源，而不是“拿到后永远持有”的全局连接：

- 一次操作的原生 connection；
- 可复用但可 retire 的 Engine/Pool；
- tunnel 与依赖它的连接资源绑定；
- 文件 datasource 考虑文件锁和路径规范化；
- 操作结束或 generation 退役时释放。

## 5. `DatasourceResourceLifecycle`

[`engine/connectivity/lifecycle.py`](../../engine/connectivity/lifecycle.py) 维护运行资源世代，核心操作包括：

- `checkout`：取得与当前 Profile/generation 匹配的资源；
- `replace`：配置变化后创建并切换资源；
- `recover`：资源异常后按正式策略重建；
- `retire`：停止新 checkout，等待或关闭旧资源；
- `clear`：应用退出或 datasource 删除时清理。

### 5.1 为什么不能仅依赖连接池自动恢复

连接池能处理部分断线，但不知道 DBFox 的业务 generation、tunnel 替换、credential rotate 或 datasource 删除。Lifecycle 在连接池之上管理“这组连接是否仍代表当前配置”。

### 5.2 资源恢复边界

允许恢复：

- 明确幂等的资源重建；
- 新请求在新 generation 重新 checkout；
- 失效 idle connection 的 pool pre-ping/回收。

不允许自动重放：

- 结果不明确的非幂等业务请求；
- 已经提交给外部系统但响应丢失的写操作；
- Agent 工具未声明 recovery policy 的调用。

## 6. Health 与能力探测

数据源 health 不只是 TCP 连接成功。它通常需要区分：

- DNS/网络不可达；
- tunnel 建立失败；
- TLS 验证失败；
- 鉴权失败；
- database/schema 不存在；
- driver/系统依赖缺失；
- 连接成功但只读/metadata 权限不足。

健康结果应保存受控快照和稳定分类，原始异常进入脱敏日志。API 入口位于 [`engine/api/datasources/health.py`](../../engine/api/datasources/health.py)。

## 7. Authoritative Inventory 与 Catalog

### 7.1 三个层次

| 层次 | 实现 | 含义 |
| --- | --- | --- |
| 数据源真实 schema | 外部数据库 system catalog | 最终来源 |
| Authoritative Inventory | [`authoritative_inventory.py`](../../engine/environment/authoritative_inventory.py) | 规范化的表/列/关系清单 |
| DBFox Catalog 投影 | [`schema_catalog_sync.py`](../../engine/environment/schema_catalog_sync.py) | 可搜索、可供 Agent 使用的 metadata 投影 |

Catalog 是对外部 schema 的投影，不是外部 schema 的替代事实源。

### 7.2 `SchemaCatalogSync`

同步流程：

1. 从当前 datasource generation checkout 连接；
2. 使用 dialect-aware introspector 读取权威 schema；
3. 规范化对象、列、类型、主外键等；
4. 在 metadata 短事务中更新 Catalog 投影；
5. 在同一事务中原子递增 `DataSource.catalog_revision`；
6. 记录 datasource/schema identity 和同步状态；
6. 成功后才替换上一份可用投影。

失败时保留上一份可用 Catalog，并标记陈旧/失败信息；不能先清空再同步，否则暂时网络错误会把 Agent 的 schema 认知全部抹掉。

### 7.3 Catalog 工具分工

- `catalog_overview`：数据库规模和同步状态摘要；
- `catalog_refresh`：显式刷新权威投影；
- `schema_list`：按过滤器分页列对象；
- `schema_search`：按词或语义寻找相关对象/列；
- `schema_inspect`：查看明确目标的字段、键和关系。

“查”和“看”是两步：搜索先缩小对象集合，inspect 再读取结构。不要让模型一次请求全库所有列。

## 8. Catalog 失败为何常被误解成 Agent 失败

当 `schema_inspect` 失败时，可能的真实原因包括：

- 模型传入的 target 不符合工具 Schema；
- Catalog 尚未同步或已过期；
- target 使用展示名而非规范 identity；
- datasource generation 已变化；
- introspection 权限不足；
- 连接/TLS/tunnel 失败；
- ToolRuntime 将内部错误正确净化后 UI 信息不足。

排查顺序：

1. 查看 ToolInvocation 的 canonical input 和 policy；
2. 查看工具是否物化在当前 Turn；
3. 查看 Catalog 同步状态与 datasource generation；
4. 直接运行相同 Service/Repository 测试，而不是先改 Prompt；
5. 查看安全日志中的稳定 error code；
6. 确认公开错误没有泄漏内部详情，但有足够操作建议。

## 9. 文件型 datasource

SQLite/DuckDB 需额外考虑：

- 路径规范化和允许目录；
- 不写入安装只读目录；
- 大小写、符号链接和路径逃逸；
- 文件是否存在、是否可读；
- SQLite 只读 URI/权限；
- DuckDB 文件/临时资源；
- datasource 删除不等于删除用户文件；
- metadata SQLite 与用户 SQLite 绝不能混淆。

## 10. SSL 与 Tunnel

SSL 和 SSH tunnel 是 ConnectionProfile 的正式组成，不是 API 临时参数。

设计要求：

- SSL mode 与证书路径经过 Schema 校验；
- 不因连接失败自动降级为不验证证书；
- tunnel 生命周期与依赖资源绑定；
- 本地转发端口不成为 datasource 稳定身份；
- 错误分类区分 tunnel、TLS、auth、database；
- 诊断不输出 private key、密码或完整 DSN。

相关实现：[`engine/tunnel.py`](../../engine/tunnel.py)、[`engine/connectivity/profile.py`](../../engine/connectivity/profile.py)、[`engine/connectivity/factory.py`](../../engine/connectivity/factory.py)。

## 11. 数据源删除/更新

更新：

1. 校验新配置；
2. 若含新 secret，完成 Credential Lease Saga；
3. metadata 原子切换引用；
4. Lifecycle replace/retire；
5. 健康与 Catalog 重新同步；
6. 旧 generation 的 Run 保留历史，但不能假装连接仍相同。

删除：

1. 检查关联与产品策略；
2. 停止新资源 checkout；
3. retire/clear 运行资源；
4. 删除 metadata 引用；
5. 按 Saga 安全清理 secret；
6. 不删除用户外部数据库或文件内容，除非另有显式产品能力。

## 12. 关键测试

| 合同 | 测试 |
| --- | --- |
| Vault 不泄漏/存取 | [`test_credential_vault.py`](../../verification/tests/system/test_credential_vault.py) |
| Credentials API | [`test_credentials_api.py`](../../verification/tests/system/test_credentials_api.py) |
| 连接边界唯一性 | [`test_connectivity_boundary.py`](../../verification/tests/system/test_connectivity_boundary.py) |
| Resource lifecycle | [`test_datasource_resource_lifecycle.py`](../../verification/tests/system/test_dbfox_data_domain_model.py) |
| 数据源更新 | [`test_datasource_update_api.py`](../../verification/tests/system/test_dbfox_data_domain_model.py) |
| SSL 配置与端到端 | [`test_datasource_ssl.py`](../../verification/tests/system/test_datasource_ssl.py)、[`test_datasource_ssl_e2e.py`](../../verification/tests/system/test_datasource_ssl_e2e.py) |
| 权威 Schema sync | [`test_authoritative_schema_sync.py`](../../verification/tests/system/test_dbfox_data_domain_model.py) |
| Catalog introspection | [`test_catalog_introspector.py`](../../verification/tests/system/test_dbfox_data_domain_model.py) |
| Catalog 同步失败保留 | [`test_schema_catalog_sync.py`](../../verification/tests/system/test_dbfox_data_domain_model.py) |
| 数据源安全 | [`test_datasource_safety.py`](../../verification/tests/system/test_datasource_safety.py) |

## 13. 扩展新 datasource 类型

增加新 dialect 前必须回答：

1. 官方 driver 和 SQLAlchemy dialect 是否成熟、许可证是否可接受；
2. ConnectionProfile 如何表达其必要配置而不加猜测式 mapper；
3. secret 哪些字段进入 Vault；
4. SSL/证书/tunnel 能否复用正式边界；
5. health 如何分类；
6. Catalog introspector 如何读取权威 schema；
7. SQL parser/safety/readonly/parameter binding 是否支持；
8. Result serialization 和分页语义如何验证；
9. 资源 generation 如何 replace/retire；
10. 有哪些真实集成测试，而非只 mock driver。

如果这些问题未解决，不应只在 UI 下拉框增加一个数据库名称。

## 14. 修改检查表

- [ ] secret 正文只在 Vault；
- [ ] 连接参数通过 ConnectionProfile 规范化一次；
- [ ] 没有在新模块手工拼 DSN；
- [ ] 配置变化推进资源 generation；
- [ ] 旧资源可 drain/retire；
- [ ] Catalog 同步失败保留上一份可用投影；
- [ ] Agent Run 绑定 datasource generation；
- [ ] SSL 不静默降级；
- [ ] 路径和错误日志不泄漏 secret；
- [ ] 新 dialect 同时覆盖 Catalog、Safety、Execution 和 Result。
