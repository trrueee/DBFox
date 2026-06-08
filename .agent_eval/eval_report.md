# DataBox Agent Text-to-SQL Evaluation Report

*Generated at: 2026-06-06T13:13:43.472519+00:00*

## 📊 Overall Performance Summary

| Metric | Value |
| :--- | :--- |
| **Total Test Cases** | 50 |
| **Passed Cases** | 27 |
| **Failed Cases** | 23 |
| **Pass Rate** | **54.0%** |
| **Average Latency** | 31.42s |
| **Total Duration** | 1610.55s |

## 📋 Case-by-Case Breakdown

| Case ID | DB | Difficulty | Status | Score | Latency | Reason |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `spider-dev-001` | `concert_singer` | easy | **🟢 PASS** | 5/5 | 28.8s | Execution match |
| `spider-dev-002` | `concert_singer` | easy | **🟢 PASS** | 5/5 | 20.9s | Execution match |
| `spider-dev-003` | `concert_singer` | easy | **🟢 PASS** | 5/5 | 24.8s | Execution match |
| `spider-dev-004` | `concert_singer` | easy | **🟢 PASS** | 5/5 | 19.5s | Execution match |
| `spider-dev-005` | `concert_singer` | easy | **🔴 FAIL** | 3/5 | 35.1s | Result mismatch: Column count mismatch: gold=2, agent=3 |
| `spider-dev-006` | `concert_singer` | easy | **🔴 FAIL** | 3/5 | 36.3s | Result mismatch: Column count mismatch: gold=2, agent=3 |
| `spider-dev-007` | `concert_singer` | easy | **🟢 PASS** | 5/5 | 39.8s | Execution match |
| `spider-dev-008` | `concert_singer` | easy | **🟢 PASS** | 5/5 | 31.6s | Execution match |
| `spider-dev-009` | `concert_singer` | easy | **🟢 PASS** | 5/5 | 37.3s | Execution match |
| `spider-dev-010` | `concert_singer` | easy | **🟢 PASS** | 5/5 | 22.3s | Execution match |
| `spider-dev-011` | `pets_1` | medium | **🟢 PASS** | 5/5 | 17.1s | Execution match |
| `spider-dev-012` | `pets_1` | medium | **🟢 PASS** | 5/5 | 27.6s | Execution match |
| `spider-dev-013` | `pets_1` | medium | **🔴 FAIL** | 3/5 | 38.5s | Result mismatch: Row mismatch: gold=['1.5000', 2, 'dog'], agent=['cat', '3.0000', 3] |
| `spider-dev-014` | `pets_1` | medium | **🔴 FAIL** | 3/5 | 19.2s | Result mismatch: Row mismatch: gold=['1.5000', 2, 'dog'], agent=['cat', '3.0000', 3] |
| `spider-dev-015` | `pets_1` | medium | **🔴 FAIL** | 3/5 | 21.0s | Result mismatch: Row mismatch: gold=[11.35, 'dog'], agent=['cat', 12.0] |
| `spider-dev-016` | `pets_1` | medium | **🔴 FAIL** | 3/5 | 31.6s | Result mismatch: Row mismatch: gold=[11.35, 'dog'], agent=['cat', 12.0] |
| `spider-dev-017` | `pets_1` | medium | **🔴 FAIL** | 3/5 | 33.9s | Result mismatch: Row count mismatch: gold=2, agent=3 |
| `spider-dev-018` | `pets_1` | medium | **🔴 FAIL** | 3/5 | 36.3s | Result mismatch: Column count mismatch: gold=2, agent=3 |
| `spider-dev-019` | `pets_1` | medium | **🔴 FAIL** | 3/5 | 29.2s | Result mismatch: Column count mismatch: gold=1, agent=2 |
| `spider-dev-020` | `pets_1` | medium | **🔴 FAIL** | 3/5 | 32.4s | Result mismatch: Column count mismatch: gold=1, agent=2 |
| `spider-dev-021` | `pets_1` | medium | **🟢 PASS** | 5/5 | 36.1s | Execution match |
| `spider-dev-022` | `pets_1` | medium | **🔴 FAIL** | 3/5 | 42.8s | Result mismatch: Column count mismatch: gold=2, agent=4 |
| `spider-dev-023` | `car_1` | medium | **🟢 PASS** | 5/5 | 49.8s | Execution match |
| `spider-dev-024` | `car_1` | medium | **🟢 PASS** | 5/5 | 40.4s | Execution match |
| `spider-dev-025` | `car_1` | medium | **🟢 PASS** | 5/5 | 36.6s | Execution match |
| `spider-dev-026` | `flight_2` | hard | **🟢 PASS** | 5/5 | 29.9s | Execution match |
| `spider-dev-027` | `flight_2` | hard | **🟢 PASS** | 5/5 | 18.5s | Execution match |
| `spider-dev-028` | `flight_2` | hard | **🟢 PASS** | 5/5 | 28.0s | Execution match |
| `spider-dev-029` | `flight_2` | hard | **🔴 FAIL** | 3/5 | 37.6s | Result mismatch: Column count mismatch: gold=1, agent=2 |
| `spider-dev-030` | `flight_2` | hard | **🔴 FAIL** | 3/5 | 32.9s | Result mismatch: Column count mismatch: gold=1, agent=2 |
| `spider-dev-031` | `flight_2` | hard | **🔴 FAIL** | 3/5 | 41.6s | Result mismatch: Column count mismatch: gold=1, agent=2 |
| `spider-dev-032` | `flight_2` | hard | **🔴 FAIL** | 3/5 | 44.4s | Result mismatch: Column count mismatch: gold=1, agent=3 |
| `spider-dev-033` | `flight_2` | hard | **🔴 FAIL** | 3/5 | 42.1s | Result mismatch: Column count mismatch: gold=1, agent=2 |
| `spider-dev-034` | `flight_2` | hard | **🔴 FAIL** | 3/5 | 37.1s | Result mismatch: Column count mismatch: gold=1, agent=2 |
| `spider-dev-035` | `flight_2` | hard | **🔴 FAIL** | 3/5 | 36.0s | Result mismatch: Row mismatch: gold=['Ada '], agent=['AAF'] |
| `spider-dev-036` | `employee_hire_evaluation` | hard | **🟢 PASS** | 5/5 | 32.5s | Execution match |
| `spider-dev-037` | `employee_hire_evaluation` | hard | **🟢 PASS** | 5/5 | 23.8s | Execution match |
| `spider-dev-038` | `employee_hire_evaluation` | hard | **🔴 FAIL** | 3/5 | 33.4s | Result mismatch: Column count mismatch: gold=1, agent=2 |
| `spider-dev-039` | `employee_hire_evaluation` | hard | **🔴 FAIL** | 3/5 | 26.0s | Result mismatch: Column count mismatch: gold=1, agent=2 |
| `spider-dev-040` | `employee_hire_evaluation` | hard | **🟢 PASS** | 5/5 | 24.7s | Execution match |
| `spider-dev-041` | `museum_visit` | extra | **🟢 PASS** | 5/5 | 36.2s | Execution match |
| `spider-dev-042` | `orchestra` | extra | **🟢 PASS** | 5/5 | 33.9s | Execution match |
| `spider-dev-043` | `orchestra` | extra | **🟢 PASS** | 5/5 | 24.6s | Execution match |
| `spider-dev-044` | `network_1` | extra | **🔴 FAIL** | 3/5 | 33.5s | Result mismatch: Column count mismatch: gold=1, agent=2 |
| `spider-dev-045` | `network_1` | extra | **🟢 PASS** | 5/5 | 20.1s | Execution match |
| `spider-dev-046` | `network_1` | extra | **🟢 PASS** | 5/5 | 24.4s | Execution match |
| `spider-dev-047` | `network_1` | extra | **🔴 FAIL** | 3/5 | 36.0s | Result mismatch: Column count mismatch: gold=1, agent=2 |
| `spider-dev-048` | `network_1` | extra | **🔴 FAIL** | 3/5 | 26.6s | Result mismatch: Column count mismatch: gold=1, agent=2 |
| `spider-dev-049` | `network_1` | extra | **🟢 PASS** | 5/5 | 26.4s | Execution match |
| `spider-dev-050` | `network_1` | extra | **🟢 PASS** | 5/5 | 31.9s | Execution match |

## 🔍 Deep Dive Details

### ✅ Case `spider-dev-001` (easy)

- **Question:** What is the total number of singers?
- **DB Name:** `concert_singer`
- **Gold SQL:**
  ```sql
  SELECT count(*) FROM singer
  ```
- **Agent SQL:**
  ```sql
  SELECT COUNT(*) AS total_singers FROM singer LIMIT 100
  ```
- **Agent Answer:** The total number of singers is 6.
- **Steps:** build_schema_context, build_query_plan, generate_sql_candidate, validate_sql, execute_sql, profile_result, suggest_chart, suggest_followups, answer_synthesizer
- **Artifacts:** query_plan, sql, safety, table, insight
- **Result:** Execution match
- **Quality Score:** 5/5 (checks: {"completed": true, "sql_generated": true, "execution_match": true, "has_safety": true, "has_answer": true, "has_query_plan": true, "has_table": true, "has_error": false, "flow_complete": true})

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
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "execute_sql",
    "error": null,
    "artifact_type": "table"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "profile_result",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "profile_result",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "profile_result",
    "error": null,
    "artifact_type": "insight"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "suggest_followups",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "suggest_followups",
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

### ✅ Case `spider-dev-002` (easy)

- **Question:** What are the names, countries, and ages for every singer in descending order of age?
- **DB Name:** `concert_singer`
- **Gold SQL:**
  ```sql
  SELECT name ,  country ,  age FROM singer ORDER BY age DESC
  ```
- **Agent SQL:**
  ```sql
  SELECT Name AS name, Country AS country, Age AS age FROM singer ORDER BY Age DESC LIMIT 100
  ```
- **Agent Answer:** The singers, ordered by age in descending order, are:

- Joe Sharp (Netherlands, age 52)
- John Nizinik (France, age 43)
- Rose White (France, age 41)
- Timbaland (United States, age 32)
- Justin Brown (France, age 29)

Note: The result set contains 6 rows total; one additional singer is present in 
- **Steps:** build_schema_context, build_query_plan, generate_sql_candidate, validate_sql, execute_sql
- **Artifacts:** query_plan, sql, safety, table
- **Result:** Execution match
- **Quality Score:** 5/5 (checks: {"completed": true, "sql_generated": true, "execution_match": true, "has_safety": true, "has_answer": true, "has_query_plan": true, "has_table": true, "has_error": false, "flow_complete": true})

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
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "execute_sql",
    "error": null,
    "artifact_type": "table"
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

### ✅ Case `spider-dev-003` (easy)

- **Question:** What is the average, minimum, and maximum age of all singers from France?
- **DB Name:** `concert_singer`
- **Gold SQL:**
  ```sql
  SELECT avg(age) ,  min(age) ,  max(age) FROM singer WHERE country  =  'France'
  ```
- **Agent SQL:**
  ```sql
  SELECT AVG(Age) AS average_age, MIN(Age) AS minimum_age, MAX(Age) AS maximum_age FROM singer WHERE Country = 'France' LIMIT 100
  ```
- **Agent Answer:** The average age of singers from France is 34.5 years, the minimum age is 25 years, and the maximum age is 43 years.
- **Steps:** build_schema_context, build_query_plan, generate_sql_candidate, validate_sql, execute_sql
- **Artifacts:** query_plan, sql, safety, table
- **Result:** Execution match
- **Quality Score:** 5/5 (checks: {"completed": true, "sql_generated": true, "execution_match": true, "has_safety": true, "has_answer": true, "has_query_plan": true, "has_table": true, "has_error": false, "flow_complete": true})

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
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "execute_sql",
    "error": null,
    "artifact_type": "table"
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

### ✅ Case `spider-dev-004` (easy)

- **Question:** What is the average, minimum, and maximum age for all French singers?
- **DB Name:** `concert_singer`
- **Gold SQL:**
  ```sql
  SELECT avg(age) ,  min(age) ,  max(age) FROM singer WHERE country  =  'France'
  ```
- **Agent SQL:**
  ```sql
  SELECT AVG(Age) AS average_age, MIN(Age) AS minimum_age, MAX(Age) AS maximum_age FROM singer WHERE Country = 'France' LIMIT 100
  ```
- **Agent Answer:** The average age of French singers is 34.5 years, the minimum age is 25 years, and the maximum age is 43 years.
- **Steps:** build_schema_context, build_query_plan, generate_sql_candidate, validate_sql, execute_sql
- **Artifacts:** query_plan, sql, safety, table
- **Result:** Execution match
- **Quality Score:** 5/5 (checks: {"completed": true, "sql_generated": true, "execution_match": true, "has_safety": true, "has_answer": true, "has_query_plan": true, "has_table": true, "has_error": false, "flow_complete": true})

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
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "execute_sql",
    "error": null,
    "artifact_type": "table"
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

### ❌ Case `spider-dev-005` (easy)

- **Question:** Show the name and the release year of the song by the youngest singer.
- **DB Name:** `concert_singer`
- **Gold SQL:**
  ```sql
  SELECT song_name ,  song_release_year FROM singer ORDER BY age LIMIT 1
  ```
- **Agent SQL:**
  ```sql
  SELECT Name AS name, Song_Name AS song_name, Song_release_year AS song_release_year FROM singer ORDER BY Age ASC LIMIT 1
  ```
- **Agent Answer:** The song by the youngest singer is 'Love' by Tribal King, released in 2016.
- **Steps:** build_schema_context, build_query_plan, generate_sql_candidate, validate_sql, execute_sql, profile_result, suggest_chart, suggest_followups, answer_synthesizer
- **Artifacts:** query_plan, sql, safety, table, insight, chart
- **Result:** Result mismatch: Column count mismatch: gold=2, agent=3
- **Quality Score:** 3/5 (checks: {"completed": false, "sql_generated": true, "execution_match": false, "has_safety": true, "has_answer": true, "has_query_plan": true, "has_table": true, "has_error": false, "flow_complete": true})

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
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "execute_sql",
    "error": null,
    "artifact_type": "table"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "profile_result",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "profile_result",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "profile_result",
    "error": null,
    "artifact_type": "insight"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": "chart"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "suggest_followups",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "suggest_followups",
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

### ❌ Case `spider-dev-006` (easy)

- **Question:** What are the names and release years for all the songs of the youngest singer?
- **DB Name:** `concert_singer`
- **Gold SQL:**
  ```sql
  SELECT song_name ,  song_release_year FROM singer ORDER BY age LIMIT 1
  ```
- **Agent SQL:**
  ```sql
  SELECT Name, Song_Name, Song_release_year FROM singer WHERE Age = (SELECT MIN(Age) FROM singer) ORDER BY Name ASC, Song_Name ASC, Song_release_year ASC LIMIT 100
  ```
- **Agent Answer:** The youngest singer is Tribal King, and their song 'Love' was released in 2016.
- **Steps:** build_schema_context, build_query_plan, generate_sql_candidate, validate_sql, execute_sql, profile_result, suggest_chart, suggest_followups, answer_synthesizer
- **Artifacts:** query_plan, sql, safety, table, insight, chart
- **Result:** Result mismatch: Column count mismatch: gold=2, agent=3
- **Quality Score:** 3/5 (checks: {"completed": false, "sql_generated": true, "execution_match": false, "has_safety": true, "has_answer": true, "has_query_plan": true, "has_table": true, "has_error": false, "flow_complete": true})

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
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "execute_sql",
    "error": null,
    "artifact_type": "table"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "profile_result",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "profile_result",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "profile_result",
    "error": null,
    "artifact_type": "insight"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": "chart"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "suggest_followups",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "suggest_followups",
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

### ✅ Case `spider-dev-007` (easy)

- **Question:** What are all distinct countries where singers above age 20 are from?
- **DB Name:** `concert_singer`
- **Gold SQL:**
  ```sql
  SELECT DISTINCT country FROM singer WHERE age  >  20
  ```
- **Agent SQL:**
  ```sql
  SELECT DISTINCT Country AS country FROM singer WHERE Age > 20 LIMIT 100
  ```
- **Agent Answer:** The distinct countries where singers above age 20 are from are: Netherlands, United States, and France.
- **Steps:** build_schema_context, build_query_plan, generate_sql_candidate, validate_sql, execute_sql, profile_result, suggest_chart, suggest_followups, answer_synthesizer
- **Artifacts:** query_plan, sql, safety, table, insight
- **Result:** Execution match
- **Quality Score:** 5/5 (checks: {"completed": true, "sql_generated": true, "execution_match": true, "has_safety": true, "has_answer": true, "has_query_plan": true, "has_table": true, "has_error": false, "flow_complete": true})

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
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "execute_sql",
    "error": null,
    "artifact_type": "table"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "profile_result",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "profile_result",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "profile_result",
    "error": null,
    "artifact_type": "insight"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "suggest_followups",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "suggest_followups",
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

### ✅ Case `spider-dev-008` (easy)

- **Question:** What are  the different countries with singers above age 20?
- **DB Name:** `concert_singer`
- **Gold SQL:**
  ```sql
  SELECT DISTINCT country FROM singer WHERE age  >  20
  ```
- **Agent SQL:**
  ```sql
  SELECT DISTINCT Country AS country FROM singer WHERE Age > 20 LIMIT 100
  ```
- **Agent Answer:** The different countries with singers above age 20 are: Netherlands, United States, and France.
- **Steps:** build_schema_context, build_query_plan, generate_sql_candidate, validate_sql, execute_sql, profile_result, suggest_chart, suggest_followups, answer_synthesizer
- **Artifacts:** query_plan, sql, safety, table, insight
- **Result:** Execution match
- **Quality Score:** 5/5 (checks: {"completed": true, "sql_generated": true, "execution_match": true, "has_safety": true, "has_answer": true, "has_query_plan": true, "has_table": true, "has_error": false, "flow_complete": true})

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
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "execute_sql",
    "error": null,
    "artifact_type": "table"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "profile_result",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "profile_result",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "profile_result",
    "error": null,
    "artifact_type": "insight"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "suggest_followups",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "suggest_followups",
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

### ✅ Case `spider-dev-009` (easy)

- **Question:** What are all the song names by singers who are older than average?
- **DB Name:** `concert_singer`
- **Gold SQL:**
  ```sql
  SELECT song_name FROM singer WHERE age  >  (SELECT avg(age) FROM singer)
  ```
- **Agent SQL:**
  ```sql
  SELECT Song_Name FROM singer WHERE Age > (SELECT AVG(Age) FROM singer) LIMIT 100
  ```
- **Agent Answer:** The song names by singers who are older than average are: You, Sun, and Gentleman.
- **Steps:** build_schema_context, build_query_plan, generate_sql_candidate, validate_sql, execute_sql, profile_result, suggest_chart, suggest_followups, answer_synthesizer
- **Artifacts:** query_plan, sql, safety, table, insight
- **Result:** Execution match
- **Quality Score:** 5/5 (checks: {"completed": true, "sql_generated": true, "execution_match": true, "has_safety": true, "has_answer": true, "has_query_plan": true, "has_table": true, "has_error": false, "flow_complete": true})

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
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "execute_sql",
    "error": null,
    "artifact_type": "table"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "profile_result",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "profile_result",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "profile_result",
    "error": null,
    "artifact_type": "insight"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "suggest_followups",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "suggest_followups",
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

### ✅ Case `spider-dev-010` (easy)

- **Question:** Show location and name for all stadiums with a capacity between 5000 and 10000.
- **DB Name:** `concert_singer`
- **Gold SQL:**
  ```sql
  SELECT LOCATION ,  name FROM stadium WHERE capacity BETWEEN 5000 AND 10000
  ```
- **Agent SQL:**
  ```sql
  SELECT Location, Name FROM stadium WHERE Capacity BETWEEN 5000 AND 10000 LIMIT 100
  ```
- **Agent Answer:** The query executed successfully and returned 0 rows. There are no stadiums in the database with a capacity between 5000 and 10000.
- **Steps:** build_schema_context, build_query_plan, generate_sql_candidate, validate_sql, execute_sql
- **Artifacts:** query_plan, sql, safety, table
- **Result:** Execution match
- **Quality Score:** 5/5 (checks: {"completed": true, "sql_generated": true, "execution_match": true, "has_safety": true, "has_answer": true, "has_query_plan": true, "has_table": true, "has_error": false, "flow_complete": true})

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
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "execute_sql",
    "error": null,
    "artifact_type": "table"
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

### ✅ Case `spider-dev-011` (medium)

- **Question:** List the maximum weight and type for each type of pet.
- **DB Name:** `pets_1`
- **Gold SQL:**
  ```sql
  SELECT max(weight) ,  petType FROM pets GROUP BY petType
  ```
- **Agent SQL:**
  ```sql
  SELECT PetType AS pet_type, MAX(weight) AS max_weight FROM pets GROUP BY PetType LIMIT 100
  ```
- **Agent Answer:** The maximum weight for each pet type is:
- Cat: 12.0
- Dog: 13.4
- **Steps:** build_schema_context, build_query_plan, generate_sql_candidate, validate_sql, execute_sql
- **Artifacts:** query_plan, sql, safety, table
- **Result:** Execution match
- **Quality Score:** 5/5 (checks: {"completed": true, "sql_generated": true, "execution_match": true, "has_safety": true, "has_answer": true, "has_query_plan": true, "has_table": true, "has_error": false, "flow_complete": true})

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
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "execute_sql",
    "error": null,
    "artifact_type": "table"
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

### ✅ Case `spider-dev-012` (medium)

- **Question:** How many pets are owned by students that have an age greater than 20?
- **DB Name:** `pets_1`
- **Gold SQL:**
  ```sql
  SELECT count(*) FROM student AS T1 JOIN has_pet AS T2 ON T1.stuid  =  T2.stuid WHERE T1.age  >  20
  ```
- **Agent SQL:**
  ```sql
  SELECT COUNT(*) AS pet_count FROM has_pet JOIN student ON has_pet.StuID = student.StuID WHERE student.Age > 20 LIMIT 100
  ```
- **Agent Answer:** There are 0 pets owned by students who are older than 20 years.
- **Steps:** build_schema_context, build_query_plan, generate_sql_candidate, validate_sql, execute_sql, profile_result, suggest_chart, suggest_followups, answer_synthesizer
- **Artifacts:** query_plan, sql, safety, table, insight
- **Result:** Execution match
- **Quality Score:** 5/5 (checks: {"completed": true, "sql_generated": true, "execution_match": true, "has_safety": true, "has_answer": true, "has_query_plan": true, "has_table": true, "has_error": false, "flow_complete": true})

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
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "execute_sql",
    "error": null,
    "artifact_type": "table"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "profile_result",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "profile_result",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "profile_result",
    "error": null,
    "artifact_type": "insight"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "suggest_followups",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "suggest_followups",
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

### ❌ Case `spider-dev-013` (medium)

- **Question:** Find the average and maximum age for each type of pet.
- **DB Name:** `pets_1`
- **Gold SQL:**
  ```sql
  SELECT avg(pet_age) ,  max(pet_age) ,  pettype FROM pets GROUP BY pettype
  ```
- **Agent SQL:**
  ```sql
  SELECT PetType AS pet_type, AVG(pet_age) AS average_age, MAX(pet_age) AS maximum_age FROM pets GROUP BY PetType LIMIT 100
  ```
- **Agent Answer:** The average and maximum age for each type of pet are:

- Cat: average age 3.0, maximum age 3
- Dog: average age 1.5, maximum age 2
- **Steps:** build_schema_context, build_query_plan, generate_sql_candidate, validate_sql, execute_sql, profile_result, suggest_chart, suggest_followups, answer_synthesizer
- **Artifacts:** query_plan, sql, safety, table, insight, chart
- **Result:** Result mismatch: Row mismatch: gold=['1.5000', 2, 'dog'], agent=['cat', '3.0000', 3]
- **Quality Score:** 3/5 (checks: {"completed": false, "sql_generated": true, "execution_match": false, "has_safety": true, "has_answer": true, "has_query_plan": true, "has_table": true, "has_error": false, "flow_complete": true})

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
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "execute_sql",
    "error": null,
    "artifact_type": "table"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "profile_result",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "profile_result",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "profile_result",
    "error": null,
    "artifact_type": "insight"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": "chart"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "suggest_followups",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "suggest_followups",
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

### ❌ Case `spider-dev-014` (medium)

- **Question:** What is the average and maximum age for each pet type?
- **DB Name:** `pets_1`
- **Gold SQL:**
  ```sql
  SELECT avg(pet_age) ,  max(pet_age) ,  pettype FROM pets GROUP BY pettype
  ```
- **Agent SQL:**
  ```sql
  SELECT PetType AS pet_type, AVG(pet_age) AS average_age, MAX(pet_age) AS maximum_age FROM pets GROUP BY PetType LIMIT 100
  ```
- **Agent Answer:** The average and maximum age for each pet type are as follows:

- **Cat**: Average age = 3.0, Maximum age = 3
- **Dog**: Average age = 1.5, Maximum age = 2
- **Steps:** build_schema_context, build_query_plan, generate_sql_candidate, validate_sql, execute_sql
- **Artifacts:** query_plan, sql, safety, table
- **Result:** Result mismatch: Row mismatch: gold=['1.5000', 2, 'dog'], agent=['cat', '3.0000', 3]
- **Quality Score:** 3/5 (checks: {"completed": false, "sql_generated": true, "execution_match": false, "has_safety": true, "has_answer": true, "has_query_plan": true, "has_table": true, "has_error": false, "flow_complete": true})

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
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "execute_sql",
    "error": null,
    "artifact_type": "table"
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

### ❌ Case `spider-dev-015` (medium)

- **Question:** Find the average weight for each pet type.
- **DB Name:** `pets_1`
- **Gold SQL:**
  ```sql
  SELECT avg(weight) ,  pettype FROM pets GROUP BY pettype
  ```
- **Agent SQL:**
  ```sql
  SELECT PetType AS pet_type, AVG(weight) AS average_weight FROM pets GROUP BY PetType LIMIT 100
  ```
- **Agent Answer:** The average weight for each pet type is:

- Cat: 12.0
- Dog: 11.35
- **Steps:** build_schema_context, build_query_plan, generate_sql_candidate, validate_sql, execute_sql
- **Artifacts:** query_plan, sql, safety, table
- **Result:** Result mismatch: Row mismatch: gold=[11.35, 'dog'], agent=['cat', 12.0]
- **Quality Score:** 3/5 (checks: {"completed": false, "sql_generated": true, "execution_match": false, "has_safety": true, "has_answer": true, "has_query_plan": true, "has_table": true, "has_error": false, "flow_complete": true})

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
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "execute_sql",
    "error": null,
    "artifact_type": "table"
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

### ❌ Case `spider-dev-016` (medium)

- **Question:** What is the average weight for each type of pet?
- **DB Name:** `pets_1`
- **Gold SQL:**
  ```sql
  SELECT avg(weight) ,  pettype FROM pets GROUP BY pettype
  ```
- **Agent SQL:**
  ```sql
  SELECT PetType AS pet_type, AVG(weight) AS average_weight FROM pets GROUP BY PetType LIMIT 100
  ```
- **Agent Answer:** The average weight for each type of pet is:

- Cat: 12.0
- Dog: 11.35

This result is based on the executed query that grouped pets by type and computed the average weight for each group.
- **Steps:** build_schema_context, build_query_plan, generate_sql_candidate, validate_sql, execute_sql, profile_result, suggest_chart, suggest_followups, answer_synthesizer
- **Artifacts:** query_plan, sql, safety, table, insight, chart
- **Result:** Result mismatch: Row mismatch: gold=[11.35, 'dog'], agent=['cat', 12.0]
- **Quality Score:** 3/5 (checks: {"completed": false, "sql_generated": true, "execution_match": false, "has_safety": true, "has_answer": true, "has_query_plan": true, "has_table": true, "has_error": false, "flow_complete": true})

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
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "execute_sql",
    "error": null,
    "artifact_type": "table"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "profile_result",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "profile_result",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "profile_result",
    "error": null,
    "artifact_type": "insight"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": "chart"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "suggest_followups",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "suggest_followups",
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

### ❌ Case `spider-dev-017` (medium)

- **Question:** Find the first name and age of students who have a pet.
- **DB Name:** `pets_1`
- **Gold SQL:**
  ```sql
  SELECT DISTINCT T1.fname ,  T1.age FROM student AS T1 JOIN has_pet AS T2 ON T1.stuid  =  T2.stuid
  ```
- **Agent SQL:**
  ```sql
  SELECT student.Fname AS name, student.Fname AS student_fname, student.Age AS student_age FROM student JOIN has_pet ON student.StuID = has_pet.StuID LIMIT 100
  ```
- **Agent Answer:** The query returned 3 rows of students who have a pet:

- Linda, age 18
- Tracy, age 19
- Tracy, age 19

Tracy appears twice, making her the most frequent name in this result set. Ages range from 18 to 19.
- **Steps:** build_schema_context, build_query_plan, generate_sql_candidate, validate_sql, execute_sql, profile_result, suggest_chart, suggest_followups, answer_synthesizer
- **Artifacts:** query_plan, sql, safety, table, insight, chart
- **Result:** Result mismatch: Row count mismatch: gold=2, agent=3
- **Quality Score:** 3/5 (checks: {"completed": false, "sql_generated": true, "execution_match": false, "has_safety": true, "has_answer": true, "has_query_plan": true, "has_table": true, "has_error": false, "flow_complete": true})

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
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "execute_sql",
    "error": null,
    "artifact_type": "table"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "profile_result",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "profile_result",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "profile_result",
    "error": null,
    "artifact_type": "insight"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": "chart"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "suggest_followups",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "suggest_followups",
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

### ❌ Case `spider-dev-018` (medium)

- **Question:** What are the different first names and ages of the students who do have pets?
- **DB Name:** `pets_1`
- **Gold SQL:**
  ```sql
  SELECT DISTINCT T1.fname ,  T1.age FROM student AS T1 JOIN has_pet AS T2 ON T1.stuid  =  T2.stuid
  ```
- **Agent SQL:**
  ```sql
  SELECT DISTINCT student.Fname AS name, student.Fname AS student_fname, student.Age AS student_age FROM student JOIN has_pet ON student.StuID = has_pet.StuID LIMIT 100
  ```
- **Agent Answer:** The students who have pets have the following distinct first names and ages:

- Linda, age 18
- Tracy, age 19
- **Steps:** build_schema_context, build_query_plan, generate_sql_candidate, validate_sql, execute_sql, profile_result, suggest_chart, suggest_followups, answer_synthesizer
- **Artifacts:** query_plan, sql, safety, table, insight, chart
- **Result:** Result mismatch: Column count mismatch: gold=2, agent=3
- **Quality Score:** 3/5 (checks: {"completed": false, "sql_generated": true, "execution_match": false, "has_safety": true, "has_answer": true, "has_query_plan": true, "has_table": true, "has_error": false, "flow_complete": true})

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
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "execute_sql",
    "error": null,
    "artifact_type": "table"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "profile_result",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "profile_result",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "profile_result",
    "error": null,
    "artifact_type": "insight"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": "chart"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "suggest_followups",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "suggest_followups",
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

### ❌ Case `spider-dev-019` (medium)

- **Question:** Find the id of the pet owned by student whose last name is ‘Smith’.
- **DB Name:** `pets_1`
- **Gold SQL:**
  ```sql
  SELECT T2.petid FROM student AS T1 JOIN has_pet AS T2 ON T1.stuid  =  T2.stuid WHERE T1.Lname  =  'Smith'
  ```
- **Agent SQL:**
  ```sql
  SELECT has_pet.PetID AS id, pets.PetType AS name FROM student JOIN has_pet ON student.StuID = has_pet.StuID JOIN pets ON has_pet.PetID = pets.PetID WHERE student.LName = 'Smith' LIMIT 100
  ```
- **Agent Answer:** The pet owned by the student whose last name is 'Smith' has ID 2001.
- **Steps:** build_schema_context, build_query_plan, generate_sql_candidate, validate_sql, execute_sql
- **Artifacts:** query_plan, sql, safety, table
- **Result:** Result mismatch: Column count mismatch: gold=1, agent=2
- **Quality Score:** 3/5 (checks: {"completed": false, "sql_generated": true, "execution_match": false, "has_safety": true, "has_answer": true, "has_query_plan": true, "has_table": true, "has_error": false, "flow_complete": true})

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
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "execute_sql",
    "error": null,
    "artifact_type": "table"
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

### ❌ Case `spider-dev-020` (medium)

- **Question:** What is the id of the pet owned by the student whose last name is 'Smith'?
- **DB Name:** `pets_1`
- **Gold SQL:**
  ```sql
  SELECT T2.petid FROM student AS T1 JOIN has_pet AS T2 ON T1.stuid  =  T2.stuid WHERE T1.Lname  =  'Smith'
  ```
- **Agent SQL:**
  ```sql
  SELECT has_pet.PetID AS id, pets.PetType AS name FROM student JOIN has_pet ON student.StuID = has_pet.StuID JOIN pets ON has_pet.PetID = pets.PetID WHERE student.LName = 'Smith' LIMIT 100
  ```
- **Agent Answer:** The pet owned by the student whose last name is 'Smith' has ID 2001.
- **Steps:** build_schema_context, build_query_plan, generate_sql_candidate, validate_sql, execute_sql, profile_result, suggest_chart, suggest_followups, answer_synthesizer
- **Artifacts:** query_plan, sql, safety, table, insight, chart
- **Result:** Result mismatch: Column count mismatch: gold=1, agent=2
- **Quality Score:** 3/5 (checks: {"completed": false, "sql_generated": true, "execution_match": false, "has_safety": true, "has_answer": true, "has_query_plan": true, "has_table": true, "has_error": false, "flow_complete": true})

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
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "execute_sql",
    "error": null,
    "artifact_type": "table"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "profile_result",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "profile_result",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "profile_result",
    "error": null,
    "artifact_type": "insight"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": "chart"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "suggest_followups",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "suggest_followups",
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

### ✅ Case `spider-dev-021` (medium)

- **Question:** Find the number of pets for each student who has any pet and student id.
- **DB Name:** `pets_1`
- **Gold SQL:**
  ```sql
  SELECT count(*) ,  T1.stuid FROM student AS T1 JOIN has_pet AS T2 ON T1.stuid  =  T2.stuid GROUP BY T1.stuid
  ```
- **Agent SQL:**
  ```sql
  SELECT COUNT(*) AS id, has_pet.StuID AS student_stuid FROM has_pet GROUP BY has_pet.StuID LIMIT 100
  ```
- **Agent Answer:** The query returned 2 rows: student ID 1001 has 1 pet, and student ID 1002 has 2 pets. This answers the question 'Find the number of pets for each student who has any pet and student id.'
- **Steps:** build_schema_context, build_query_plan, generate_sql_candidate, validate_sql, execute_sql, profile_result, suggest_chart, suggest_followups, answer_synthesizer
- **Artifacts:** query_plan, sql, safety, table, insight
- **Result:** Execution match
- **Quality Score:** 5/5 (checks: {"completed": true, "sql_generated": true, "execution_match": true, "has_safety": true, "has_answer": true, "has_query_plan": true, "has_table": true, "has_error": false, "flow_complete": true})

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
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "execute_sql",
    "error": null,
    "artifact_type": "table"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "profile_result",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "profile_result",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "profile_result",
    "error": null,
    "artifact_type": "insight"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "suggest_followups",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "suggest_followups",
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

### ❌ Case `spider-dev-022` (medium)

- **Question:** For students who have pets , how many pets does each student have ? list their ids instead of names .
- **DB Name:** `pets_1`
- **Gold SQL:**
  ```sql
  select count(*) ,  t1.stuid from student as t1 join has_pet as t2 on t1.stuid  =  t2.stuid group by t1.stuid
  ```
- **Agent SQL:**
  ```sql
  SELECT student.StuID AS id, CONCAT(student.Fname, ' ', student.LName) AS name, student.StuID AS student_stuid, COUNT(*) AS pet_count FROM student JOIN has_pet ON student.StuID = has_pet.StuID GROUP BY student.StuID LIMIT 100
  ```
- **Agent Answer:** For students who have pets, the query returned two students:

- Student ID 1001 has 1 pet.
- Student ID 1002 has 2 pets.

These results are based on executed SQL and reflect only students with at least one pet.
- **Steps:** build_schema_context, build_query_plan, generate_sql_candidate, validate_sql, execute_sql, profile_result, suggest_chart, suggest_followups, answer_synthesizer
- **Artifacts:** query_plan, sql, safety, table, insight, chart
- **Result:** Result mismatch: Column count mismatch: gold=2, agent=4
- **Quality Score:** 3/5 (checks: {"completed": false, "sql_generated": true, "execution_match": false, "has_safety": true, "has_answer": true, "has_query_plan": true, "has_table": true, "has_error": false, "flow_complete": true})

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
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "execute_sql",
    "error": null,
    "artifact_type": "table"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "profile_result",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "profile_result",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "profile_result",
    "error": null,
    "artifact_type": "insight"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": "chart"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "suggest_followups",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "suggest_followups",
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

### ✅ Case `spider-dev-023` (medium)

- **Question:** How many countries does each continent have? List the continent id, continent name and the number of countries.
- **DB Name:** `car_1`
- **Gold SQL:**
  ```sql
  SELECT T1.ContId ,  T1.Continent ,  count(*) FROM CONTINENTS AS T1 JOIN COUNTRIES AS T2 ON T1.ContId  =  T2.Continent GROUP BY T1.ContId;
  ```
- **Agent SQL:**
  ```sql
  SELECT continents.ContId AS id, continents.Continent AS name, continents.ContId AS continents_contid, continents.Continent AS continents_continent, COUNT(*) AS country_count FROM continents JOIN countries ON continents.ContId = countries.Continent GROUP BY continents.ContId, continents.Continent LIMIT 100
  ```
- **Agent Answer:** The query executed successfully but returned no rows. This means that, based on the current schema and join condition (`continents.ContId = countries.Continent`), there are no matching records between the `continents` and `countries` tables — possibly due to mismatched column names, data type incons
- **Steps:** build_schema_context, build_query_plan, generate_sql_candidate, validate_sql, execute_sql, profile_result, suggest_chart, suggest_followups, answer_synthesizer
- **Artifacts:** query_plan, sql, safety, table, insight
- **Result:** Execution match
- **Quality Score:** 5/5 (checks: {"completed": true, "sql_generated": true, "execution_match": true, "has_safety": true, "has_answer": true, "has_query_plan": true, "has_table": true, "has_error": false, "flow_complete": true})

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
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "execute_sql",
    "error": null,
    "artifact_type": "table"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "profile_result",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "profile_result",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "profile_result",
    "error": null,
    "artifact_type": "insight"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "suggest_followups",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "suggest_followups",
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

### ✅ Case `spider-dev-024` (medium)

- **Question:** For each continent, list its id, name, and how many countries it has?
- **DB Name:** `car_1`
- **Gold SQL:**
  ```sql
  SELECT T1.ContId ,  T1.Continent ,  count(*) FROM CONTINENTS AS T1 JOIN COUNTRIES AS T2 ON T1.ContId  =  T2.Continent GROUP BY T1.ContId;
  ```
- **Agent SQL:**
  ```sql
  SELECT continents.ContId AS id, continents.Continent AS name, continents.ContId AS continents_contid, continents.Continent AS continents_continent, COUNT(countries.CountryId) AS count FROM continents LEFT JOIN countries ON continents.ContId = countries.Continent GROUP BY continents.ContId, continents.Continent LIMIT 100
  ```
- **Agent Answer:** The query executed successfully but returned no rows. This means that, for the given schema and join condition (continents.ContId = countries.Continent), there were no matching records — either because the continent IDs in the `countries` table do not align with those in the `continents` table, or b
- **Steps:** build_schema_context, build_query_plan, generate_sql_candidate, validate_sql, execute_sql, profile_result, suggest_chart, suggest_followups, answer_synthesizer
- **Artifacts:** query_plan, sql, safety, table, insight
- **Result:** Execution match
- **Quality Score:** 5/5 (checks: {"completed": true, "sql_generated": true, "execution_match": true, "has_safety": true, "has_answer": true, "has_query_plan": true, "has_table": true, "has_error": false, "flow_complete": true})

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
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "execute_sql",
    "error": null,
    "artifact_type": "table"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "profile_result",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "profile_result",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "profile_result",
    "error": null,
    "artifact_type": "insight"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "suggest_followups",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "suggest_followups",
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

### ✅ Case `spider-dev-025` (medium)

- **Question:** How many models does each car maker produce? List maker full name, id and the number.
- **DB Name:** `car_1`
- **Gold SQL:**
  ```sql
  SELECT T1.FullName ,  T1.Id ,  count(*) FROM CAR_MAKERS AS T1 JOIN MODEL_LIST AS T2 ON T1.Id  =  T2.Maker GROUP BY T1.Id;
  ```
- **Agent SQL:**
  ```sql
  SELECT car_makers.Id AS id, car_makers.Maker AS name, car_makers.FullName AS car_makers_fullname, car_makers.Id AS car_makers_id, COUNT(*) AS model_count FROM car_makers JOIN model_list ON car_makers.Id = model_list.Maker GROUP BY car_makers.Id, car_makers.Maker, car_makers.FullName LIMIT 100
  ```
- **Agent Answer:** The query executed successfully but returned no rows. This means there are no models associated with car makers in the current dataset under the join condition `car_makers.Id = model_list.Maker`. Possible causes include missing or mismatched IDs between the `car_makers` and `model_list` tables, or a
- **Steps:** build_schema_context, build_query_plan, generate_sql_candidate, validate_sql, execute_sql, profile_result, suggest_chart, suggest_followups
- **Artifacts:** query_plan, sql, safety, table, insight
- **Result:** Execution match
- **Quality Score:** 5/5 (checks: {"completed": true, "sql_generated": true, "execution_match": true, "has_safety": true, "has_answer": true, "has_query_plan": true, "has_table": true, "has_error": false, "flow_complete": true})

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
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "execute_sql",
    "error": null,
    "artifact_type": "table"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "profile_result",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "profile_result",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "profile_result",
    "error": null,
    "artifact_type": "insight"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "suggest_followups",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "suggest_followups",
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

### ✅ Case `spider-dev-026` (hard)

- **Question:** How many flights depart from City 'Aberdeen' and have destination City 'Ashley'?
- **DB Name:** `flight_2`
- **Gold SQL:**
  ```sql
  SELECT count(*) FROM FLIGHTS AS T1 JOIN AIRPORTS AS T2 ON T1.DestAirport  =  T2.AirportCode JOIN AIRPORTS AS T3 ON T1.SourceAirport  =  T3.AirportCode WHERE T2.City  =  "Ashley" AND T3.City  =  "Aberdeen"
  ```
- **Agent SQL:**
  ```sql
  SELECT COUNT(*) FROM flights AS f JOIN airports AS src ON f.SourceAirport = src.AirportCode JOIN airports AS dst ON f.DestAirport = dst.AirportCode WHERE src.City = 'Aberdeen' AND dst.City = 'Ashley' LIMIT 1000
  ```
- **Agent Answer:** There are 0 flights that depart from City 'Aberdeen' and have destination City 'Ashley'.
- **Steps:** build_schema_context, build_query_plan, generate_sql_candidate, validate_sql, execute_sql, profile_result, suggest_chart
- **Artifacts:** query_plan, sql, safety, table, insight
- **Result:** Execution match
- **Quality Score:** 5/5 (checks: {"completed": true, "sql_generated": true, "execution_match": true, "has_safety": true, "has_answer": true, "has_query_plan": true, "has_table": true, "has_error": false, "flow_complete": true})

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
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "execute_sql",
    "error": null,
    "artifact_type": "table"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "profile_result",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "profile_result",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "profile_result",
    "error": null,
    "artifact_type": "insight"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "suggest_chart",
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

### ✅ Case `spider-dev-027` (hard)

- **Question:** How many flights fly from Aberdeen to Ashley?
- **DB Name:** `flight_2`
- **Gold SQL:**
  ```sql
  SELECT count(*) FROM FLIGHTS AS T1 JOIN AIRPORTS AS T2 ON T1.DestAirport  =  T2.AirportCode JOIN AIRPORTS AS T3 ON T1.SourceAirport  =  T3.AirportCode WHERE T2.City  =  "Ashley" AND T3.City  =  "Aberdeen"
  ```
- **Agent SQL:**
  ```sql
  SELECT COUNT(*) AS flight_count FROM flights JOIN airports ON flights.SourceAirport = airports.AirportCode WHERE airports.City = 'Aberdeen' AND airports.City = 'Ashley' LIMIT 100
  ```
- **Agent Answer:** There are 0 flights that fly from Aberdeen to Ashley.
- **Steps:** build_schema_context, build_query_plan, generate_sql_candidate, validate_sql, execute_sql
- **Artifacts:** query_plan, sql, safety, table
- **Result:** Execution match
- **Quality Score:** 5/5 (checks: {"completed": true, "sql_generated": true, "execution_match": true, "has_safety": true, "has_answer": true, "has_query_plan": true, "has_table": true, "has_error": false, "flow_complete": true})

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
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "execute_sql",
    "error": null,
    "artifact_type": "table"
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

### ✅ Case `spider-dev-028` (hard)

- **Question:** How many United Airlines flights go to City 'Aberdeen'?
- **DB Name:** `flight_2`
- **Gold SQL:**
  ```sql
  SELECT count(*) FROM FLIGHTS AS T1 JOIN AIRPORTS AS T2 ON T1.DestAirport  =  T2.AirportCode JOIN AIRLINES AS T3 ON T3.uid  =  T1.Airline WHERE T2.City  =  "Aberdeen" AND T3.Airline  =  "United Airlines"
  ```
- **Agent SQL:**
  ```sql
  SELECT COUNT(*) AS airline FROM flights JOIN airlines ON flights.Airline = airlines.uid JOIN airports ON flights.DestAirport = airports.AirportCode WHERE airlines.Airline = 'United Airlines' AND airports.City = 'Aberdeen' LIMIT 100
  ```
- **Agent Answer:** There are 0 United Airlines flights that go to Aberdeen.
- **Steps:** build_schema_context, build_query_plan, generate_sql_candidate, validate_sql, execute_sql
- **Artifacts:** query_plan, sql, safety, table
- **Result:** Execution match
- **Quality Score:** 5/5 (checks: {"completed": true, "sql_generated": true, "execution_match": true, "has_safety": true, "has_answer": true, "has_query_plan": true, "has_table": true, "has_error": false, "flow_complete": true})

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
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "execute_sql",
    "error": null,
    "artifact_type": "table"
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

### ❌ Case `spider-dev-029` (hard)

- **Question:** Count the number of United Airlines flights that arrive in Aberdeen.
- **DB Name:** `flight_2`
- **Gold SQL:**
  ```sql
  SELECT count(*) FROM FLIGHTS AS T1 JOIN AIRPORTS AS T2 ON T1.DestAirport  =  T2.AirportCode JOIN AIRLINES AS T3 ON T3.uid  =  T1.Airline WHERE T2.City  =  "Aberdeen" AND T3.Airline  =  "United Airlines"
  ```
- **Agent SQL:**
  ```sql
  SELECT COUNT(*) AS count, 'United Airlines' AS airline FROM flights JOIN airlines ON flights.Airline = airlines.uid JOIN airports ON flights.DestAirport = airports.AirportCode WHERE airlines.Airline = 'United Airlines' AND airports.City = 'Aberdeen' LIMIT 100
  ```
- **Agent Answer:** There are 0 United Airlines flights that arrive in Aberdeen.
- **Steps:** build_schema_context, build_query_plan, generate_sql_candidate, validate_sql, execute_sql, profile_result, suggest_chart, suggest_followups, answer_synthesizer
- **Artifacts:** query_plan, sql, safety, table, insight, chart
- **Result:** Result mismatch: Column count mismatch: gold=1, agent=2
- **Quality Score:** 3/5 (checks: {"completed": false, "sql_generated": true, "execution_match": false, "has_safety": true, "has_answer": true, "has_query_plan": true, "has_table": true, "has_error": false, "flow_complete": true})

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
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "execute_sql",
    "error": null,
    "artifact_type": "table"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "profile_result",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "profile_result",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "profile_result",
    "error": null,
    "artifact_type": "insight"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": "chart"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "suggest_followups",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "suggest_followups",
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

### ❌ Case `spider-dev-030` (hard)

- **Question:** Find all airlines that have at least 10 flights.
- **DB Name:** `flight_2`
- **Gold SQL:**
  ```sql
  SELECT T1.Airline FROM AIRLINES AS T1 JOIN FLIGHTS AS T2 ON T1.uid  =  T2.Airline GROUP BY T1.Airline HAVING count(*)  >  10
  ```
- **Agent SQL:**
  ```sql
  SELECT a.Airline AS airline, a.Airline AS airlines_airline FROM airlines AS a JOIN flights AS f ON a.uid = f.Airline GROUP BY a.Airline HAVING COUNT(*) >= 10 LIMIT 1000
  ```
- **Agent Answer:** The airlines that have at least 10 flights are: United Airlines, US Airways, Delta Airlines, Southwest Airlines, and American Airlines. The query returned 12 rows in total.
- **Steps:** build_schema_context, build_query_plan, generate_sql_candidate, validate_sql, execute_sql
- **Artifacts:** query_plan, sql, safety, table
- **Result:** Result mismatch: Column count mismatch: gold=1, agent=2
- **Quality Score:** 3/5 (checks: {"completed": false, "sql_generated": true, "execution_match": false, "has_safety": true, "has_answer": true, "has_query_plan": true, "has_table": true, "has_error": false, "flow_complete": true})

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
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "execute_sql",
    "error": null,
    "artifact_type": "table"
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

### ❌ Case `spider-dev-031` (hard)

- **Question:** Which airlines have at least 10 flights?
- **DB Name:** `flight_2`
- **Gold SQL:**
  ```sql
  SELECT T1.Airline FROM AIRLINES AS T1 JOIN FLIGHTS AS T2 ON T1.uid  =  T2.Airline GROUP BY T1.Airline HAVING count(*)  >  10
  ```
- **Agent SQL:**
  ```sql
  SELECT a.Airline AS airline, a.Airline AS airlines_airline FROM airlines AS a JOIN flights AS f ON a.uid = f.Airline GROUP BY a.Airline HAVING COUNT(*) >= 10 LIMIT 1000
  ```
- **Agent Answer:** The airlines that have at least 10 flights are: United Airlines, US Airways, Delta Airlines, Southwest Airlines, and American Airlines — along with 7 other airlines (total of 12 airlines). The result set contains 12 rows, each representing one such airline.
- **Steps:** build_schema_context, build_query_plan, generate_sql_candidate, validate_sql, execute_sql, profile_result, suggest_chart, suggest_followups, answer_synthesizer
- **Artifacts:** query_plan, sql, safety, table, insight
- **Result:** Result mismatch: Column count mismatch: gold=1, agent=2
- **Quality Score:** 3/5 (checks: {"completed": false, "sql_generated": true, "execution_match": false, "has_safety": true, "has_answer": true, "has_query_plan": true, "has_table": true, "has_error": false, "flow_complete": true})

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
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "execute_sql",
    "error": null,
    "artifact_type": "table"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "profile_result",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "profile_result",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "profile_result",
    "error": null,
    "artifact_type": "insight"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "suggest_followups",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "suggest_followups",
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

### ❌ Case `spider-dev-032` (hard)

- **Question:** Find all airlines that have fewer than 200 flights.
- **DB Name:** `flight_2`
- **Gold SQL:**
  ```sql
  SELECT T1.Airline FROM AIRLINES AS T1 JOIN FLIGHTS AS T2 ON T1.uid  =  T2.Airline GROUP BY T1.Airline HAVING count(*)  <  200
  ```
- **Agent SQL:**
  ```sql
  SELECT a.Airline AS airline, a.Airline AS airlines_airline, COUNT(*) AS flight_count FROM airlines AS a JOIN flights AS f ON a.uid = f.Airline GROUP BY a.Airline HAVING COUNT(*) < 200 LIMIT 1000
  ```
- **Agent Answer:** The query successfully identified 12 airlines that have fewer than 200 flights. Sample results include United Airlines, US Airways, Delta Airlines, Southwest Airlines, and American Airlines — each with a flight count of 100. The full result set contains 12 rows, all satisfying the condition `COUNT(*
- **Steps:** build_schema_context, build_query_plan, generate_sql_candidate, validate_sql, execute_sql, profile_result, suggest_chart, suggest_followups, answer_synthesizer
- **Artifacts:** query_plan, sql, safety, table, insight, chart
- **Result:** Result mismatch: Column count mismatch: gold=1, agent=3
- **Quality Score:** 3/5 (checks: {"completed": false, "sql_generated": true, "execution_match": false, "has_safety": true, "has_answer": true, "has_query_plan": true, "has_table": true, "has_error": false, "flow_complete": true})

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
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "execute_sql",
    "error": null,
    "artifact_type": "table"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "profile_result",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "profile_result",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "profile_result",
    "error": null,
    "artifact_type": "insight"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": "chart"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "suggest_followups",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "suggest_followups",
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

### ❌ Case `spider-dev-033` (hard)

- **Question:** Which airlines have less than 200 flights?
- **DB Name:** `flight_2`
- **Gold SQL:**
  ```sql
  SELECT T1.Airline FROM AIRLINES AS T1 JOIN FLIGHTS AS T2 ON T1.uid  =  T2.Airline GROUP BY T1.Airline HAVING count(*)  <  200
  ```
- **Agent SQL:**
  ```sql
  SELECT a.Airline AS airline, a.Airline AS airlines_airline FROM airlines AS a JOIN flights AS f ON a.uid = f.Airline GROUP BY a.Airline HAVING COUNT(*) < 200 LIMIT 1000
  ```
- **Agent Answer:** The airlines with less than 200 flights are: United Airlines, US Airways, Delta Airlines, Southwest Airlines, American Airlines, and 7 other airlines — totaling 12 airlines. This result is based on a validated SQL query that joined the airlines and flights tables, grouped by airline, and filtered fo
- **Steps:** build_schema_context, build_query_plan, generate_sql_candidate, validate_sql, execute_sql, profile_result, suggest_chart, suggest_followups, answer_synthesizer
- **Artifacts:** query_plan, sql, safety, table, insight
- **Result:** Result mismatch: Column count mismatch: gold=1, agent=2
- **Quality Score:** 3/5 (checks: {"completed": false, "sql_generated": true, "execution_match": false, "has_safety": true, "has_answer": true, "has_query_plan": true, "has_table": true, "has_error": false, "flow_complete": true})

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
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "execute_sql",
    "error": null,
    "artifact_type": "table"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "profile_result",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "profile_result",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "profile_result",
    "error": null,
    "artifact_type": "insight"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "suggest_followups",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "suggest_followups",
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

### ❌ Case `spider-dev-034` (hard)

- **Question:** Find the name of airports which do not have any flight in and out.
- **DB Name:** `flight_2`
- **Gold SQL:**
  ```sql
  SELECT AirportName FROM Airports WHERE AirportCode NOT IN (SELECT SourceAirport FROM Flights UNION SELECT DestAirport FROM Flights)
  ```
- **Agent SQL:**
  ```sql
  SELECT AirportName AS name, AirportName AS airportname FROM airports WHERE NOT AirportCode IN (SELECT SourceAirport FROM flights UNION SELECT DestAirport FROM flights) LIMIT 100
  ```
- **Agent Answer:** The query identified 100 airports that do not have any flights in or out. The most frequent airport name in the result is 'Municipal ' (appearing 12 times). These airports are those whose AirportCode does not appear in either the SourceAirport or DestAirport columns of the flights table.
- **Steps:** build_schema_context, build_query_plan, generate_sql_candidate, validate_sql, execute_sql, profile_result, suggest_chart, suggest_followups, answer_synthesizer
- **Artifacts:** query_plan, sql, safety, table, insight
- **Result:** Result mismatch: Column count mismatch: gold=1, agent=2
- **Quality Score:** 3/5 (checks: {"completed": false, "sql_generated": true, "execution_match": false, "has_safety": true, "has_answer": true, "has_query_plan": true, "has_table": true, "has_error": false, "flow_complete": true})

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
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "execute_sql",
    "error": null,
    "artifact_type": "table"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "profile_result",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "profile_result",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "profile_result",
    "error": null,
    "artifact_type": "insight"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "suggest_followups",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "suggest_followups",
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

### ❌ Case `spider-dev-035` (hard)

- **Question:** Which airports do not have departing or arriving flights?
- **DB Name:** `flight_2`
- **Gold SQL:**
  ```sql
  SELECT AirportName FROM Airports WHERE AirportCode NOT IN (SELECT SourceAirport FROM Flights UNION SELECT DestAirport FROM Flights)
  ```
- **Agent SQL:**
  ```sql
  SELECT AirportCode FROM airports WHERE NOT AirportCode IN (SELECT SourceAirport FROM flights WHERE NOT SourceAirport IS NULL UNION SELECT DestAirport FROM flights WHERE NOT DestAirport IS NULL) LIMIT 1000
  ```
- **Agent Answer:** The query identified 100 airports that do not have departing or arriving flights. These airports are not present in either the SourceAirport or DestAirport columns of the flights table. The result includes airport codes such as AAF, ABI, ABL, ABQ, and ABR — with AAF appearing most frequently (1 row)
- **Steps:** build_schema_context, build_query_plan, generate_sql_candidate, validate_sql, execute_sql, profile_result, suggest_chart, suggest_followups, answer_synthesizer
- **Artifacts:** query_plan, sql, safety, table, insight
- **Result:** Result mismatch: Row mismatch: gold=['Ada '], agent=['AAF']
- **Quality Score:** 3/5 (checks: {"completed": false, "sql_generated": true, "execution_match": false, "has_safety": true, "has_answer": true, "has_query_plan": true, "has_table": true, "has_error": false, "flow_complete": true})

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
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "execute_sql",
    "error": null,
    "artifact_type": "table"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "profile_result",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "profile_result",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "profile_result",
    "error": null,
    "artifact_type": "insight"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "suggest_followups",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "suggest_followups",
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

### ✅ Case `spider-dev-036` (hard)

- **Question:** Which cities do more than one employee under age 30 come from?
- **DB Name:** `employee_hire_evaluation`
- **Gold SQL:**
  ```sql
  SELECT city FROM employee WHERE age  <  30 GROUP BY city HAVING count(*)  >  1
  ```
- **Agent SQL:**
  ```sql
  SELECT City FROM employee WHERE Age < 30 GROUP BY City HAVING COUNT(*) > 1 LIMIT 1000
  ```
- **Agent Answer:** The city that has more than one employee under age 30 is Bath.
- **Steps:** build_schema_context, build_query_plan, generate_sql_candidate, validate_sql, execute_sql, profile_result, suggest_chart, suggest_followups, answer_synthesizer
- **Artifacts:** query_plan, sql, safety, table, insight
- **Result:** Execution match
- **Quality Score:** 5/5 (checks: {"completed": true, "sql_generated": true, "execution_match": true, "has_safety": true, "has_answer": true, "has_query_plan": true, "has_table": true, "has_error": false, "flow_complete": true})

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
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "execute_sql",
    "error": null,
    "artifact_type": "table"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "profile_result",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "profile_result",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "profile_result",
    "error": null,
    "artifact_type": "insight"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "suggest_followups",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "suggest_followups",
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

### ✅ Case `spider-dev-037` (hard)

- **Question:** Find the cities that have more than one employee under age 30.
- **DB Name:** `employee_hire_evaluation`
- **Gold SQL:**
  ```sql
  SELECT city FROM employee WHERE age  <  30 GROUP BY city HAVING count(*)  >  1
  ```
- **Agent SQL:**
  ```sql
  SELECT City FROM employee WHERE Age < 30 GROUP BY City HAVING COUNT(*) > 1 LIMIT 1000
  ```
- **Agent Answer:** The city that has more than one employee under age 30 is Bath.
- **Steps:** build_schema_context, build_query_plan, generate_sql_candidate, validate_sql, execute_sql
- **Artifacts:** query_plan, sql, safety, table
- **Result:** Execution match
- **Quality Score:** 5/5 (checks: {"completed": true, "sql_generated": true, "execution_match": true, "has_safety": true, "has_answer": true, "has_query_plan": true, "has_table": true, "has_error": false, "flow_complete": true})

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
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "execute_sql",
    "error": null,
    "artifact_type": "table"
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

### ❌ Case `spider-dev-038` (hard)

- **Question:** Find the names of employees who never won any award in the evaluation.
- **DB Name:** `employee_hire_evaluation`
- **Gold SQL:**
  ```sql
  SELECT name FROM employee WHERE Employee_ID NOT IN (SELECT Employee_ID FROM evaluation)
  ```
- **Agent SQL:**
  ```sql
  SELECT e.Name AS name, e.Name AS employee_name FROM employee AS e WHERE NOT EXISTS(SELECT 1 FROM evaluation AS ev WHERE ev.Employee_ID = e.Employee_ID) LIMIT 100
  ```
- **Agent Answer:** The names of employees who never won any award in the evaluation are:

- Mark Regan
- Tim Payne
- Andrew Sheridan
- Phil Vickery
- Steve Borthwick

This result is based on a query that identifies employees with no corresponding records in the evaluation table, and 5 such employees were found.
- **Steps:** build_schema_context, build_query_plan, generate_sql_candidate, validate_sql, execute_sql, profile_result, suggest_chart
- **Artifacts:** query_plan, sql, safety, table, insight
- **Result:** Result mismatch: Column count mismatch: gold=1, agent=2
- **Quality Score:** 3/5 (checks: {"completed": false, "sql_generated": true, "execution_match": false, "has_safety": true, "has_answer": true, "has_query_plan": true, "has_table": true, "has_error": false, "flow_complete": true})

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
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "execute_sql",
    "error": null,
    "artifact_type": "table"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "profile_result",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "profile_result",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "profile_result",
    "error": null,
    "artifact_type": "insight"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "suggest_chart",
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

### ❌ Case `spider-dev-039` (hard)

- **Question:** What are the names of the employees who never received any evaluation?
- **DB Name:** `employee_hire_evaluation`
- **Gold SQL:**
  ```sql
  SELECT name FROM employee WHERE Employee_ID NOT IN (SELECT Employee_ID FROM evaluation)
  ```
- **Agent SQL:**
  ```sql
  SELECT e.Name AS name, e.Name AS employee_name FROM employee AS e WHERE NOT EXISTS(SELECT 1 FROM evaluation AS ev WHERE ev.Employee_ID = e.Employee_ID) LIMIT 100
  ```
- **Agent Answer:** The names of the employees who never received any evaluation are:

- Mark Regan
- Tim Payne
- Andrew Sheridan
- Phil Vickery
- Steve Borthwick
- **Steps:** build_schema_context, build_query_plan, generate_sql_candidate, validate_sql, execute_sql
- **Artifacts:** query_plan, sql, safety, table
- **Result:** Result mismatch: Column count mismatch: gold=1, agent=2
- **Quality Score:** 3/5 (checks: {"completed": false, "sql_generated": true, "execution_match": false, "has_safety": true, "has_answer": true, "has_query_plan": true, "has_table": true, "has_error": false, "flow_complete": true})

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
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "execute_sql",
    "error": null,
    "artifact_type": "table"
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

### ✅ Case `spider-dev-040` (hard)

- **Question:** Find the name of the shops that do not hire any employee.
- **DB Name:** `employee_hire_evaluation`
- **Gold SQL:**
  ```sql
  SELECT name FROM shop WHERE shop_id NOT IN (SELECT shop_id FROM hiring)
  ```
- **Agent SQL:**
  ```sql
  SELECT shop.Name AS name FROM shop WHERE NOT EXISTS(SELECT 1 FROM hiring WHERE hiring.Shop_ID = shop.Shop_ID) LIMIT 100
  ```
- **Agent Answer:** The shops that do not hire any employee are: FC Honka, KuPS, and IFK Mariehamn.
- **Steps:** build_schema_context, build_query_plan, generate_sql_candidate, validate_sql, execute_sql
- **Artifacts:** query_plan, sql, safety, table
- **Result:** Execution match
- **Quality Score:** 5/5 (checks: {"completed": true, "sql_generated": true, "execution_match": true, "has_safety": true, "has_answer": true, "has_query_plan": true, "has_table": true, "has_error": false, "flow_complete": true})

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
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "execute_sql",
    "error": null,
    "artifact_type": "table"
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

### ✅ Case `spider-dev-041` (extra)

- **Question:** What is the name of the visitor who visited both a museum opened before 2009 and a museum opened after 2011?
- **DB Name:** `museum_visit`
- **Gold SQL:**
  ```sql
  SELECT t1.name FROM visitor AS t1 JOIN visit AS t2 ON t1.id  =  t2.visitor_id JOIN museum AS t3 ON t3.Museum_ID  =  t2.Museum_ID WHERE t3.open_year  <  2009 INTERSECT SELECT t1.name FROM visitor AS t1 JOIN visit AS t2 ON t1.id  =  t2.visitor_id JOIN museum AS t3 ON t3.Museum_ID  =  t2.Museum_ID WHERE t3.open_year  >  2011
  ```
- **Agent SQL:**
  ```sql
  SELECT DISTINCT v.Name AS visitor_name FROM visitor AS v WHERE EXISTS(SELECT 1 FROM visit AS vi JOIN museum AS m ON vi.Museum_ID = m.Museum_ID WHERE vi.visitor_ID = v.ID AND m.Open_Year < '2009') AND EXISTS(SELECT 1 FROM visit AS vi JOIN museum AS m ON vi.Museum_ID = m.Museum_ID WHERE vi.visitor_ID = v.ID AND m.Open_Year > '2011') LIMIT 100
  ```
- **Agent Answer:** The name of the visitor who visited both a museum opened before 2009 and a museum opened after 2011 is Fernando Gago.
- **Steps:** build_schema_context, build_query_plan, generate_sql_candidate, validate_sql, execute_sql
- **Artifacts:** query_plan, sql, safety, table
- **Result:** Execution match
- **Quality Score:** 5/5 (checks: {"completed": true, "sql_generated": true, "execution_match": true, "has_safety": true, "has_answer": true, "has_query_plan": true, "has_table": true, "has_error": false, "flow_complete": true})

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
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "execute_sql",
    "error": null,
    "artifact_type": "table"
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

### ✅ Case `spider-dev-042` (extra)

- **Question:** Show the record companies shared by orchestras founded before 2003 and after 2003.
- **DB Name:** `orchestra`
- **Gold SQL:**
  ```sql
  SELECT Record_Company FROM orchestra WHERE Year_of_Founded  <  2003 INTERSECT SELECT Record_Company FROM orchestra WHERE Year_of_Founded  >  2003
  ```
- **Agent SQL:**
  ```sql
  SELECT DISTINCT t1.Record_Company FROM orchestra AS t1 WHERE t1.Year_of_Founded < 2003 AND EXISTS(SELECT 1 FROM orchestra AS t2 WHERE t2.Record_Company = t1.Record_Company AND t2.Year_of_Founded > 2003) LIMIT 100
  ```
- **Agent Answer:** The only record company shared by orchestras founded before 2003 and after 2003 is Decca Records.
- **Steps:** build_schema_context, build_query_plan, generate_sql_candidate, validate_sql, execute_sql
- **Artifacts:** query_plan, sql, safety, table
- **Result:** Execution match
- **Quality Score:** 5/5 (checks: {"completed": true, "sql_generated": true, "execution_match": true, "has_safety": true, "has_answer": true, "has_query_plan": true, "has_table": true, "has_error": false, "flow_complete": true})

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
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "execute_sql",
    "error": null,
    "artifact_type": "table"
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

### ✅ Case `spider-dev-043` (extra)

- **Question:** What are the record companies that are used by both orchestras founded before 2003 and those founded after 2003?
- **DB Name:** `orchestra`
- **Gold SQL:**
  ```sql
  SELECT Record_Company FROM orchestra WHERE Year_of_Founded  <  2003 INTERSECT SELECT Record_Company FROM orchestra WHERE Year_of_Founded  >  2003
  ```
- **Agent SQL:**
  ```sql
  SELECT DISTINCT t1.Record_Company FROM orchestra AS t1 WHERE EXISTS(SELECT 1 FROM orchestra AS t2 WHERE t2.Record_Company = t1.Record_Company AND t2.Year_of_Founded < 2003) AND EXISTS(SELECT 1 FROM orchestra AS t3 WHERE t3.Record_Company = t1.Record_Company AND t3.Year_of_Founded > 2003) LIMIT 1000
  ```
- **Agent Answer:** The only record company used by both orchestras founded before 2003 and those founded after 2003 is Decca Records.
- **Steps:** build_schema_context, build_query_plan, generate_sql_candidate, validate_sql, execute_sql
- **Artifacts:** query_plan, sql, safety, table
- **Result:** Execution match
- **Quality Score:** 5/5 (checks: {"completed": true, "sql_generated": true, "execution_match": true, "has_safety": true, "has_answer": true, "has_query_plan": true, "has_table": true, "has_error": false, "flow_complete": true})

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
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "execute_sql",
    "error": null,
    "artifact_type": "table"
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

### ❌ Case `spider-dev-044` (extra)

- **Question:** Show the names of all of the high schooler Kyle's friends.
- **DB Name:** `network_1`
- **Gold SQL:**
  ```sql
  SELECT T3.name FROM Friend AS T1 JOIN Highschooler AS T2 ON T1.student_id  =  T2.id JOIN Highschooler AS T3 ON T1.friend_id  =  T3.id WHERE T2.name  =  "Kyle"
  ```
- **Agent SQL:**
  ```sql
  SELECT h2.name AS name, h2.name AS highschooler_name FROM highschooler AS h1 JOIN friend AS f ON h1.ID = f.student_id JOIN highschooler AS h2 ON f.friend_id = h2.ID WHERE h1.name = 'Kyle' LIMIT 100
  ```
- **Agent Answer:** Kyle's friend is Jordan.
- **Steps:** build_schema_context, build_query_plan, generate_sql_candidate, validate_sql, execute_sql
- **Artifacts:** query_plan, sql, safety, table
- **Result:** Result mismatch: Column count mismatch: gold=1, agent=2
- **Quality Score:** 3/5 (checks: {"completed": false, "sql_generated": true, "execution_match": false, "has_safety": true, "has_answer": true, "has_query_plan": true, "has_table": true, "has_error": false, "flow_complete": true})

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
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "execute_sql",
    "error": null,
    "artifact_type": "table"
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

### ✅ Case `spider-dev-045` (extra)

- **Question:** Show ids of all students who do not have any friends.
- **DB Name:** `network_1`
- **Gold SQL:**
  ```sql
  SELECT id FROM Highschooler EXCEPT SELECT student_id FROM Friend
  ```
- **Agent SQL:**
  ```sql
  SELECT ID FROM highschooler AS h WHERE NOT EXISTS(SELECT 1 FROM friend AS f WHERE f.student_id = h.ID) LIMIT 1000
  ```
- **Agent Answer:** The IDs of students who do not have any friends are: 1025 and 1641.
- **Steps:** build_schema_context, build_query_plan, generate_sql_candidate, validate_sql, execute_sql
- **Artifacts:** query_plan, sql, safety, table
- **Result:** Execution match
- **Quality Score:** 5/5 (checks: {"completed": true, "sql_generated": true, "execution_match": true, "has_safety": true, "has_answer": true, "has_query_plan": true, "has_table": true, "has_error": false, "flow_complete": true})

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
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "execute_sql",
    "error": null,
    "artifact_type": "table"
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

### ✅ Case `spider-dev-046` (extra)

- **Question:** What are the ids of high school students who do not have friends?
- **DB Name:** `network_1`
- **Gold SQL:**
  ```sql
  SELECT id FROM Highschooler EXCEPT SELECT student_id FROM Friend
  ```
- **Agent SQL:**
  ```sql
  SELECT ID FROM highschooler AS h WHERE NOT EXISTS(SELECT 1 FROM friend AS f WHERE f.student_id = h.ID) LIMIT 1000
  ```
- **Agent Answer:** The IDs of high school students who do not have friends are 1025 and 1641.
- **Steps:** build_schema_context, build_query_plan, generate_sql_candidate, validate_sql, execute_sql
- **Artifacts:** query_plan, sql, safety, table
- **Result:** Execution match
- **Quality Score:** 5/5 (checks: {"completed": true, "sql_generated": true, "execution_match": true, "has_safety": true, "has_answer": true, "has_query_plan": true, "has_table": true, "has_error": false, "flow_complete": true})

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
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "execute_sql",
    "error": null,
    "artifact_type": "table"
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

### ❌ Case `spider-dev-047` (extra)

- **Question:** Show names of all high school students who do not have any friends.
- **DB Name:** `network_1`
- **Gold SQL:**
  ```sql
  SELECT name FROM Highschooler EXCEPT SELECT T2.name FROM Friend AS T1 JOIN Highschooler AS T2 ON T1.student_id  =  T2.id
  ```
- **Agent SQL:**
  ```sql
  SELECT h.name AS name, h.name AS highschooler_name FROM highschooler AS h WHERE NOT EXISTS(SELECT 1 FROM friend AS f WHERE f.student_id = h.ID) LIMIT 1000
  ```
- **Agent Answer:** The high school students who do not have any friends are John and Brittany.
- **Steps:** build_schema_context, build_query_plan, generate_sql_candidate, validate_sql, execute_sql, profile_result, suggest_chart, suggest_followups, answer_synthesizer
- **Artifacts:** query_plan, sql, safety, table, insight
- **Result:** Result mismatch: Column count mismatch: gold=1, agent=2
- **Quality Score:** 3/5 (checks: {"completed": false, "sql_generated": true, "execution_match": false, "has_safety": true, "has_answer": true, "has_query_plan": true, "has_table": true, "has_error": false, "flow_complete": true})

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
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "execute_sql",
    "error": null,
    "artifact_type": "table"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "profile_result",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "profile_result",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "profile_result",
    "error": null,
    "artifact_type": "insight"
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "suggest_chart",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.started",
    "type": "agent.step.started",
    "step": "suggest_followups",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "suggest_followups",
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

### ❌ Case `spider-dev-048` (extra)

- **Question:** What are the names of students who have no friends?
- **DB Name:** `network_1`
- **Gold SQL:**
  ```sql
  SELECT name FROM Highschooler EXCEPT SELECT T2.name FROM Friend AS T1 JOIN Highschooler AS T2 ON T1.student_id  =  T2.id
  ```
- **Agent SQL:**
  ```sql
  SELECT h.name AS name, h.name AS highschooler_name FROM highschooler AS h WHERE NOT EXISTS(SELECT 1 FROM friend AS f WHERE f.student_id = h.ID) LIMIT 100
  ```
- **Agent Answer:** The names of students who have no friends are John and Brittany.
- **Steps:** build_schema_context, build_query_plan, generate_sql_candidate, validate_sql, execute_sql
- **Artifacts:** query_plan, sql, safety, table
- **Result:** Result mismatch: Column count mismatch: gold=1, agent=2
- **Quality Score:** 3/5 (checks: {"completed": false, "sql_generated": true, "execution_match": false, "has_safety": true, "has_answer": true, "has_query_plan": true, "has_table": true, "has_error": false, "flow_complete": true})

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
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "execute_sql",
    "error": null,
    "artifact_type": "table"
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

### ✅ Case `spider-dev-049` (extra)

- **Question:** Show the ids of high schoolers who have friends and are also liked by someone else.
- **DB Name:** `network_1`
- **Gold SQL:**
  ```sql
  SELECT student_id FROM Friend INTERSECT SELECT liked_id FROM Likes
  ```
- **Agent SQL:**
  ```sql
  SELECT h.ID FROM highschooler AS h WHERE EXISTS(SELECT 1 FROM friend AS f WHERE f.student_id = h.ID) AND EXISTS(SELECT 1 FROM likes AS l WHERE l.liked_id = h.ID) LIMIT 1000
  ```
- **Agent Answer:** The IDs of high schoolers who have friends and are also liked by someone else are: 1101, 1247, 1304, 1468, and 1501. A total of 8 such high schoolers were found.
- **Steps:** build_schema_context, build_query_plan, generate_sql_candidate, validate_sql, execute_sql
- **Artifacts:** query_plan, sql, safety, table
- **Result:** Execution match
- **Quality Score:** 5/5 (checks: {"completed": true, "sql_generated": true, "execution_match": true, "has_safety": true, "has_answer": true, "has_query_plan": true, "has_table": true, "has_error": false, "flow_complete": true})

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
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "execute_sql",
    "error": null,
    "artifact_type": "table"
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

### ✅ Case `spider-dev-050` (extra)

- **Question:** What are the ids of students who both have friends and are liked?
- **DB Name:** `network_1`
- **Gold SQL:**
  ```sql
  SELECT student_id FROM Friend INTERSECT SELECT liked_id FROM Likes
  ```
- **Agent SQL:**
  ```sql
  SELECT DISTINCT h.ID AS id FROM highschooler AS h WHERE EXISTS(SELECT 1 FROM friend AS f WHERE f.student_id = h.ID) AND EXISTS(SELECT 1 FROM likes AS l WHERE l.liked_id = h.ID) LIMIT 100
  ```
- **Agent Answer:** The IDs of students who both have friends and are liked are: 1101, 1247, 1304, 1468, and 1501. A total of 8 such students were found.
- **Steps:** build_schema_context, build_query_plan, generate_sql_candidate, validate_sql, execute_sql
- **Artifacts:** query_plan, sql, safety, table
- **Result:** Execution match
- **Quality Score:** 5/5 (checks: {"completed": true, "sql_generated": true, "execution_match": true, "has_safety": true, "has_answer": true, "has_query_plan": true, "has_table": true, "has_error": false, "flow_complete": true})

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
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.step.completed",
    "type": "agent.step.completed",
    "step": "execute_sql",
    "error": null,
    "artifact_type": null
  },
  {
    "event": "agent.artifact.created",
    "type": "agent.artifact.created",
    "step": "execute_sql",
    "error": null,
    "artifact_type": "table"
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
