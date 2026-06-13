# Mascot v3 Replica Assets Design

## Goal

Create a new reusable mascot asset set by visually replicating the user-provided reference image. The work must not reuse, trace from, import, or depend on the existing mascot source assets already present in the repository. The output should feel like the reference board while producing clean product assets that can be used independently in the DataBox desktop UI.

## Deliverables

Create a new asset directory:

```text
desktop/src/assets/mascot-v3-replica/
```

The directory should contain:

- `app-icon.svg`: full app icon tile with the snow fox, purple AI sparkle, and DataBox tray.
- `rail-mark.svg`: compact mascot head mark for rail, favicon, or 16-32px usage.
- `empty-no-datasource.svg`: fox plus data box empty state.
- `agent-running.svg`: fox in an active/running state with cyan circular progress and violet sparkle accents.
- `empty-no-result.svg`: fox plus empty table/search-result state.
- `mascot-board.svg`: overview board that arranges the above assets in the same composition family as the reference image.
- `README.md`: short usage notes, recommended sizes, and color tokens.

Optional PNG export sizes may be generated after the SVG set is accepted:

- `app-icon-1024.png`
- `app-icon-512.png`
- `app-icon-256.png`
- `rail-mark-64.png`
- `rail-mark-32.png`
- `rail-mark-16.png`

## Visual Direction

The visual target is the supplied reference image:

- Soft ice-blue background.
- Large white rounded presentation board with subtle blue border and soft shadow.
- Clean product-logo quality, not a sticker or plush-toy style.
- White snow fox mascot with pointed ears, closed smiling eyes, small nose, and gentle mouth.
- Fox face should stay angular enough to read as a fox and avoid becoming pig-like or fully circular.
- Purple/violet AI sparkle near the fox.
- DataBox tray or box motif under the mascot.
- Cyan accent for active/running states.
- Light UI-panel details in the board preview, but individual assets should remain simple and readable.

## Color Tokens

Use the reference palette as the default:

| Token | Hex | Usage |
| --- | --- | --- |
| Snow White | `#FFFFFF` | Fox body, card surfaces, icon tile highlight |
| Ice Blue | `#EAF6FF` | Backgrounds, soft shadows, tile gradient |
| Soft Border | `#DDEAF8` | Card borders, UI dividers, table grid |
| AI Violet | `#7667F2` | Sparkle, DataBox tray stroke, AI accent |
| Data Cyan | `#55D4CF` | Running ring, active state accents |
| Text Dark | `#162033` | Board title and strong labels |
| Text Muted | `#7C8798` | Board captions and secondary labels |
| Fox Ink | `#2D2C2A` | Eyes, nose, mouth |

## Asset Requirements

### App Icon

- Square rounded tile.
- Uses a white-to-ice-blue gradient surface.
- Contains the full snow fox mascot in the DataBox tray.
- Includes a violet/cyan AI sparkle near the left side of the mascot.
- Must remain recognizable at 128px and visually balanced at 1024px.

### Rail Mark

- Compact head-only mark.
- Must still read as a fox at 16px.
- Remove unnecessary body, tray, and small decorative details if they reduce small-size clarity.
- Use simplified strokes and higher contrast than the full icon where needed.

### No Datasource

- Fox sits or looks toward a simple DataBox/database cube.
- Tone should communicate "connect a data source" without looking like an error.
- Keep the silhouette compact for empty-state placement.

### Agent Running

- Fox appears active, surrounded by a cyan progress ring.
- Include small violet sparkle details.
- Must be usable as a static SVG, with animation possible later through CSS or React if desired.

### No Result

- Fox appears calm and curious near an empty table/search-result panel.
- Avoid sad or failure-heavy expression.
- Should work in empty search results and query-result zero-state views.

### Overview Board

- Recreate the reference board composition:
  - title and subtitle at top,
  - app icon card on the left,
  - palette/product UI preview on the right,
  - four asset cards along the bottom,
  - key bar at the bottom.
- This board is for visual review and documentation, not as the primary app asset.

## Technical Constraints

- SVGs must be self-contained and should not reference existing repository SVG definitions.
- Prefer simple paths, gradients, masks, and reusable local groups inside each file.
- Avoid embedded raster images.
- Avoid JavaScript in SVG files.
- Use readable IDs scoped per SVG file to reduce collision risk if inlined.
- Keep files ASCII where practical.
- Do not edit the existing `docs/design/assets/databox-mascot-v3-premium-snow-fox-board.svg` asset.
- Do not depend on `desktop/src/pages/MascotPage.tsx` or its embedded SVG constants.

## Integration Scope

This task creates the asset files and documentation only. It does not replace existing UI references unless explicitly requested after asset review.

Recommended future integration points:

- Desktop app icon source.
- Sidebar rail brand mark.
- Empty datasource state.
- Agent running or analyzing state.
- Empty query result state.

## Verification

Verify the work by:

- Opening the generated board locally and comparing it against the reference image.
- Checking each individual SVG renders independently.
- Checking the rail mark at 16px, 24px, and 32px.
- Checking the app icon at 128px, 256px, and 512px.
- Running the frontend build if any app code changes are introduced later.

## Out Of Scope

- Replacing the real desktop application icon files.
- Refactoring existing mascot pages or docs.
- Creating Figma files.
- Creating animated React components.
- Pixel-perfect legal/design tracing. The target is a faithful product-quality recreation from the provided reference, not an exact extraction.
