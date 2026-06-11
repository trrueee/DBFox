# DataBox Agent 经验教训

## 1. LangGraph checkpoint thread 只能用 run_id，不能用 session_id

**现象：** 多轮对话到第三轮时，agent 调用 LLM 直接卡死，LangSmith 持续转圈，前端 300s 超时。

**根因：** `ctx.graph_config(thread_id)` 的 `thread_id` 决定了 LangGraph checkpoint
的存储 key。当 key 设为 `session_id` 时，同一对话的所有 run 共享一个 checkpoint
thread。第二轮、第三轮开始前，checkpoint 里已经堆积了前面所有 run 的完整 message
history + tool results。到第三轮时上下文 token 数爆炸，LLM API 调用超时。

**修复：** `thread_id = run_id`，每个 run 独立 checkpoint。
跨轮上下文通过 `follow_up_context` 传递，只传结构化摘要（schema、sql、execution），
不传完整的 message history。

**教训：** LangGraph checkpoint 不是免费的对话记忆。它序列化整个 state（包括 messages
数组），每次新 run 从 checkpoint 恢复时会把历史 messages 全部注入上下文。多轮 SQL agent
对话的 message history 增长极快（每轮 10+ tool calls），用 session 做 thread key
必然导致上下文爆炸。

---

## 2. 删除 Planner 后必须同步更新 system prompt

**现象：** 删除 Planner（`planner_node.py`）后，agent 出现两类退化：
- 简单对话（"你好"）也走完整 SQL 管线（schema → sql_generate → sql_validate →
  sql_revise），浪费 token 且答案很弱
- 模糊查询（"cookie"）不再自己搜索 schema，而是直接反问用户

**根因：** Planner 做了两件 system prompt 没做的事：
1. 初始 tool scope 控制——chat 类问题 `allowed_tool_groups=[]`，模型没工具自然直接
   回复文本
2. Clarification policy——`_apply_clarification_policy()` 判断"这个问题可以先搜
   schema 再回答，不要问用户"，然后覆盖 Planner 的 `needs_clarification` 决定

删除 Planner 后，模型拥有全部工具 + 没有 clarification policy 约束，表现为"乱调工具"
和"过度追问"。

**修复：** system prompt 加两段：
- **"When to use tools vs. respond directly"** — 明确什么时候不调工具
- **"Do the work — don't ask the user to do it"** — 模糊输入先搜索，schema 错误自己修，
  只在真正无法确定时才问用户

**教训：** Planner 虽然是"不该存在的节点"，但它承担了隐含的 scope gating 和
clarification suppression 职责。删除它后这些职责必须显式地转移到 system prompt 中。
否则模型在缺少约束时会回到"默认行为"——看到工具就用，遇到模糊就问。

---

## 3. answer.py 的 answer_synthesize 不能只读 result_profile

**现象：** "list users" 查询返回 2 个用户（admin, user1），但 answer_synthesize 输出
是："The result contains 2 profiled rows. I treated the returned rows as evidence."

**根因：** `synthesize_agent_answer()` 只读 `result_profile.notable_facts`，
从来不读 `execution.rows`（实际数据）。所以不管查出来什么数据，答案永远是一句空话。

**修复：** `execution.rows` 有数据时直接展示。≤10 行 → 格式化为文本表格嵌入答案；
>10 行 → 用 notable_facts 做摘要。

**教训：** 结构化工具的输出之间需要数据桥接。`result_profile` 和 `execution` 是互补的
——profile 提供统计摘要，execution 提供原始数据。answer synthesizer 只用一边就会产生
空洞的答案。

---

## 4. 多轮会话中的 Schema 检索污染

**现象：** 在同一个会话（Thread）的多次对话中，当前期提问涉及某些表（例如 `cookie表`），后面切换话题提问别的数据（例如 `用户数据`）时，Schema 检索（`schema_build_context`）只停留并选出了上一轮的 `cookie` 相关表，导致无法关联到正确的业务表。

**根因：** 
1. 跨轮会话时，底层会生成 `follow_up_context` 并携带上一轮的提问和所有的 SQL、结果表格等 artifacts 摘要。
2. 即使 Planner/LLM 能够理解上下文并针对本轮任务发起了纯净的工具调用 `schema_build_context(question="用户数据")`，底层的 `_request()` 辅助函数在为工具调用生成局部 `AgentRunRequest` 拷贝时，依然保留了 `follow_up_context`。
3. `schema_linking_question()` 会将 `question` 与 `follow_up_context` 中的旧问题及旧 artifacts 扁平化拼接成一个检索词（变成 `"用户数据 cookie表 SQL candidate SELECT..."`），导致 Schema Linker 的关键词打分完全被上一轮的长文本及强特征词支配，过滤掉了本轮真正相关的表。

**修复：** 
修改 `engine/tools/databox_tools.py` 中的 `_request()` 方法。当工具调用显式传入 `question` 参数时，在临时 Request 拷贝中清空 `follow_up_context`，只将当前纯净的工具检索关键词传给 Schema Linker。同时由于不改变 LangGraph 里的 `messages` 对话历史，主 LLM 的 Thread 记忆依然完整保留。

**教训：** 
在多轮检索增强（RAG）设计中，会话上下文（History）应用在 LLM 层面进行意图理解和指代消解。而对于下游的规则型/关键词检索工具（如 SchemaLinker），应该接收 LLM 消解并提炼后纯净的检索参数，而不应在工具层直接将历史上下文与检索词强行拼接，否则长历史极易造成严重的检索污染。
