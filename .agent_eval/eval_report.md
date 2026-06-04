# DataBox Agent Text-to-SQL Evaluation Report

*Generated at: 2026-06-04T17:08:24.332985+00:00*

## 📊 Overall Performance Summary

| Metric | Value |
| :--- | :--- |
| **Total Test Cases** | 3 |
| **Passed Cases** | 0 |
| **Failed Cases** | 3 |
| **Pass Rate** | **0.0%** |
| **Average Latency** | 0.31s |
| **Total Duration** | 1.1s |

## 📋 Case-by-Case Breakdown

| Case ID | DB | Difficulty | Status | Score | Latency | Reason |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `spider-smoke-1` | `concert_singer` | simple | **🔴 FAIL** | 3/5 | 0.4s | Agent SQL execution failed: (1146, "Table 'spider_concert_singer.products' doesn't exist") |
| `spider-smoke-6` | `pets_1` | medium | **🔴 FAIL** | 3/5 | 0.3s | Agent SQL execution failed: (1146, "Table 'spider_pets_1.products' doesn't exist") |
| `spider-smoke-7` | `pets_1` | medium | **🔴 FAIL** | 3/5 | 0.3s | Agent SQL execution failed: (1146, "Table 'spider_pets_1.products' doesn't exist") |

## 🔍 Deep Dive Details

### ❌ Case `spider-smoke-1` (simple)

- **Question:** How many singers do we have?
- **DB Name:** `concert_singer`
- **Gold SQL:**
  ```sql
  SELECT count(*) FROM singer
  ```
- **Agent SQL:**
  ```sql
  SELECT * FROM products LIMIT 10
  ```
- **Agent Answer:** I do not have a successful result set to analyze yet.
- **Steps:** build_schema_context, build_query_plan, generate_sql_candidate, validate_sql, revise_sql, answer_synthesizer
- **Artifacts:** query_plan, sql, safety
- **Result:** Agent SQL execution failed: (1146, "Table 'spider_concert_singer.products' doesn't exist")
- **Error:** `(1146, "Table 'spider_concert_singer.products' doesn't exist")`
- **Quality Score:** 3/5 (checks: {"completed": false, "sql_generated": true, "execution_match": false, "has_safety": true, "has_answer": true, "has_query_plan": true, "has_table": false, "has_error": true, "flow_complete": true})

<details>
<summary>💬 Agent SSE Event Stream</summary>

```json
[
  {
    "event": "agent.run.started",
    "type": "agent.run.started",
    "step": null,
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "build_schema_context",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "build_schema_context",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "build_query_plan",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "build_query_plan",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "build_query_plan",
    "error": null,
    "artifact_type": "query_plan"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "generate_sql_candidate",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "generate_sql_candidate",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "validate_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "validate_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "validate_sql",
    "error": null,
    "artifact_type": "sql"
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "validate_sql",
    "error": null,
    "artifact_type": "safety"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "revise_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "revise_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "answer_synthesizer",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "answer_synthesizer",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.answer.completed",
    "type": "agent.answer.completed",
    "step": null,
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.run.completed",
    "type": "agent.run.completed",
    "step": null,
    "error": null,
    "artifact_type": null
  }
]
```
</details>

---

### ❌ Case `spider-smoke-6` (medium)

- **Question:** Find the maximum weight for each type of pet. List the maximum weight and pet type.
- **DB Name:** `pets_1`
- **Gold SQL:**
  ```sql
  SELECT max(weight) ,  petType FROM pets GROUP BY petType
  ```
- **Agent SQL:**
  ```sql
  SELECT * FROM products LIMIT 10
  ```
- **Agent Answer:** I do not have a successful result set to analyze yet.
- **Steps:** build_schema_context, build_query_plan, generate_sql_candidate, validate_sql, revise_sql, answer_synthesizer
- **Artifacts:** query_plan, sql, safety
- **Result:** Agent SQL execution failed: (1146, "Table 'spider_pets_1.products' doesn't exist")
- **Error:** `(1146, "Table 'spider_pets_1.products' doesn't exist")`
- **Quality Score:** 3/5 (checks: {"completed": false, "sql_generated": true, "execution_match": false, "has_safety": true, "has_answer": true, "has_query_plan": true, "has_table": false, "has_error": true, "flow_complete": true})

<details>
<summary>💬 Agent SSE Event Stream</summary>

```json
[
  {
    "event": "agent.run.started",
    "type": "agent.run.started",
    "step": null,
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "build_schema_context",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "build_schema_context",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "build_query_plan",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "build_query_plan",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "build_query_plan",
    "error": null,
    "artifact_type": "query_plan"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "generate_sql_candidate",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "generate_sql_candidate",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "validate_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "validate_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "validate_sql",
    "error": null,
    "artifact_type": "sql"
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "validate_sql",
    "error": null,
    "artifact_type": "safety"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "revise_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "revise_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "answer_synthesizer",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "answer_synthesizer",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.answer.completed",
    "type": "agent.answer.completed",
    "step": null,
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.run.completed",
    "type": "agent.run.completed",
    "step": null,
    "error": null,
    "artifact_type": null
  }
]
```
</details>

---

### ❌ Case `spider-smoke-7` (medium)

- **Question:** Find number of pets owned by students who are older than 20.
- **DB Name:** `pets_1`
- **Gold SQL:**
  ```sql
  SELECT count(*) FROM student AS T1 JOIN has_pet AS T2 ON T1.stuid  =  T2.stuid WHERE T1.age  >  20
  ```
- **Agent SQL:**
  ```sql
  SELECT * FROM products LIMIT 10
  ```
- **Agent Answer:** I do not have a successful result set to analyze yet.
- **Steps:** build_schema_context, build_query_plan, generate_sql_candidate, validate_sql, revise_sql, answer_synthesizer
- **Artifacts:** query_plan, sql, safety
- **Result:** Agent SQL execution failed: (1146, "Table 'spider_pets_1.products' doesn't exist")
- **Error:** `(1146, "Table 'spider_pets_1.products' doesn't exist")`
- **Quality Score:** 3/5 (checks: {"completed": false, "sql_generated": true, "execution_match": false, "has_safety": true, "has_answer": true, "has_query_plan": true, "has_table": false, "has_error": true, "flow_complete": true})

<details>
<summary>💬 Agent SSE Event Stream</summary>

```json
[
  {
    "event": "agent.run.started",
    "type": "agent.run.started",
    "step": null,
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "build_schema_context",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "build_schema_context",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "build_query_plan",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "build_query_plan",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "build_query_plan",
    "error": null,
    "artifact_type": "query_plan"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "generate_sql_candidate",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "generate_sql_candidate",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "validate_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "validate_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "validate_sql",
    "error": null,
    "artifact_type": "sql"
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "validate_sql",
    "error": null,
    "artifact_type": "safety"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "revise_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "revise_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "answer_synthesizer",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "answer_synthesizer",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.answer.completed",
    "type": "agent.answer.completed",
    "step": null,
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.run.completed",
    "type": "agent.run.completed",
    "step": null,
    "error": null,
    "artifact_type": null
  }
]
```
</details>

---
