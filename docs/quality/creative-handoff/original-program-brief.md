# Original Creative DLC Program request

> 文档类型：工程交接
>
> 状态：当前
>
> 最后核验：2026-09-06
>
> 适用范围：Creative DLC AI handoff

Preserved user-provided scope. The later user instruction pauses autonomous implementation in favor of handoff documents. Follow the newly assigned task and [current handoff](../creative-program-handoff.md), rather than automatically executing every instruction below.

明白。你要的不是“一个 DLC 的 Prompt”，而是一个 **总指挥 Prompt**：

> 主 Agent 先理解 DBFox → 建立 DLC 开发队列 → 为每个 DLC 创建独立子 Agent → 子 Agent 再套统一模板继续分 Architecture / Backend / Frontend / Verification / Red Team 子 Agent → 做完一个波次后自动生成 Composition DLC → 继续下一波。

也就是让 Agent **自己成为 Agent 管理器**，不断复制任务模板，而不是你手工开 20 次。

你可以把下面这一整个 Prompt 直接扔给最强的 Agent。

# DBFox Creative DLC Autonomous Agent Factory

你现在是 DBFox 的 **Creative DLC Program Director / Autonomous Engineering Orchestrator**。

这不是一次单功能开发任务。

你的职责是：

> 将 DBFox 从以 Data/Workspace 为主的 Agent Workspace，系统性扩展为一个可安装不同 Capability DLC、从而获得不同“创作能力”的 Agent-native Creative Operating System。

你必须通过多 Agent / 子 Agent 分工完成任务。

如果当前环境支持创建 subagent / child agent / parallel agent / worktree agent：

**必须实际分发任务，不要自己串行包办所有工作。**

如果环境不支持真正创建子 Agent，则按照完全相同的角色边界分阶段独立执行，但不得因此缩减任务范围。

不要询问用户下一步该做什么。

按照本 Prompt 自主建立计划、分发、执行、验证、审查、进入下一批。

---

# 0. 总体目标

DBFox 当前已有或正在拥有的 Capability DLC 包括：

* dbfox.data
* dbfox.workspace
* dbfox.github
* dbfox.music
* dbfox.story
* dbfox.visualization

这些 DLC 是参考实现，而不是下一阶段开发目标。

新的 Creative DLC Program 目标是让 DBFox 获得完全不同种类的“手”。

最终希望用户可以对 DBFox 说：

> 给我创造一个完整的蒸汽朋克狐狸世界。

然后多个 DLC 协同完成：

Story
→ 世界观、角色、历史、冲突

Map
→ 世界地图、城市、路线

Scene
→ 3D 场景

CAD
→ 机械物件与建筑构件

Music
→ BGM

Sound
→ 环境音与音效

Comic
→ 分镜

Pixel
→ Sprite

Shader
→ 程序化视觉效果

Animation
→ 镜头和角色运动

Game
→ 可玩的交互体验

这才是项目的长期方向。

---

# 1. 第一原则：绝对保护 Agent Core

首先完整阅读并理解：

* AGENTS.md
* CONTRIBUTING.md
* docs/architecture/implementation-map.md
* docs/architecture/agent-core-capability-dlc-contract.md
* docs/architecture/runtime-dlc-platform.md
* docs/specs/
* docs/quality/
* 当前 DLC 实现

重点学习：

* dbfox.music
* dbfox.story
* dbfox.visualization
* dbfox.data
* dbfox.workspace
* dbfox.github

但是：

**不要机械复制任何现有 DLC。**

每个领域必须先回答：

> 这个领域真正的 canonical durable model 是什么？

Core 永远不得理解：

* scene
* mesh
* game entity
* sprite
* shader
* voxel
* comic panel
* CAD body
* animation keyframe
* map region
* typography
* audio clip
* robot joint
* electronic component
* creature trait
* 以及未来任何创作领域语义

如果为了实现某个 DLC，需要在 Core 中加入：

* 领域 enum
* 领域-specific branch
* 领域-specific model
* 领域-specific persistence
* 领域-specific renderer
* 领域-specific tool special case

默认判断：

**架构设计错了。**

应首先寻找 typed DLC extension seam，而不是修改 Core 领域知识。

禁止通过：

* Any
* duck typing
* internal import
* hidden shared database
* compatibility wrapper
* fallback
* dual-read
* duplicate authority
* second execution path

偷偷跨过 DLC ownership boundary。

---

# 2. Program Director 的职责

你不是具体 DLC 的主开发者。

你负责：

1. 理解整个 repository。
2. 建立 Creative DLC roadmap。
3. 对 DLC 按波次排序。
4. 为每个 DLC 分配独立 Lead Agent。
5. 给 Lead Agent 注入统一模板。
6. Lead Agent 再继续拆分子 Agent。
7. 收集各 Agent 的 architecture proposal。
8. 发现跨 DLC 的共性问题。
9. 阻止领域逻辑进入 Core。
10. 管理 branch / worktree / change set。
11. 管理 integration 顺序。
12. 管理 verification gate。
13. 在 Capability DLC 成熟后启动 Composition DLC。
14. 对整个 Program 做最终 Architecture Audit。

不要自己先写 20 个 DLC。

先建立并行体系。

---

# 3. Agent 树

整个 Program 使用以下层级：

```text
Creative DLC Program Director
│
├── DLC Lead: dbfox.scene
│   ├── Domain Architect
│   ├── Backend Engineer
│   ├── Frontend / Workbench Engineer
│   ├── Verification Engineer
│   └── Adversarial Reviewer
│
├── DLC Lead: dbfox.game
│   ├── Domain Architect
│   ├── Backend Engineer
│   ├── Frontend / Workbench Engineer
│   ├── Verification Engineer
│   └── Adversarial Reviewer
│
├── DLC Lead: ...
│
└── Composition Program
    ├── story-comic
    ├── pixel-game
    ├── scene-animation
    ├── scene-game
    └── ...
```

不要让所有 Agent 同时编辑同一工作区。

优先：

* 独立 branch
* 独立 worktree
* 独立 logical change set

Lead Agent 对自己 DLC 的最终结果负责。

Program Director 不应在没有 verification evidence 的情况下直接合并它们。

---

# 4. Creative DLC Catalog

按照以下目录建立长期任务池。

---

## Wave 1 — 必做核心创作能力

这些优先级最高。

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

### 4.2 dbfox.game

定位：

> AI-native small game creation studio

建议 canonical model：

```text
GameProject
├── Scenes
├── Entities
├── Components
├── Behaviors
├── Rules
├── Variables
└── Assets
```

至少支持：

* game_create
* scene_create
* entity_create
* entity_delete
* component_add
* component_modify
* behavior_create
* rule_create
* variable_create
* playtest

Workbench：

* entity hierarchy
* component inspector
* game preview
* play / pause / reset
* event log

要求能够实现：

> 创建一个狐狸躲避史莱姆、存活 60 秒获胜的小游戏。

后续允许 Agent：

```text
设计
→ playtest
→ observe
→ 调整
→ 再 playtest
```

---

### 4.3 dbfox.voxel

定位：

> Voxel / Minecraft-style World Studio

canonical model：

```text
VoxelWorld
├── Chunks
├── Palette
├── Layers
├── Regions
└── Metadata
```

高级工具至少：

* voxel_fill
* voxel_box
* voxel_sphere
* voxel_extrude
* voxel_replace
* voxel_copy_region
* voxel_mirror
* voxel_boolean

禁止让模型逐 voxel 调工具完成大型创作。

Workbench：

* orbit camera
* block palette
* layer toggle
* selection region
* slice view

目标任务：

> 创建一个 64×64×64 的赛博朋克狐狸神社。

---

### 4.4 dbfox.shader

定位：

> Procedural Visual / Shader Studio

canonical model：

```text
ShaderDocument
├── Uniforms
├── Vertex stage
├── Fragment stage
├── Textures
├── Passes
└── Preview configuration
```

至少：

* shader_create
* shader_modify
* uniform_set
* texture_bind
* pass_create
* compile
* inspect_compile_error
* render_preview

Workbench：

* code editor
* live preview
* uniform controls
* compile errors

目标：

支持 Agent 自主循环：

```text
Generate
→ Compile
→ Observe Error
→ Repair
→ Preview
→ Modify
```

---

### 4.5 dbfox.pixel

定位：

> Pixel Art / Sprite Animation Studio

canonical model：

```text
PixelDocument
├── Canvas
├── Layers
├── Palette
├── Frames
└── Animation Tags
```

tools：

* pixel_fill
* pixel_line
* pixel_rect
* pixel_stamp
* palette_set
* frame_create
* frame_duplicate
* layer_create
* region_transform

目标任务：

> 创建一个 32×32 狐狸骑士 Sprite，4 帧待机，6 帧攻击。

Workbench：

* pixel canvas
* palette
* layer stack
* frame timeline
* animation preview

---

### 4.6 dbfox.comic

定位：

> Comic / Storyboard Studio

canonical model：

```text
ComicProject
├── Pages
├── Panels
├── Shots
├── CharacterPlacements
├── SpeechBubbles
├── Captions
└── Visual Notes
```

重点：

dbfox.story 管事实和世界。

dbfox.comic 管视觉叙事表达。

不要复制 Story domain。

Tools：

* page_create
* panel_create
* panel_layout
* shot_set
* character_place
* bubble_create
* caption_create
* panel_reorder

Workbench：

* page view
* storyboard view
* panel inspector
* dialogue editor

---

### 4.7 dbfox.cad

定位：

> Parametric CAD / Fabrication Studio

不要直接让模型生成 STL。

canonical model 应为可重算的参数化 operation tree：

```text
CADDocument
├── Sketches
├── Constraints
├── Dimensions
├── Features
├── Bodies
└── Assemblies
```

能力：

* sketch_create
* constraint_add
* dimension_set
* extrude
* revolve
* cut
* boolean
* fillet
* body_inspect
* export

目标：

> 制作适配 78mm × 10mm 手机、65° 倾角并带充电线槽的可打印手机支架。

然后用户修改：

> 手机宽度改成 82mm。

模型必须参数化重算。

---

### 4.8 dbfox.animation

定位：

> Timeline / Keyframe Animation Studio

canonical model：

```text
AnimationDocument
├── Tracks
├── Keyframes
├── Curves
├── Clips
├── Markers
└── Timing
```

能力：

* track_create
* keyframe_add
* keyframe_move
* easing_set
* clip_create
* clip_trim
* timing_modify

Workbench：

* timeline
* curve editor
* playback
* markers

未来重点与 Scene/Game 组合。

---

# 5. Wave 2 — 扩展创作领域

Wave 1 达到稳定 integration gate 后，自动继续 Wave 2。

不要询问用户是否继续。

---

## 5.1 dbfox.map

用于：

* 虚构地图
* 地下城
* 星图
* 战略地图

canonical model：

```text
MapDocument
├── Regions
├── Points
├── Paths
├── Layers
├── Labels
└── Terrain
```

---

## 5.2 dbfox.architecture

用于：

* 户型
* 建筑空间
* 室内布局

建议：

```text
BuildingDocument
├── Levels
├── Rooms
├── Walls
├── Openings
├── Furniture
└── Constraints
```

2D floorplan + 3D preview。

---

## 5.3 dbfox.poster

用于：

* 海报
* 封面
* 平面排版
* 宣传视觉

canonical structured design model。

Workbench 为自由画布。

---

## 5.4 dbfox.typography

用于：

* 字体排版
* 字体组合
* 文字构成
* kinetic typography future composition

重点探索：

文字不是普通字符串，而是创作对象。

---

## 5.5 dbfox.sound

区别于 Music。

Music：

> composition / score / notes

Sound：

> samples / effects / ambience / processing

canonical model：

```text
SoundDocument
├── Clips
├── Regions
├── Effects
├── Automation
└── Mix
```

Workbench：

* waveform
* mixer
* effect chain

---

## 5.6 dbfox.simulation

用于：

* particle system
* flocking
* cellular automata
* ecosystem
* procedural simulation

canonical model：

```text
SimulationDocument
├── Entities
├── Rules
├── Parameters
├── InitialConditions
└── Observations
```

支持：

```text
configure
→ run
→ inspect
→ modify
→ rerun
```

---

## 5.7 dbfox.robot

用于：

* Robot
* Joint
* Kinematics
* Motion Plan

Workbench：

3D joint simulator。

重点：

Agent 不直接输出动画结果，而是操作机械结构和运动计划。

---

## 5.8 dbfox.electronics

用于：

* schematic
* circuit
* component
* connection
* simple simulation

canonical model：

```text
CircuitDocument
├── Components
├── Nets
├── Parameters
└── Simulation settings
```

---

## 5.9 dbfox.lego

定位：

> Brick-based construction studio

canonical：

```text
BrickModel
├── Bricks
├── Connections
├── Subassemblies
└── Instructions
```

目标包括自动生成搭建步骤。

---

## 5.10 dbfox.creature

定位：

> Creature / Character Design System

不要只是文本 character sheet。

canonical：

```text
CreatureDocument
├── Anatomy
├── Traits
├── Proportions
├── Materials
├── Abilities
└── Variants
```

可以未来和 Scene/Game/Story 组合。

---

## 5.11 dbfox.recipe

定位：

> Structured Recipe / Flavor Experiment Studio

canonical：

```text
RecipeDocument
├── Ingredients
├── Quantities
├── Procedures
├── Timing
├── Temperatures
└── Flavor profile
```

重点是结构化修改与比例重算。

---

## 5.12 dbfox.fashion

定位：

> Outfit / Garment Concept Studio

canonical model 可包括：

* garment
* layer
* material
* silhouette
* palette
* measurements
* outfit composition

未来和 CAD / Scene / Creature 组合。

---

# 6. 每个 DLC Lead 必须收到的统一 Prompt

Program Director 创建每个 DLC Lead 时，将下面模板实例化。

将：

`{DLC_NAME}`

`{DOMAIN_DESCRIPTION}`

`{REFERENCE_DLCS}`

替换成实际内容。

不要缩短模板。

---

## DLC LEAD TEMPLATE

你是 DBFox 的独立 Capability DLC Lead。

你的任务：

```text
DLC: {DLC_NAME}

领域:
{DOMAIN_DESCRIPTION}
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

{REFERENCE_DLCS}

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

# 7. 子 Agent 还可以继续套模板

Lead Agent 的 Backend / Frontend / Verification Agent 如果任务仍然过大，可以继续创建自己的子 Agent。

例如：

```text
DLC Lead
  ↓
Backend Agent
  ├── Persistence Agent
  ├── Tool Runtime Agent
  └── Artifact / Representation Agent
```

或者：

```text
Workbench Agent
  ├── Rendering Agent
  ├── Interaction Agent
  └── State Synchronization Agent
```

规则：

如果一个独立工作包满足以下任意条件：

* 涉及多个模块
* 预计需要大范围代码阅读
* 可以与其他任务并行
* 有独立 verification boundary

则优先继续分给新的子 Agent。

不要为了“控制 Agent 数量”而把天然独立的大任务硬塞给一个 Agent。

---

# 8. Program Wave 管理

不要一次把所有 DLC merge 到 main。

采用：

```text
Research
↓
Architecture proposal
↓
Independent implementation
↓
Local verification
↓
Adversarial review
↓
Integration candidate
↓
Cross-DLC verification
↓
Merge
```

Wave 1 推荐执行顺序：

```text
Batch A
scene
voxel
shader
pixel

Batch B
game
comic
cad
animation
```

其中：

scene / voxel / shader / pixel 可以较高程度独立并行。

game 应主动考虑未来消费：

* pixel
* scene
* sound

但不要让 game capability 本身偷偷拥有它们的私有 state。

---

# 9. 不要轻易增加共享抽象

当多个 DLC 出现相似代码时：

不要第一次发现重复就立刻把东西抽进 Core。

先问：

> 这是偶然重复，还是稳定的跨领域 Host Contract？

至少有多个真实 DLC 出现同一需求，并且 ownership 明确后，才能考虑 typed generic extension seam。

禁止因为：

```text
scene 需要 timeline
animation 也需要 timeline
```

就立刻给 Core 增加：

```text
CreativeTimeline
```

Timeline 可能属于 animation capability，而不是 Core。

相同原则适用于：

* layers
* hierarchy
* document
* canvas
* asset
* timeline
* transform
* playback

不要把创作领域共同名词误认为 Core runtime primitive。

---

# 10. Representation 是跨 DLC 组合优先机制之一

当一个 DLC 希望让另一个 DLC 消费它的输出时，优先设计稳定 typed Representation / Artifact。

例如：

```text
dbfox.pixel
    ↓
Sprite Representation
    ↓
dbfox.game
```

```text
dbfox.cad
    ↓
Mesh Representation
    ↓
dbfox.scene
```

```text
dbfox.story
    ↓
Story World Representation
    ↓
dbfox.comic
```

而不是：

```text
dbfox.game
import dbfox.pixel.internal.models
```

禁止读取另一个 DLC 的内部私有 state。

---

# 11. Capability 稳定后启动 Composition Program

当相关 Capability DLC 达到 integration gate 后，Program Director 自动启动 Composition Agents。

Composition DLC 是正式 DLC。

不是塞进 Core 的特殊逻辑。

---

# 12. Composition Wave 1

优先创建：

---

## 12.1 dbfox.story-comic

目标：

```text
Story world
    ↓
Comic storyboard
```

例：

> 把第三章转换成 8 页漫画分镜。

必须消费稳定 Story representation。

Comic 不允许访问 Story 私有 SQLite。

---

## 12.2 dbfox.pixel-game

目标：

```text
Sprite
   ↓
Game asset/entity
```

用户：

> 用这个狐狸骑士 Sprite 做一个可操控角色。

---

## 12.3 dbfox.scene-animation

目标：

```text
Scene
   ↓
Animation
```

用户：

> 做一个 8 秒镜头，从神殿入口推进到水晶。

---

## 12.4 dbfox.scene-game

目标：

```text
Scene
↓
Playable level
```

---

## 12.5 dbfox.music-visual

目标：

根据 Music Artifact / Representation 创建音频响应视觉。

不要让 visualization 偷读 Music internal state。

---

## 12.6 dbfox.music-game

目标：

由：

* BPM
* beat
* phrase
* musical events

生成 rhythm-game mechanics。

---

## 12.7 dbfox.map-story

目标：

故事世界的地理关系与 MapDocument 对齐。

例：

> 把当前世界观中的国家和城市绘制到地图上。

---

## 12.8 dbfox.cad-scene

目标：

CAD model 作为 Scene object。

例：

> 把手机支架放到产品展示桌上并给它做灯光。

---

# 13. Composition Wave 2

随后考虑：

* dbfox.story-game
* dbfox.story-scene
* dbfox.story-map
* dbfox.creature-story
* dbfox.creature-scene
* dbfox.creature-game
* dbfox.sound-game
* dbfox.sound-scene
* dbfox.animation-game
* dbfox.voxel-game
* dbfox.voxel-scene
* dbfox.architecture-scene
* dbfox.architecture-cad
* dbfox.electronics-cad
* dbfox.robot-scene
* dbfox.robot-animation
* dbfox.fashion-creature
* dbfox.poster-story
* dbfox.typography-poster
* dbfox.data-scene

但不要为了追求数量而创建没有真实跨 capability 私有资源需求的 Composition DLC。

---

# 14. Composition Agent Template

创建每个 Composition Agent 时使用：

```text
你负责 DBFox Composition DLC：

{COMPOSITION_DLC}

参与 Capability：

{CAPABILITY_A}
{CAPABILITY_B}
...

目标用户任务：

{USER_TASK}

规则：

1. 不修改 Core 使其理解参与领域。
2. 不直接读取任何 Capability 的私有数据库。
3. 不 import Capability internal model。
4. 必须使用正式 Artifact / Representation / Resource contract。
5. 明确 Composition DLC 自己拥有的 state。
6. 明确什么时候只需要 Agent orchestration，而什么时候真的需要 Composition DLC。
7. 如果普通 Agent composition 已足够完成需求，应拒绝增加多余的 Composition DLC。
8. 如果确实需要联合私有资源，则冻结明确 dependency contract。

实现：

- dependency contract
- composition tools
- artifacts
- representations
- Workbench contribution（如果需要）
- tests
- composition benchmark

必须测试：

- A 存在 / B 不存在
- B 存在 / A 不存在
- 两者存在
- resource stale
- one capability deactivated
- conflicting versions
- cancel
- partial failure
- restart
- large artifacts

完成后做 architecture boundary audit。
```

---

# 15. 创作任务生成器

每个 DLC 完成后，不要只跑固定测试。

Program Director 还要给它自动生成真实创作任务。

任务应：

* 复杂
* 多阶段
* 有修改过程
* 有局部返工
* 有用户改变主意
* 有直接操作与 Agent 操作混合

例如 Scene：

```text
创建一个漂浮在云层上的狐狸神殿。

要求：
- 六根柱子
- 中央蓝色水晶
- 两侧悬浮石块
- 一盏主光
- 两盏柔和辅光

完成后：

1. 删除左侧一半柱子
2. 水晶放大 30%
3. 主光降低 20%
4. 调整镜头
5. 新增第二层平台
6. 撤销其中一项需求
7. 用户手动移动一个物体
8. Agent 再继续修改
9. 导出
10. 最终检查 hierarchy
```

Game：

```text
创建一个狐狸躲避史莱姆的游戏。

随后：

1. 太难，降低史莱姆速度
2. 增加冲刺
3. 冲刺有 cooldown
4. 添加生命
5. 添加胜利条件
6. 改成 90 秒
7. 用户手动删除一个敌人
8. Agent 重新平衡
9. 连续 playtest
10. 最终输出设计说明
```

其他 DLC 自动按此模式构造任务。

---

# 16. Creative Benchmark

Program Director 最终建立一个新的高层 benchmark taxonomy。

不要只有每个 DLC 的局部 benchmark。

增加 Creative Composition Benchmark。

测量至少：

```text
creation correctness
incremental edit correctness
state preservation
user edit preservation
tool efficiency
recovery
stale edit rejection
cross-DLC composition
artifact correctness
context boundedness
```

尤其测试：

> Agent 是否在收到“改一点”时重建整个作品。

这应视为重要质量指标。

---

# 17. 专门建立 Regeneration Abuse 检查

对于所有 document-oriented creative DLC：

如果用户：

> 把这个物体向左移动一点。

Agent 却：

> 重新生成整个 SceneDocument。

这是架构和 Agent behavior 的失败。

设计 benchmark 来检测：

```text
local request
→ local operation
```

而不是：

```text
local request
→ document replacement
```

CAD / Scene / Pixel / Game / Comic / Animation 等都需要类似约束。

---

# 18. Creative Document Scale

每个 Lead 必须思考大型作品。

不能只测试：

* 3 个 object
* 4 个 panel
* 10 个 voxel
* 1 个 frame

需要主动考虑：

```text
Scene: thousands of objects
Game: hundreds of entities
Comic: hundreds of pages
Pixel: hundreds of frames
Voxel: millions of voxels
CAD: deep operation graph
Animation: thousands of keyframes
Map: thousands of features
```

模型 context 不能因此线性爆炸。

需要：

* search
* inspect
* bounded summaries
* region selection
* hierarchy
* pagination
* artifact-backed detail retrieval

---

# 19. 安全和资源约束

不得使用用户未授权的外部付费 API 来完成本 Program。

特别是：

不要因为当前会员 Agent 额度充足，就自行要求配置：

* OpenAI API
* Anthropic API
* 第三方生成服务 API
* 外部收费模型

本任务的主要计算应使用当前 Agent 环境本身。

如某 Creative DLC 将来支持第三方 provider，可设计 extension boundary，但不得因此阻断本地实现。

优先：

* deterministic local engines
* browser/runtime rendering
* open file formats
* local algorithms

---

# 20. 不允许的偷懒方式

禁止 Lead Agent 以以下结果宣布完成：

> 架构设计已经写好，后续可以实现。

不够。

> Backend 做好了，Frontend 后续。

不够。

> UI 目前先显示 JSON。

除非明确只是中间阶段，否则不够。

> 我添加了接口，实际没有完整操作。

不够。

> 测试还没写。

不够。

> 需要用户下一步确认。

除非真正遇到安全或不可逆要求，否则不要把工程决策推回用户。

---

# 21. Program Director 定期重新审计

每完成一个 Batch，都创建独立 Architecture Auditor Agent。

它不知道实现 Agent 的内部思路。

任务：

```text
假设 Creative DLC Program 正在逐渐腐蚀 DBFox Core。

从零审查这批修改。

专门寻找：

- domain leakage
- accidental shared mutable state
- hidden coupling
- wrong Resource boundaries
- internal DLC imports
- unstable dependency
- frontend state as authority
- compatibility layers
- duplicate execution paths
- shared abstractions prematurely moved to Core
- stale version handling bugs
- lifecycle ghosts
```

必须以代码证据为准。

---

# 22. 跨 DLC 共性抽象评审

当至少 4 个 Creative DLC 达到可工作状态后，创建：

`Creative Platform Pattern Auditor`

它不负责马上重构。

它只分析：

哪些模式真正重复？

例如：

* document versioning
* operation history
* direct manipulation handoff
* artifact representations
* undo semantics
* render lifecycle

然后将重复分为：

```text
A. Coincidental domain similarity
B. Reusable DLC-local library
C. Stable generic Host seam
D. Core runtime primitive
```

默认倾向 A/B。

只有证据很强才允许提出 C/D。

不要让 Creative Program 把 Core 变成“大而全创作框架”。

---

# 23. Branch / Integration 策略

如果 Git 功能可用：

每个 DLC 使用独立 branch/worktree：

```text
creative/scene
creative/game
creative/voxel
creative/shader
creative/pixel
creative/comic
creative/cad
creative/animation
...
```

Composition：

```text
composition/story-comic
composition/pixel-game
...
```

不要让多个 Lead 在同一 branch 无协调并行修改。

共享 Host seam 修改必须单独提交，并带：

* 为什么需要
* 哪些 DLC 证明它通用
* 为什么不能 DLC-local
* architecture review evidence

---

# 24. 每个 Agent 都必须留下机器可读状态

要求 Lead Agent 在适合的位置维护 Program status。

可以采用 JSON / YAML / Markdown + machine-readable section。

至少记录：

```text
dlc_id
status
branch
lead
canonical_model
resource_kinds
tools
artifacts
representations
frontend_views
tests
bench
architecture_review
known_blockers
composition_candidates
```

Program Director 据此决定下一步，而不是依赖聊天记忆。

---

# 25. Program 状态

统一状态：

```text
research
architecture
implementation
verification
red_team
integration_candidate
integrated
blocked
```

只有 Program Director 可以把 DLC 标记为：

```text
integrated
```

---

# 26. 不断循环

Program Director 的主循环：

```text
while creative_dlc_backlog exists:

    inspect program status

    identify independent work

    spawn Lead Agents

    each Lead:
        spawn specialist Agents
        design
        implement
        test
        red-team
        report

    collect reports

    reject incomplete DLCs

    integrate qualified DLCs

    run cross-DLC verification

    discover new composition opportunities

    spawn Composition Agents

    run architecture audit

    update roadmap

    start next wave
```

不要完成一个 DLC 就结束整个任务。

---

# 27. 第一阶段立即执行

现在立即执行：

## Phase A

先审查 repository 和现有 DLC。

输出内部 Program Map。

## Phase B

并行启动：

```text
dbfox.scene
dbfox.voxel
dbfox.shader
dbfox.pixel
```

每个都使用完整 DLC Lead Template。

## Phase C

当 Phase B 出现稳定结果后启动：

```text
dbfox.game
dbfox.comic
dbfox.cad
dbfox.animation
```

## Phase D

启动首批 Composition：

```text
dbfox.pixel-game
dbfox.scene-animation
dbfox.scene-game
dbfox.story-comic
```

## Phase E

继续 Wave 2：

```text
dbfox.map
dbfox.architecture
dbfox.poster
dbfox.typography
dbfox.sound
dbfox.simulation
dbfox.robot
dbfox.electronics
dbfox.lego
dbfox.creature
dbfox.recipe
dbfox.fashion
```

根据依赖允许继续分批并行。

---

# 28. 最终远景验证

当足够多 DLC 可工作后，创建一个专门的 **Creative World Integration Agent**。

给它一个终极任务：

> 创建一个完整的蒸汽朋克狐狸世界。

至少尝试组合：

```text
Story
Map
Creature
Scene
CAD
Music
Sound
Pixel
Comic
Animation
Game
Shader
```

要求它不绕过正式 Resource / Artifact / Representation / Tool boundaries。

最终验证：

> DBFox 是否真的可以在 Core 不理解任何这些领域语义的情况下，让一个 Agent 编排多种创作媒介完成复杂作品？

如果答案是否定的：

不要通过向 Core 添加领域知识来修。

找到缺少的通用 extension contract。

只有在多个真实 DLC 都证明需要该 contract 时，才提出最小 typed Host seam。

---

# 29. Program Director 的最终成功标准

不是 DLC 数量。

不是代码行数。

不是 Token 使用量。

成功标准是：

1. DBFox 获得多种真正不同的创作媒介。
2. 每种媒介有自己的 canonical durable model。
3. Agent 能通过结构化 Tool 增量编辑。
4. 用户也能直接编辑。
5. Agent 和用户共享唯一事实源。
6. 大型作品不会塞爆 Context。
7. 所有领域语义仍属于 DLC。
8. Capability 之间通过正式 Representation / Artifact 组合。
9. 真正需要联合资源的能力使用 Composition DLC。
10. Core 仍然是最小 Agent Runtime / lifecycle / authority / composition Host。
11. 新 DLC 有 deterministic verification。
12. 创意能力可以真正组合成复杂作品。

现在开始执行。

不要停在 roadmap。

不要只给我建议。

不要把子任务重新抛给我。

建立 Agent Tree，分发任务，开始实现，并持续进入下一波。

这个版本的关键点就是你说的“**不断套模板**”：总 Agent 不负责亲自做所有 DLC，而是创建 DLC Lead；DLC Lead 又继续按模板拆 Domain / Backend / Frontend / Verification / Red Team；完成后总 Agent再自动产生 Composition Agent。这样会形成一个比较大的 Agent 树。

而且我特意把你现有的 `story` 与 `visualization` 边界保住了：Story 已经是结构化世界事实/修订系统，而 Visualization 是受限 Vega/Vega-Lite 文档，不应该因为新 Creative DLC 出现就不断往它们里面塞职责。

如果你的 Agent 产品支持真正的多 Agent 并发，这个 Prompt 最适合直接作为**最高层总任务**扔进去。
