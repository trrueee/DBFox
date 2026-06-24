# DBFox 软件质量保证规格说明（QA Spec）

> 本目录是基于系统设计与质量标准产出的可立项、可追踪、可验收的质量工程文档集。
> 与设计文档 `docs/designs/2026-06-17-db-tools-spec.md`（描述工具「应该做什么」）互补，
> 本目录描述「系统在质量、安全、测试方面必须满足什么」。

---

## 文档索引

| 文档 | 对应报告章节 | 内容 | 主要读者 |
|---|---|---|---|
| [04-integration-test.md](./04-integration-test.md) | 第 4 节 | 集成测试与系统测试规格 | 测试工程师 |
| [05-defect-reports.md](./05-defect-reports.md) | 第 5 节 | 7 张具体缺陷单（D1–D7） | 开发 + 测试 + 产品 |
| [06-whitebox-test.md](./06-whitebox-test.md) | 第 6 节 | 核心方法白盒测试用例（G/DELIM/SV/RES/CONF/PREVIEW/WHERE/ROW/TG/TUNNEL） | 测试工程师 |
| [07-blackbox-test.md](./07-blackbox-test.md) | 第 7 节 | 黑盒测试用例（等价类/边界值/错误推测/场景/状态迁移，136 例） | 测试工程师 + QA |
| [08-nonfunctional.md](./08-nonfunctional.md) | 第 8 节 | 非功能需求 NFR（安全/异常/性能/可用性，23 条） | 架构 + 开发 |
| [09-refactoring.md](./09-refactoring.md) | 第 9 节 | 8 条安全重构方案（R1–R8） | 开发 |
| [10-frontend-ux-issues.md](./10-frontend-ux-issues.md) | N/A | 前端对话与 SQL 结果展示问题梳理及修复状态 | 前端开发 + UX |

---

## 交叉引用关系

```
缺陷单 (05) ──回归测试──► 白盒用例 (06) + 黑盒用例 (07)
   │
   ├──修复方案──► 重构方案 (09)
   │
   └──质量属性──► NFR (08)

重构方案 (09) ──守护测试──► 集成测试 (04) + golden set
   │
   └──落实──► NFR (08)
```

**编号体系**：
- 缺陷：`D1`–`D7`
- 白盒用例：`G3`、`SV-2`、`RES-4`、`CONF-8`、`PREVIEW-1`…（按方法前缀）
- 黑盒用例：`SQL-EQ-1`、`AGENT-SCN-2`、`DS-CONF-3`…（功能域-类别-序号）
- NFR：`NFR-SEC-1`、`NFR-PRF-5`…（域-序号）
- 重构：`R1`–`R8`

缺陷单的「回归测试」字段、NFR 的「验证」字段、重构的「守护测试」字段，统一引用上述编号。

---

## 优先级总览

### P0（本周必须闭环）
- **缺陷**：D1（preview 注入）、D2（结果未脱敏）
- **NFR**：NFR-SEC-1、NFR-SEC-2、NFR-PRF-1、NFR-PRF-2、NFR-USE-6
- **重构**：R2、R3
- **测试**：所有 P0 黑盒用例（约 68 例）+ PREVIEW/WHERE/REDACT 白盒用例

### P1（两周内）
- **缺陷**：D3、D4、D5
- **NFR**：NFR-SEC-3/4/5/6/7、NFR-EXC-1/2、NFR-PRF-5、NFR-USE-1/3/4/5
- **重构**：R1、R7

### P2（季度内）
- **缺陷**：D6、D7
- **NFR**：其余
- **重构**：R4、R5、R6、R8

---

## 使用方式

1. **立项时**：从 05 缺陷单 / 08 NFR 中挑条目建 ticket，描述引用对应 ID
2. **开发时**：按 09 重构方案的小步拆解执行，每步引用守护测试编号
3. **测试时**：06 + 07 是测试用例库的索引，按编号在 `engine/tests/whitebox/` 与 `engine/tests/blackbox/` 落地代码
4. **发版门**：第 4 节 §9 验收清单 + 第 7 节 P0 用例 + 第 8 节 P0 NFR 全绿方可发版
5. **回归时**：第 4 节 §7 两份 golden set 是 guardrail 规则变更的强制门

---

## 与既有文档的关系

| 既有文档 | 关系 |
|---|---|
| `docs/designs/2026-06-17-db-tools-spec.md` | 描述工具「做什么」；本目录描述「做到什么质量」 |
| `docs/软件重构和测试.md` | 早期质量分析报告；本目录是其规格化、可立项化的延伸 |
