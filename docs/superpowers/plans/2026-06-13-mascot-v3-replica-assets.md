# Mascot v3 Replica Assets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a new reusable SVG asset pack that faithfully recreates the user-provided DataBox snow fox reference as independent product assets.

**Architecture:** The asset pack lives in a new self-contained directory under `desktop/src/assets/mascot-v3-replica/`. Each SVG is standalone, with local gradients and groups only, so assets can be copied into product UI without depending on existing mascot files. The overview board composes fresh local drawings that visually match the reference image and proves the individual assets work together.

**Tech Stack:** Standalone SVG, Markdown documentation, PowerShell/.NET XML parsing for validation.

---

### Task 1: Asset Directory And Usage Documentation

**Files:**
- Create: `desktop/src/assets/mascot-v3-replica/README.md`

- [ ] **Step 1: Create the asset directory**

Run:

```powershell
New-Item -ItemType Directory -Force -Path 'desktop\src\assets\mascot-v3-replica'
```

Expected: the directory exists and no existing mascot files are modified.

- [ ] **Step 2: Create README with asset usage rules**

Write `desktop/src/assets/mascot-v3-replica/README.md` with:

```markdown
# DataBox Mascot v3 Replica Assets

Fresh SVG asset pack recreated from the user-provided reference image. These files are intentionally independent from the earlier mascot concept files in `docs/design/assets`.

## Files

- `app-icon.svg`: rounded app icon tile with the fox, DataBox tray, and AI sparkle.
- `rail-mark.svg`: compact head-only mark for rail and favicon use.
- `empty-no-datasource.svg`: empty datasource state.
- `agent-running.svg`: active/running agent state with cyan progress ring.
- `empty-no-result.svg`: empty query/search result state.
- `mascot-board.svg`: overview board for visual review.

## Recommended Sizes

- App icon: 128px, 256px, 512px, 1024px.
- Rail mark: 16px, 24px, 32px, 64px.
- Empty states: 96px to 240px depending on layout density.
- Overview board: 1440px by 820px or larger.

## Color Tokens

- Snow White: `#FFFFFF`
- Ice Blue: `#EAF6FF`
- Soft Border: `#DDEAF8`
- AI Violet: `#7667F2`
- Data Cyan: `#55D4CF`
- Text Dark: `#162033`
- Text Muted: `#7C8798`
- Fox Ink: `#2D2C2A`

## Notes

The SVG files avoid external image references and JavaScript. They can be imported as static assets, copied into design tools, or inlined after checking ID collisions.
```

- [ ] **Step 3: Verify README exists**

Run:

```powershell
Test-Path 'desktop\src\assets\mascot-v3-replica\README.md'
```

Expected: `True`.

### Task 2: Core Standalone Mascot SVGs

**Files:**
- Create: `desktop/src/assets/mascot-v3-replica/app-icon.svg`
- Create: `desktop/src/assets/mascot-v3-replica/rail-mark.svg`

- [ ] **Step 1: Create `app-icon.svg`**

Implement a standalone `viewBox="0 0 512 512"` SVG:

- rounded tile background with white-to-ice-blue gradient,
- soft border and shadow filter,
- white angular fox head with pointed ears,
- closed smiling eyes, small nose, gentle mouth,
- violet DataBox tray under the fox,
- violet/cyan sparkle on the left side,
- all gradient/filter IDs prefixed with `replica-app-`.

- [ ] **Step 2: Create `rail-mark.svg`**

Implement a standalone `viewBox="0 0 128 128"` SVG:

- compact rounded tile,
- simplified fox head only,
- high-contrast ears, eyes, nose, and face outline,
- no tray and no tiny decorative elements that would blur at 16px,
- all gradient/filter IDs prefixed with `replica-rail-`.

- [ ] **Step 3: Validate the two SVG files parse as XML**

Run:

```powershell
[xml](Get-Content -Raw 'desktop\src\assets\mascot-v3-replica\app-icon.svg') | Out-Null
[xml](Get-Content -Raw 'desktop\src\assets\mascot-v3-replica\rail-mark.svg') | Out-Null
```

Expected: no XML parse errors.

### Task 3: State SVG Assets

**Files:**
- Create: `desktop/src/assets/mascot-v3-replica/empty-no-datasource.svg`
- Create: `desktop/src/assets/mascot-v3-replica/agent-running.svg`
- Create: `desktop/src/assets/mascot-v3-replica/empty-no-result.svg`

- [ ] **Step 1: Create `empty-no-datasource.svg`**

Implement a standalone `viewBox="0 0 240 180"` SVG:

- seated or compact fox facing a small data cube,
- calm expression,
- light datasource connection text/detail lines,
- violet cube strokes and ice-blue support shadows,
- IDs prefixed with `replica-datasource-`.

- [ ] **Step 2: Create `agent-running.svg`**

Implement a standalone `viewBox="0 0 240 180"` SVG:

- fox in an active pose,
- cyan circular progress ring behind or around the fox,
- small violet/cyan sparkles,
- static SVG only, with shape structure that can be animated later,
- IDs prefixed with `replica-running-`.

- [ ] **Step 3: Create `empty-no-result.svg`**

Implement a standalone `viewBox="0 0 240 180"` SVG:

- calm fox beside an empty result grid,
- small search/lightbulb cue,
- no sad or error-heavy expression,
- IDs prefixed with `replica-noresult-`.

- [ ] **Step 4: Validate state SVG files parse as XML**

Run:

```powershell
[xml](Get-Content -Raw 'desktop\src\assets\mascot-v3-replica\empty-no-datasource.svg') | Out-Null
[xml](Get-Content -Raw 'desktop\src\assets\mascot-v3-replica\agent-running.svg') | Out-Null
[xml](Get-Content -Raw 'desktop\src\assets\mascot-v3-replica\empty-no-result.svg') | Out-Null
```

Expected: no XML parse errors.

### Task 4: Overview Board

**Files:**
- Create: `desktop/src/assets/mascot-v3-replica/mascot-board.svg`

- [ ] **Step 1: Create `mascot-board.svg`**

Implement a standalone `viewBox="0 0 1440 820"` SVG that recreates the supplied board composition:

- ice-blue outer background,
- large rounded white board,
- title "DataBox Mascot v3 - Premium Snow Fox",
- subtitle "white, clean, cute but professional - less pig-like - more product-logo quality",
- left App Icon card,
- right product UI preview card with palette chips and a miniature app mock,
- bottom Asset Set row containing Rail Mark, No Datasource, Agent Running, and No Result cards,
- bottom key bar naming the visual traits.

- [ ] **Step 2: Validate overview board parses as XML**

Run:

```powershell
[xml](Get-Content -Raw 'desktop\src\assets\mascot-v3-replica\mascot-board.svg') | Out-Null
```

Expected: no XML parse errors.

### Task 5: Pack Verification

**Files:**
- Read: `desktop/src/assets/mascot-v3-replica/*.svg`
- Read: `desktop/src/assets/mascot-v3-replica/README.md`

- [ ] **Step 1: Confirm expected files exist**

Run:

```powershell
Get-ChildItem 'desktop\src\assets\mascot-v3-replica' | Select-Object Name, Length
```

Expected: the six SVG files and README are listed with non-zero lengths.

- [ ] **Step 2: Confirm no external raster or script references**

Run:

```powershell
rg "<script|href=\"https?:|xlink:href=\"https?:|\\.png|\\.jpg|\\.jpeg|\\.webp" desktop\src\assets\mascot-v3-replica
```

Expected: no matches.

- [ ] **Step 3: Confirm every SVG has the expected root dimensions**

Run:

```powershell
@(
  'app-icon.svg',
  'rail-mark.svg',
  'empty-no-datasource.svg',
  'agent-running.svg',
  'empty-no-result.svg',
  'mascot-board.svg'
) | ForEach-Object {
  $path = Join-Path 'desktop\src\assets\mascot-v3-replica' $_
  $svg = [xml](Get-Content -Raw $path)
  [PSCustomObject]@{
    Name = $_
    ViewBox = $svg.svg.viewBox
  }
}
```

Expected viewBoxes:

- `app-icon.svg`: `0 0 512 512`
- `rail-mark.svg`: `0 0 128 128`
- state assets: `0 0 240 180`
- `mascot-board.svg`: `0 0 1440 820`

- [ ] **Step 4: Review git diff**

Run:

```powershell
git diff -- desktop/src/assets/mascot-v3-replica docs/superpowers/plans/2026-06-13-mascot-v3-replica-assets.md
```

Expected: only the new plan and new asset pack files appear.
