# Answer & Artifact 架构重构设计

日期: 2026-06-20 | 状态: 设计中

---

## 问题诊断

1. **Artifact 类型混乱**：10 种 artifact 类型混在一起，内部产物和用户可见产物没有区分
2. **答案生成多条路径**：LLM 直接生成 / multi-unit composer / finalize_node 提取文本 / template fallback
3. **前端 FinalAnswerCard 承载过多**：一个组件做了所有事
4. **result.profile 多此一举**：AI 本来就会写 SQL，固定 profile 步骤替 AI 做了它能自己做的事，既不灵活又多一个工具

核心诉求：**答案才是用户最终要看的，工件是支撑数据，Agent 内部过程是调试用的。**

---

## 核心原则

1. **答案优先** — 用户第一眼看到的是结构化的 Markdown 报告
2. **不用硬编码模板** — 所有文本生成走 LLM prompt，边界情况由 prompt 覆盖
3. **AI 自己写统计 SQL** — 不替 AI 做统计，需要了解数据分布就自己查
4. **架构清晰** — 只保留必要的类型，删除冗余

---

## 一、数据模型

### 1.1 Artifact 分层

```
EVIDENCE Artifacts（用户可见，附在答案下方）:
  table   — 查询结果表格
  chart   — 可视化图表
  sql     — 生成的 SQL（供复查和复制）

PROCESS Artifacts（仅 Trace 面板，调试用）:
  query_plan     — AI 的查询计划
  sql_suggestion — SQL 生成过程的候选
  safety         — 安全检查报告
  agent_plan     — Agent 执行规划
  error          — 错误信息（仅失败时）
```

**删除的类型:**
- `insight` — result.profile 整个删除，AI 自己写统计 SQL
- `recommendation` — 属于 Answer 的一部分

### 1.2 Answer 结构

```python
class AgentAnswer(BaseModel):
    answer: str                    # Markdown 报告正文（AI 撰写）
    key_findings: list[str]        # 关键数字/发现（从 answer 中提取）
    evidence: list[AnswerEvidence] # 链接到 Evidence Artifacts
    caveats: list[str]             # 数据口径、局限性、注意事项
    recommendations: list[str]     # 可操作的下一步建议
    follow_up_questions: list[str] # 追问建议
```

**Answer 的 Markdown 结构（prompt 引导 AI 输出）:**
```markdown
## 结论
一句话总结核心发现

## 关键指标
- **发布总数：11**（成功 0，失败 11）

## 分析
说明趋势、占比、异常、规律...

## 数据口径
覆盖范围、过滤条件、时间跨度

## 建议
2-3 条可操作的下一步
```

### 1.3 AnalysisUnit（Agent 内部状态）

```python
# 每次 sql.execute_readonly 成功后追加一个 unit
# chart.suggest 按 SQL fingerprint 匹配并 enrich
{
    "id": "sql_fingerprint",
    "sql": "SELECT ...",
    "execution": {"columns": [...], "rows": [...], "rowCount": 1234},
    "chart": {...},        # 来自 chart.suggest（可选）
    "is_empty": false,
    "is_truncated": false,
}
```

### 1.4 删除的内容

| 删除项 | 原因 |
|--------|------|
| `ResultProfile` / `ColumnProfile` 类型 | AI 自己写 SQL 统计，不需要固定 profile |
| `result.profile` 工具 | 同上 |
| `engine/agent_core/result_profiler.py` | 同上 |
| `engine/agent_core/analysis_composer.py` | `build_display_plan` 不再需要，前端自己决定渲染 |
| `build_profile_artifact` | insight artifact 删除 |
| `build_recommendations_artifact` | recommendation 在 answer 里 |
| 所有硬编码回答模板字符串 | 走 LLM prompt |

---

## 二、答案生成流程

### 2.1 流程

```
Agent ReAct Loop（收集信息）
  ├─ sql.generate → 生成 SQL
  ├─ sql.execute_readonly → 执行 → 创建 AnalysisUnit
  │   （AI 如果觉得需要统计，自己再写 SQL 查 COUNT/AVG/GROUP BY 等）
  └─ chart.suggest → 建议图表 → enrich AnalysisUnit
        │
        ▼
Progress Judge 判定 "complete"
        │
        ▼
answer.synthesize 被调用（唯一入口）
  ├─ 收集所有 non-empty AnalysisUnits
  ├─ 对每个 unit，传给 LLM:
  │   • question（用户问题）
  │   • sql（执行的查询）
  │   • columns, rowCount
  │   • rows（结果行，控制数量避免 token 爆炸）
  │   • chart info（如有）
  ├─ 发送给 LLM，生成结构化 Markdown 报告
  └─ 输出 AgentAnswer
        │
        ▼
finalize_node（收尾）
  ├─ 状态标记 (completed / failed)
  ├─ 持久化到 DB
  └─ 写入 trajectory 到 memory
```

### 2.2 Answer Prompt 设计

**System Prompt 要点:**
- 角色：专业数据分析师
- 你有能力自己写 SQL 查询来验证假设和深入分析
- 输出格式：Markdown，含 ## 结论、## 关键指标、## 分析、## 数据口径、## 建议
- 如果结果是空集，直接说明，不要编造
- **加粗关键数字**
- 控制在 200-500 字
- 中文输出

**不硬编码模板 — 所有边界情况由 prompt 覆盖:**
- 空结果 → AI 自然说明
- 单行结果 → AI 自然说明
- 多 query → AI 综合对比分析

### 2.3 单 Query vs 多 Query

区别只在于传给 LLM 的 unit 数量：
- 1 个 unit → LLM 生成单 query 分析报告
- 2+ units → LLM 综合多个 query 结果
- 0 个 unit → error 路径

---

## 三、前端层级

```
┌─ Trace Timeline（思考链路，默认折叠）─────────────────┐
│  ▼ 理解问题 → 搜索表 → 生成SQL → 执行 → 统计查询 → 答案│
└──────────────────────────────────────────────────────┘
                        │
                        ▼
┌─ FinalAnswerCard（答案卡片，最显眼）──────────────────┐
│                                                       │
│  [FoxIcon] AI                                         │
│                                                       │
│  ## 结论                                              │
│  过去 6 个月共 11 次发布，全部失败…                     │
│                                                       │
│  ## 关键指标                                          │
│  **发布总数：11**  **成功率：0%**                       │
│                                                       │
│  ## 分析                                              │
│  …（Markdown 正文）…                                   │
│                                                       │
│  ┌─ 📊 支撑数据（可折叠）─────────────────────────┐   │
│  │  [查看结果表] [查看图表] [查看SQL]              │   │
│  └────────────────────────────────────────────────┘   │
│                                                       │
│  ⚠ 注意事项: 数据覆盖…                                │
│  💡 建议: 检查 CI/CD 配置                             │
└──────────────────────────────────────────────────────┘
```

**规则:**
- 答案正文永远不受折叠影响
- Evidence artifact（table/chart/sql）默认折叠
- Process artifact 仅在 Trace 面板
- 思考链路默认折叠

---

## 四、实现改动清单

### 4.1 后端

| # | 文件 | 改动 | 影响 |
|---|------|------|------|
| 1 | `engine/agent_core/types.py` | 新增 `EVIDENCE_ARTIFACT_TYPES` / `PROCESS_ARTIFACT_TYPES`；删除 `recommendation` `insight` 类型；删除 `ResultProfile` `ColumnProfile` | 中 |
| 2 | `engine/agent_core/answer.py` | 重写：统一入口，删除 profile 依赖，LLM 基于原始结果写答案，删除所有硬编码 template | **大** |
| 3 | `engine/agent_core/artifacts.py` | 删除 `build_profile_artifact` `build_recommendations_artifact`；artifact 按分层标记 | 中 |
| 4 | `engine/agent/nodes/finalize_node.py` | 简化：状态标记 + 持久化 + trajectory，不组装 answer | 中 |
| 5 | `engine/tools/runtime/state_reducer.py` | 删除 `result.profile` 相关逻辑；清理 `answer.synthesize` | 中 |
| 6 | `engine/tools/dbfox_tools.py` | 删除 `ResultProfileTool`；更新 `AnswerSynthesizeTool` context | 中 |
| 7 | `engine/agent_core/result_profiler.py` | **整个文件删除** | — |
| 8 | `engine/agent_core/analysis_composer.py` | **整个文件删除** | — |
| 9 | `engine/agent_core/chart_builder.py` | 更新 `suggest_plotly_chart` 不再依赖 `result_profile` | 中 |

### 4.2 前端

| # | 文件 | 改动 | 影响 |
|---|------|------|------|
| 10 | `desktop/src/lib/api/types.ts` | 删除 `insight` `recommendation` 类型；删除 `ResultProfile` 接口 | 小 |
| 11 | `FinalAnswerCard.tsx` | 重构：答案正文主导，evidence artifact 内联折叠 | **大** |
| 12 | `AgentTurnItem.tsx` | Process artifacts 不传给 FinalAnswerCard | 小 |
| 13 | `AnswerCard.tsx` | 合并到 FinalAnswerCard 或标记 deprecated | 小 |

### 4.3 测试更新

| # | 文件 | 改动 |
|---|------|------|
| 14 | `engine/agent/tests/test_answer_synthesis.py` | 更新测试，不再 mock profile |
| 15 | `engine/tests/test_agent_answer.py` | 更新测试 |
| 16 | `engine/evaluation/evaluators/answer_eval.py` | 删除 profile 相关评估 |
| 17 | `engine/evaluation/evaluators/artifact_eval.py` | 删除 insight artifact 评估 |

### 4.4 不变

- ReAct 循环结构
- Progress Judge 逻辑
- 思考链路折叠展开 UX
- AnalysisUnit 累积机制（去掉 profile enrichment）
- Trace 面板渲染
