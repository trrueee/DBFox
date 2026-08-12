# Agent 会话档案检索合同

> 文档类型：架构决定
>
> 状态：已接受
>
> 最后核验：2026-08-06
>
> 适用范围：Agent 会话档案、历史检索、上下文装配和审计

## 1. 决策

DBFox 将完整会话档案、当前模型上下文和跨会话长期记忆视为三个不同能力：

```text
AgentMessage（完整、耐久、可审计的唯一事实来源）
  ├─ ContextAssembler（当前 Run 的有界工作上下文）
  ├─ FTS5 派生索引（当前 Session 的按需搜索）
  └─ conversation_search / conversation_read（模型可调用的只读召回工具）

AgentSessionMemory（受限的稳定工作状态，不代替完整会话档案）
Artifact / Observation（数据库证据和工具结果，不代替会话档案）
```

首期只实现当前 Session 内的精确会话召回。不会引入跨 Session 语义记忆、向量数据库、第二套 Session、第二套 Agent Runtime 或模型自动写长期记忆。

## 2. 参考设计与复用判断

调查过的成熟设计：

- OpenAI Agents SDK Session 将完整会话历史保存在 SQLite、SQLAlchemy 等后端，模型输入可以独立限制最近条目；Compaction 负责长上下文延续，但不应成为业务事实的唯一来源。
- OpenAI Sandbox Memory 将跨 Run 经验提炼为后台生成的记忆文件，并明确把工作结论和引用保留在可审计 Artifact 中。
- Codex 将单个任务的 transcript 与后台生成的 local memories 分开；memory 是辅助召回层，不是强制规则和完整历史的唯一来源。
- LangGraph 将 Checkpoint（线程内耐久执行状态）与 Store（跨线程长期记忆）分开；LangMem 进一步区分 semantic、episodic 和 procedural memory。
- Letta 将始终在上下文中的 Memory Blocks、可搜索的 conversation history 和外部 archival memory 分开。
- SQLite FTS5 提供官方的全文索引、`MATCH`、`bm25()` 和 `snippet()`，适合作为本地单用户桌面应用的第一阶段检索实现。

采用方案：

- 复用现有 `AgentMessage`、SQLAlchemy Session、Alembic、SQLite FTS5、`ToolRuntime`、`ContextAssembler` 和共享脱敏合同。
- 新增可重建的 `agent_message_search_docs` / `agent_message_fts` 派生索引。
- 新增两个 provider-neutral 严格函数：`conversation_search` 和 `conversation_read`。

不采用：

- 不引入 OpenAI Agents SDK、LangGraph、LangMem 或 Letta 作为运行依赖；它们会与 DBFox 已有 Session、RunLoop、工具恢复和审批边界重叠。
- 不恢复历史上已经移除的 embedding recall；精确历史、中文片段和顺序读取应先用本地 FTS 与关系查询完成，并通过 eval 证明不足后再决定是否需要语义索引。
- 不将压缩摘要作为完整历史；摘要可能遗漏、漂移或被错误事实污染。

参考资料：

- https://openai.github.io/openai-agents-python/sessions/
- https://openai.github.io/openai-agents-python/sandbox/memory/
- https://developers.openai.com/cookbook/examples/agents_sdk/building_reliable_agents_memory_compaction
- https://learn.chatgpt.com/docs/customization/memories
- https://langchain-ai.github.io/langmem/concepts/conceptual_guide/
- https://docs.letta.com/guides/core-concepts/memory/context-hierarchy
- https://www.sqlite.org/fts5.html

## 3. 权威数据和索引合同

`agent_messages` 是会话内容的唯一事实来源。搜索索引只保存以下可重建投影：

```text
message_id, session_id, sequence, role, status, search_text, created_at
```

索引必须满足：

1. 由 Alembic 创建，Runtime 只断言合同存在，不在启动时自行修复 DDL。
2. 通过 SQLite trigger 与 `agent_messages` 的 insert/update/delete 同步。
3. 迁移时回填既有消息并执行 FTS rebuild。
4. 搜索结果必须回连 `agent_messages` 和 `agent_sessions`，不能把索引投影当作权威消息。
5. 索引可以删除并重建，不得承载新业务状态。
6. Session 删除、软删除、归档和身份隔离规则以权威表为准。

## 4. 工具合同

### 4.1 `conversation_search`

用途：当早期消息未进入当前 Prompt，或用户询问先前讨论、精确措辞和历史决定时，在当前 Session 中搜索相关消息。

输入：

```text
query: 1..500 字符（空白会被拒绝）
roles: user | assistant 的可选集合
limit: 1..20，默认 10
```

输出：

```text
matches[]:
  message_id
  sequence
  role
  created_at
  snippet
returned_count
search_mode: fts5_trigram | literal_scan
```

约束：

- `session_id` 只能从 `ToolRunContext.require_request()` 取得，模型不能传入。
- 只返回 `user` 与状态为 `completed` 的 `assistant` 消息。
- 不返回 system、reasoning、Provider 原始事件、内部错误或工具原始结果。
- 输出进入 Provider 前必须使用共享文本脱敏，并受条目数、单条字符数和总输出字节限制。
- 没有匹配只证明本次受限查询没有结果，不证明历史中不存在相关内容。
- 三个及以上字符使用 FTS5 trigram；一至两个字符因 tokenizer 合同限制，使用当前 Session 内、绑定参数且限制返回条数的字面扫描。该路径是显式输入合同，不是异常 fallback。

### 4.2 `conversation_read`

用途：从当前 Session 按稳定 `sequence` 读取连续消息，或读取一个搜索命中附近的上下文。

输入：

```text
after_sequence: 非负整数，默认 0
limit: 1..10，默认 10
```

输出：

```text
messages[]:
  message_id
  sequence
  role
  created_at
  content
returned_count
has_more
next_after_sequence
```

约束：

- 使用 keyset pagination，不使用不稳定的 offset pagination。
- 只能读取当前 Session。
- 每条内容和总输出均有硬上限；截断必须显式标记。
- 返回文本是非可信数据，不能成为系统指令。

## 5. Context 和 Prompt 合同

`ContextAssembler` 应提供一个很小的 `conversation_archive` 元数据块：

```json
{
  "oldest_sequence": 1,
  "newest_sequence": 186,
  "message_count": 186,
  "loaded_message_count": 20,
  "omitted_message_count": 166,
  "search_available": true
}
```

它只告诉模型“完整历史是否还有未装载内容”，不复制历史正文。

系统提示应要求：

- 用户询问早期内容、精确措辞、历史决定或“本轮全部讨论”且当前上下文不完整时，使用会话召回工具。
- 不得仅依据当前 Prompt 断言某件事从未讨论过。
- `conversation_search` 负责定位，`conversation_read` 负责精确连续读取。
- 不要在普通数据库分析中无理由搜索会话历史。

## 6. 安全与隐私

- 当前 Session 是首期唯一授权边界，不支持模型指定其他 Session、用户或数据源。
- Provider 可见的命中片段和消息内容使用现有共享脱敏逻辑；本地 UI 中的原始 transcript 不因该工具而改变。
- 搜索结果使用 XML/结构化数据边界标记为 untrusted data。
- 删除 Session 后，级联删除搜索投影；软删除 Session 不再允许工具检索。
- 工具为 `metadata_read`、`parallel_safe`、`retry_safe`，不修改会话和记忆。
- 搜索查询使用绑定参数；FTS 查询表达式由 Runtime 生成，不能把模型输入直接解释为任意 FTS 语法或 SQL。

## 7. 验收不变量

1. 一个已被 Context Budget 淘汰的早期事实，可以通过 search → read 找回并正确回答。
2. 当前 Session 的工具不能读取另一个 Session 的消息。
3. Assistant 草稿、失败消息和 reasoning 不进入召回结果。
4. 搜索输入中的引号、FTS 操作符和 SQL 片段不会改变查询结构。
5. 中文和英文消息均有确定性检索测试；若正式 SQLite 不支持选定 tokenizer，迁移必须失败而不是静默降级。
6. 长消息和大量结果始终有结构化截断及下一页游标。
7. Token、Authorization、DSN、邮箱、电话和卡号在 Provider 工具输出中被脱敏。
8. 迁移升级会回填历史消息，降级会完整移除投影、FTS 表和 triggers，不删除 `agent_messages`。
9. 进程重启后，搜索和顺序读取仍从耐久数据库恢复。
10. 没有新增向量数据库、兼容 mapper、第二套 Session 或双写事实来源。

## 8. 实施链路

```text
AgentMessage INSERT / UPDATE / DELETE
  -> SQLite trigger（同一事务）
  -> agent_message_search_docs（可重建投影）
  -> FTS5 external-content trigger
  -> agent_message_fts

模型调用 conversation_search
  -> ToolRunContext 提供不可伪造的当前 session_id
  -> FTS/短词字面定位
  -> 回连 AgentMessage + AgentSession
  -> 角色/状态/软删除过滤
  -> DataRedactor.redact_text
  -> 当轮 provider_payload
  -> Observation 仅保存数量和 sequence，不保存召回原文

模型调用 conversation_read
  -> 当前 Session 的 AgentMessage keyset page
  -> 同样的过滤、脱敏、字符/字节预算
  -> 当轮 provider_payload
  -> Observation 仅保存分页事实
```

实施没有新增 Python 或前端依赖。SQLite FTS5 是正式 Python Runtime 已启用的内建能力；Schema 由 Alembic 唯一拥有，工具层不会建表或修表。

## 9. 验证记录

- 迁移 head：`13bc45de67f0`。
- 单元/合同覆盖：FTS trigger 插入、状态完成、内容更新、删除；中文 trigram；中文短词；注入样式输入；Session 隔离；失败 Assistant 排除；稳定 sequence 分页；Provider 脱敏；Observation 最小持久化。
- Harness 覆盖：30 条旧消息使最早决定退出 24 条活动历史窗口；正式 RunLoop 依次调用 `conversation_search`、`conversation_read`，第三轮在 `phase=None` 的合法完成消息中正确回答。
- 迁移覆盖：新库升级、历史消息回填、降级保留 `agent_messages`，并移除所有派生表和 trigger。

## 10. 后续重新评估

只有当真实长会话 eval 证明 FTS 的召回率不足，并且缺失集中在“同义表达而非精确历史定位”时，才评估跨 Session semantic memory。届时必须单独决定：命名空间、来源引用、冲突合并、过期、删除、用户控制、embedding 模型和本地打包成本。
