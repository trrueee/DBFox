# dbfox.scene - complete Lead task template

> 文档类型：工程交接
>
> 状态：当前
>
> 最后核验：2026-09-06
>
> 适用范围：Creative DLC AI handoff

Read [the current handoff](../creative-program-handoff.md) and [task packets](task-packets.md) first. This preserved template defines the original scope, not the current completion state. Do not recreate completed code or automatically start the whole program.

## DLC LEAD TEMPLATE

你是 DBFox 的独立 Capability DLC Lead。

你的任务：

```text
DLC: dbfox.scene

领域:
### 4.1 dbfox.scene

定位：

> AI-native 3D Scene Studio / Blender-lite

建议 canonical model：

```text
SceneDocument
├── Objects
├── Hierarchy
├── Geometry refs
├── Materials
├── Cameras
├── Lights
└── Scene settings
```

至少支持：

* scene_create
* object_create
* object_duplicate
* object_transform
* object_delete
* material_create
* material_assign
* light_create
* camera_create
* hierarchy inspect
* export glTF / GLB

Workbench：

* Three.js viewport
* hierarchy tree
* inspector
* selection
* transform controls

重点：

Agent 必须增量修改 canonical SceneDocument。

禁止每次重新生成完整场景。

---


```

这不是 demo。

这不是 architecture-only exercise。

这不是 prototype。

目标是：

> 建立一个符合 DBFox 当前 Agent Core / Capability DLC architecture contract 的完整创作领域能力。

---

### A. 首先理解 Host

完整阅读：

* AGENTS.md
* CONTRIBUTING.md
* docs/architecture/
* docs/specs/
* docs/quality/
* DLC runtime
* typed Host Extension APIs
* Workbench contribution system

重点研究：

dbfox.music, dbfox.story, dbfox.visualization, dbfox.data, dbfox.workspace, dbfox.github

但是禁止机械复制。

---

### B. 第一个问题

在写代码之前必须定义：

> 这个领域真正的 canonical durable model 是什么？

明确区分：

```text
Resource
Object
Selection
View state
Canonical durable state
Derived state
Artifact
Representation
Operation
```

禁止混淆。

尤其：

UI selection 不等于 authority。

Object 不等于 Resource。

View state 不等于 durable truth。

---

### C. 你必须继续创建自己的子 Agent

如果环境支持 subagents，至少创建：

#### 1. Domain Architect

只负责：

* canonical model
* invariants
* Resource boundary
* Object boundary
* operation semantics
* concurrency
* versioning
* undo
* diff
* persistence
* context semantics

它第一轮不要写实现。

---

#### 2. Backend Engineer

负责：

* backend package
* state
* persistence
* migration
* tools
* operations
* artifacts
* representations
* resource provider
* resolver
* context
* lifecycle

---

#### 3. Workbench Engineer

负责：

* frontend module
* connector
* dock
* renderer
* interaction
* direct manipulation
* keyboard/mouse flows
* visual state
* user editing

要求：

用户必须可以直接编辑作品。

不能只有 Agent 能改。

不能只是 JSON viewer。

---

#### 4. Verification Engineer

负责：

* deterministic tests
* architecture contracts
* capability benchmark
* state transitions
* failure handling
* persistence tests
* frontend tests
* lifecycle tests

---

#### 5. Adversarial Reviewer

在其他实现基本完成前保持独立。

最后专门攻击：

* Core leakage
* stale version
* lost update
* concurrent edit
* cancel
* retry
* crash recovery
* DLC deactivate
* invalid input
* oversized document
* corrupted state
* authority bypass
* unsafe external resource
* frontend/backend divergence

Reviewer 不允许默认相信实现者的解释。

---

### D. 每个 DLC 必须回答的问题

必须明确回答：

1. Resource 是什么？
2. Object 是什么？
3. Selection 是什么？
4. canonical document 是什么？
5. state.sqlite3 中真正 durable 的事实是什么？
6. 哪些信息只是 frontend view state？
7. 哪些信息进入 Agent context？
8. 哪些信息绝对不进入 Agent context？
9. document version 如何变化？
10. stale ToolInvocation 如何处理？
11. 用户直接编辑和 Agent 修改冲突时怎么办？
12. 是否需要 operation log？
13. 如何 undo？
14. 如何 diff？
15. crash 后怎么恢复？
16. deactivate DLC 后怎么清理 active contributions？
17. Project 删除时怎么处理自己的 state？
18. 大型作品怎么避免整个塞进 context？
19. tool result 如何 bounded？
20. 哪些动作需要 approval？
21. 哪些动作可 retry？
22. 哪些动作非幂等？
23. 如何输出 artifact？
24. 是否提供 Representation 给其他 DLC？
25. 将来 Composition DLC 应如何消费它？

---

### E. Tool 设计原则

Agent 不允许每次重新生成整个作品。

优先：

```text
Inspect
→ propose/change
→ structured operation
→ validate
→ apply
→ persist
→ artifact/evidence
```

而不是：

```text
prompt
→ regenerate entire JSON
→ overwrite everything
```

所有大规模操作设计为高层领域操作。

例如不要：

```text
set_pixel(x,y)
```

执行 10 万次。

而应有：

```text
fill_region
stamp
transform_region
```

同理适用于 voxel / scene / CAD / game 等领域。

---

### F. Workbench 标准

每个创意 DLC 必须拥有一个真正体现该领域的专业 Workbench。

不能把：

```text
<textarea>
JSON
</textarea>
```

视为完整 UI。

Workbench 必须至少支持：

* 可视化当前作品
* direct manipulation
* selection
* inspect
* edit
* undo-compatible operations
* Agent reference handoff

视图 state 必须与 canonical durable state 分离。

---

### G. Agent + Human 双向编辑

系统必须支持：

```text
Human direct edit
        ↓
canonical state
        ↓
Agent inspect
        ↓
Agent tool operation
        ↓
canonical state
        ↓
Human immediately sees result
```

禁止维护两套事实：

```text
Agent document
Human document
```

必须只有一个 canonical durable model。

---

### H. Concurrent Edit / Stale Version

必须设计 optimistic version fence 或等效机制。

例：

Agent 在 version 17 inspect。

用户随后编辑到 version 18。

Agent 基于 version 17 的操作不能静默覆盖 version 18。

必须：

* reject
* re-inspect
* rebase
* 或使用经过证明安全的领域 operation

不得 silently overwrite。

---

### I. 测试要求

Verification Agent 必须创建测试覆盖：

#### Domain

* create
* inspect
* modify
* delete
* malformed operation
* invalid reference
* invalid state transition

#### Persistence

* restart
* crash
* partial failure
* state reload
* migration

#### Version

* stale operation
* concurrent edit
* lost-update prevention

#### Runtime

* cancel
* timeout
* retry
* duplicate invocation

#### DLC lifecycle

* activate
* deactivate
* reactivate
* contribution cleanup

#### Frontend

* render
* selection
* direct edit
* state synchronization

#### Agent

* tool discoverability
* resource authority
* context bounding
* object references

---

### J. Capability Benchmark

每个 DLC 必须建立自己的 capability benchmark。

至少包括：

* simple creation
* incremental modification
* multi-stage creation
* recovery from invalid instruction
* inspect-before-edit
* stale version
* no-op request
* ambiguous request
* large document
* bounded context
* user edit followed by Agent edit
* negative task where no modification should occur

尽量 deterministic scoring。

不要使用另一个 LLM 作为主要 grader。

---

### K. Creative Stress Test

实现完成后：

让 Agent 实际使用自己的 DLC 创建一个具有一定复杂度的作品。

随后连续执行至少 10 次不同修改。

修改必须包括：

1. 添加内容
2. 删除内容
3. 局部变化
4. 大范围重构
5. 参数修改
6. 模糊指令
7. 与当前状态冲突的指令
8. 用户直接编辑后的 Agent 修改
9. undo / correction
10. 最终 refinement

检查过程中不得绕过生产 Tool path。

---

### L. DLC Lead Exit Criteria

只有全部满足才能完成：

* canonical model 明确
* Core 零领域泄漏
* backend 可工作
* frontend 可工作
* durable persistence
* Agent tools 可工作
* human direct manipulation 可工作
* stale version 有保护
* deterministic tests
* capability benchmark
* architecture docs
* example project
* adversarial review 完成
* 所有 confirmed high severity findings 已处理

然后向 Program Director 提交：

```text
DLC COMPLETION REPORT

Architecture:
...

Canonical model:
...

Resource:
...

Objects:
...

Tools:
...

Artifacts:
...

Representations:
...

Workbench:
...

Verification:
...

Bench:
...

Core changes:
...

Core leakage audit:
...

Known limitations:
...

Composition opportunities:
...
```

---
