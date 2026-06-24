# Agent Answer Artifact SQL-First P1/P2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the P0 agent answer/artifact work with clickable evidence references, richer SQL/table/chart metadata, and larger-result browsing controls.

**Architecture:** Keep the current payload-based artifact transport. Add a frontend reference layer that derives table, SQL, result, chart, and column references from existing artifacts and `refs` payloads. Enrich artifact payload builders where backend metadata is already available, then upgrade artifact views with search/sort/window controls and source-field affordances.

**Tech Stack:** Python 3.12, pytest, React 19, TypeScript, Vitest, Testing Library, lucide-react.

---

## File Structure

- Modify `engine/agent_core/artifacts.py`: add `purpose`, `used_tables`, row metadata, warning/notices, and basic chart metric source refs to artifact payloads.
- Modify `engine/agent/tests/test_agent_artifacts.py`: verify SQL/table/chart artifact metadata.
- Modify `engine/agent/model/system_prompt.py`: reinforce follow-up analytical SQL after raw preview when analysis is needed.
- Modify `engine/tests/test_analysis_flow.py`: assert the prompt contains follow-up SQL guidance.
- Modify `desktop/src/types/agentArtifact.ts`: add `DataReference`, SQL metadata, chart source refs, and result table controls metadata.
- Modify `desktop/src/features/workspace/agentBridge.ts`: map backend metadata into view artifacts and derive references.
- Create `desktop/src/features/conversation/workspace/DataReferencePanel.tsx`: render reference chips for table, column, SQL, result, and chart artifacts.
- Modify `desktop/src/features/conversation/workspace/MessageBubble.tsx`: render `DataReferencePanel` near evidence.
- Modify `desktop/src/features/conversation/workspace/ArtifactEvidencePanel.tsx`: render clickable SQL table/field tokens and preserve existing evidence grouping.
- Modify `desktop/src/features/workspace/artifacts/SqlArtifactView.tsx`: show purpose, used tables, row count, latency, validation/execution state.
- Modify `desktop/src/features/workspace/artifacts/TableArtifactView.tsx`: add search, sorting, loaded-row windowing, notices, and view-all toggle.
- Modify `desktop/src/features/workspace/artifacts/ChartArtifactView.tsx`: show source metric formulas and dimensions.
- Tests:
  - `desktop/src/features/conversation/workspace/__tests__/DataReferencePanel.test.tsx`
  - `desktop/src/features/workspace/__tests__/agentBridge.test.ts`
  - `desktop/src/features/workspace/artifacts/__tests__/SqlArtifactView.test.tsx`
  - `desktop/src/features/workspace/artifacts/__tests__/TableArtifactView.test.tsx`
  - `desktop/src/features/workspace/artifacts/__tests__/ChartArtifactView.test.tsx`

## Task 1: Backend Metadata

- [ ] **Step 1: Write failing backend tests**

Add tests that call `build_sql_artifact`, `build_table_artifact`, and `build_chart_artifact` and assert:

```python
assert sql.payload["purpose"] == "分析查询"
assert "orders" in sql.payload["used_tables"]
assert table.payload["returnedRows"] == 2
assert table.payload["truncated"] is True
assert chart.payload["source_refs"][0]["field"] == "orders.amount"
```

- [ ] **Step 2: Run red**

Run:

```bash
python -m pytest engine/agent/tests/test_agent_artifacts.py -q
```

- [ ] **Step 3: Implement metadata extraction**

Use simple, conservative SQL table extraction for `FROM`/`JOIN`, pass execution row counts through unchanged, and map chart `x`, `y`, `metric`, and `aggregation` into `source_refs`.

- [ ] **Step 4: Run green**

Run:

```bash
python -m pytest engine/agent/tests/test_agent_artifacts.py -q
```

## Task 2: Reference Protocol And Panel

- [ ] **Step 1: Write failing frontend tests**

Create `DataReferencePanel.test.tsx` and extend `agentBridge.test.ts` to assert derived refs:

```tsx
expect(screen.getByText("orders")).toBeTruthy();
expect(screen.getByText("SQL: 趋势分析")).toBeTruthy();
expect(screen.getByText("结果表")).toBeTruthy();
expect(screen.getByText("趋势图")).toBeTruthy();
```

- [ ] **Step 2: Run red**

Run:

```bash
npm --prefix desktop test -- DataReferencePanel.test.tsx agentBridge.test.ts
```

- [ ] **Step 3: Implement DataReference types and panel**

Add `DataReference` to `desktop/src/types/agentArtifact.ts`, derive references in `agentBridge.ts`, and render reference chips in `MessageBubble.tsx`.

- [ ] **Step 4: Run green**

Run:

```bash
npm --prefix desktop test -- DataReferencePanel.test.tsx agentBridge.test.ts
```

## Task 3: SQL And Chart Artifact Metadata UI

- [ ] **Step 1: Write failing tests**

Add tests for SQL purpose/used-tables/row count/latency and chart source formulas.

- [ ] **Step 2: Run red**

Run:

```bash
npm --prefix desktop test -- SqlArtifactView.test.tsx ChartArtifactView.test.tsx
```

- [ ] **Step 3: Implement UI**

Show compact metadata chips in SQL and chart artifact cards. Keep actions unchanged.

- [ ] **Step 4: Run green**

Run:

```bash
npm --prefix desktop test -- SqlArtifactView.test.tsx ChartArtifactView.test.tsx
```

## Task 4: Result Table Search, Sort, And Windowing

- [ ] **Step 1: Extend failing table tests**

Assert search filters rows, column header sort toggles ascending/descending, view-all reveals loaded rows, and large loaded sets render a bounded window.

- [ ] **Step 2: Run red**

Run:

```bash
npm --prefix desktop test -- TableArtifactView.test.tsx
```

- [ ] **Step 3: Implement table controls**

Add a search input, sortable headers, a view-all toggle, and a simple fixed-size render window for loaded results over 500 rows.

- [ ] **Step 4: Run green**

Run:

```bash
npm --prefix desktop test -- TableArtifactView.test.tsx
```

## Task 5: Final Verification

- [ ] **Step 1: Backend verification**

Run:

```bash
python -m pytest engine/agent/tests/test_agent_artifacts.py engine/tests/test_analysis_flow.py::TestSystemPrompt -q
```

- [ ] **Step 2: Frontend verification**

Run:

```bash
npm --prefix desktop test -- DataReferencePanel.test.tsx agentBridge.test.ts SqlArtifactView.test.tsx TableArtifactView.test.tsx ChartArtifactView.test.tsx ArtifactEvidencePanel.test.tsx RunTracePanel.test.tsx
```

- [ ] **Step 3: Build**

Run:

```bash
npm --prefix desktop run build
```

## Self-Review

- P1 coverage: DataReferencePanel, references protocol, result table metadata, CSV/cell copy, SQL metadata, and follow-up SQL guidance are included.
- P2 coverage: field-level references, SQL token affordances, chart source formulas, result table search/sort/windowing are included. Full right-side Inspector and developer raw-event view are deferred because the current workspace layout has no inspector shell yet.
- Placeholder scan: no TBD/TODO placeholders remain.
