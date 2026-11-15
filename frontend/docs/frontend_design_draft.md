# ORVYX SPHEREx Blink Observatory — Frontend Design & Implementation Spec (Goldfish-Hardened)

* **Author:** Antigravity Execution Coordinator
* **Date:** 2026-11-15
* **Acceptance Reference:** `/home/myler71/Downloads/Gemini_Generated_Image_i80fa2i80fa2i80f.jpeg`
* **Source Prototype:** `/home/myler71/Downloads/orvyx_spherex_blink_observatory.tsx`
* **Target Workspace:** `/run/media/myler71/Daddy_s Home/Nasa/Latest ui/`

---

## 1. Overview & Architecture
Port the full 2D scientific observatory capabilities from `orvyx_spherex_blink_observatory.tsx` into pure, zero-build HTML/CSS/ES-module JavaScript inside `explorer.html`, `explorer.css`, and `explorer.js`, linked bidirectionally with `index.html`, while matching `/home/myler71/Downloads/Gemini_Generated_Image_i80fa2i80fa2i80f.jpeg` in visual hierarchy, palette, proportions, and controls.

```text
index.html (01: 3D Cinematic Landing)
   │  [Enter the experience -> #explorerDialog -> explorer.html]
   ▼
explorer.html (02: 2D SPHEREx Blink Observatory)
   ├── Background: Full-viewport SVG WCS Polar Grid (1440x900) + Left Edge Telemetry (06 —)
   ├── Tier 1 Micro-Bar: [▪ A NEW PERSPECTIVE ON THE UNIVERSE]           [• 01 (index.html)   02]
   ├── Tier 2 Main Header: [ORVYX▪] [RA // 133.79513] [DEC // -7.24515] [GO] | [5 Target Tabs] | [02 / 08]
   ├── Left Column (280px):
   │     ├── Card 1: HUB (shortClass H1 + Motion/Variability <input type="checkbox" switch>)
   │     ├── Card 2: MIDDLE / WISEVIEW RADIOMETRY (2 native range sliders + 41-tick rulers)
   │     └── Card 3: MULTI-AGENCY OVERLAYS (Master <input switch> + 3 colored toggle pills)
   ├── Center Column (minmax(0, 1fr)):
   │     ├── Dual Square Canvases (384x384 smooth FITS + #primaryOverlaySvg 96x96 WCS)
   │     ├── Timeline Dock (Epoch 01..04, default 03, blinking & display controls, Matrix & WiseView)
   │     └── Spectrum Bottom Dock (Glowing 0.75–5.00 µm range scrubber + 102-band SVG SED chart)
   └── Right Column (312px):
         ├── ORVYX / FIELD NOTE 06 ("THE UNIVERSE HAS A VOICE")
         ├── Quantitative Astrometric Summary (5 exact rows + 12x12 reticle SVG)
         ├── Grounded Narrative Chapters (scrollable, citation pills, click actions)
         └── BOTTOM Ask Input (Live backend /api/v1/observe/{id}/ask + deterministic fallback)
```

---

## 2. Exact File Boundary & Detailed Implementation Plan

### 2.1 Fonts & Theme Tokens (`explorer.css`)
Load existing WOFF2 font files from `assets/fonts/`:
- `assets/fonts/manrope.woff2` (`font-weight: 400`)
- `assets/fonts/manrope-semibold.woff2` (`font-weight: 600`)
- `assets/fonts/manrope-bold.woff2` (`font-weight: 800`)
- `assets/fonts/dm-sans.woff2` (`font-weight: 400`)
- `assets/fonts/dm-sans-medium.woff2` (`font-weight: 500 700`)

Define CSS tokens on `:root`:
- `--bg-void: #07090e;`
- `--card-bg: rgba(12, 16, 23, 0.84);`
- `--card-border: rgba(255, 255, 255, 0.12);`
- `--text-primary: #eef1f4;`
- `--text-muted: #939da9;`
- `--text-dim: #66707c;`
- `--amber: #e8a454;`
- `--amber-bright: #f8c67d;`
- `--amber-glow: rgba(240, 169, 78, 0.45);`
- `--cyan-line: #497896;`
- `--font-display: 'Manrope', system-ui, sans-serif;`
- `--font-sans: 'DM Sans', system-ui, sans-serif;`
- `--font-mono: ui-monospace, 'SFMono-Regular', Menlo, Monaco, Consolas, monospace;`
- Background radial nebula corner glows on `.observatory-shell`:
  `background: radial-gradient(circle at 12% 14%, rgba(42, 65, 98, 0.16), transparent 42%), radial-gradient(circle at 86% 88%, rgba(168, 102, 42, 0.12), transparent 45%), #07090e;`

### 2.2 Background WCS Reticle & Edge Telemetry (`explorer.html` + `explorer.css`)
1. `<svg class="wcs-backdrop" viewBox="0 0 1440 900" preserveAspectRatio="xMidYMid slice" aria-hidden="true">`:
   - Centered at `(720, 450)`:
   - Concentric circles at `r = 120, 210, 300, 390, 470` (`stroke="rgba(255,255,255,0.065)"`, `stroke-width="1"`), plus dotted tick ring at `r="390"` (`stroke-dasharray="2 10"`).
   - Full horizontal crosshair (`y=450, x1=120..1320`) and vertical crosshair (`x=720, y1=40..860`), plus center `+` marker (`x=712..728`, `y=442..458`, `stroke="rgba(255,255,255,0.22)"`).
   - Two subtle diagonal radial spokes (`45°` and `-45°`).
   - Labels (`fill="rgba(255,255,255,0.26)"`, `font-size="10"`, monospace):
     - `WCS` at `(720, 56)` (top), `(720, 306)` (between canvases), `(622, 616)` (lower-left arc)
     - `2808.01298` rotated `34deg` at `(956, 162)`
     - `170°` at `(342, 446)`
     - `90°` at `(1092, 446)`
     - `0007-05-15` at `(754, 622)`
     - `460` at `(948, 668)`
     - `100° • MILL TELS NATE 06` at `(756, 874)`
2. Left edge vertical scale `.edge-telemetry` (`position: fixed; left: 10px; top: 50%; transform: translateY(-50%)`):
   - Upper rotated micro-label: `118 0/00 900` (`writing-mode: vertical-rl; transform: rotate(180deg); font-size: 9px; color: rgba(255,255,255,0.25);`)
   - Horizontal tick readout aligned mid-height: `06 —` (`font-size: 10px; color: rgba(255,255,255,0.55);`)

### 2.3 Two-Tier Header (`explorer.html` + `explorer.css`)
1. **Tier 1 (`.top-micro-bar`)**:
   - Left: `<span class="amber-square" aria-hidden="true"></span><span>A NEW PERSPECTIVE ON THE UNIVERSE</span>`
   - Right: `<nav class="page-switch" aria-label="View switcher"><a href="index.html" class="page-step"><span class="amber-dot" aria-hidden="true"></span>01</a><span class="page-step is-current" aria-current="page">02</span></nav>`
2. **Tier 2 (`.main-header`)**:
   - Left brand + coordinates:
     - `<a href="index.html" class="orvyx-wordmark">ORVYX<span class="amber-pip" aria-hidden="true"></span></a>`
     - `<form id="coordForm" class="coord-form" novalidate>`:
       - `<label class="coord-field"><span>RA //</span><input id="raInput" name="ra" type="text" inputmode="decimal" value="133.79513" aria-label="Right Ascension in degrees"></label>`
       - `<label class="coord-field"><span>DEC //</span><input id="decInput" name="dec" type="text" inputmode="decimal" value="-7.24515" aria-label="Declination in degrees"></label>`
       - `<button id="coordGoBtn" type="submit" class="coord-go-btn" title="Query coordinates">GO</button>`
   - Center-right Target Tabs (`<nav class="target-tabs" aria-label="NASA challenge targets">`):
     - 5 buttons with `data-target`: `wise_0855` (`WISE 0855`, `aria-current="true"`, `.is-active`), `barnards_star` (`BARNARD'S STAR`), `epsilon_indi_b` (`EPSILON INDI B`), `rw_aurigae` (`RW AURIGAE`), `r_draconis` (`R DRACONIS`).
     - Active tab styling: color `#f4f5f7`, `border-bottom: 2px solid var(--amber)`, `box-shadow: 0 4px 12px -2px var(--amber-glow)`. Inactive tabs: `color: var(--text-muted)`, `border-bottom: 1px solid rgba(255,255,255,0.12)`.
   - Far right static view counter: `<div class="header-counter" aria-hidden="true"><strong>02</strong><span>/ 08</span></div>`

### 2.4 Main 3-Column Grid Layout (`explorer.css`)
- Desktop (`> 1180px`): `.observatory-grid { display: grid; grid-template-columns: 280px minmax(0, 1fr) 312px; gap: 22px; padding: 14px 26px 20px; align-items: start; max-width: 1600px; margin: 0 auto; }`
- Tablet (`<= 1180px`): `grid-template-columns: 260px minmax(0, 1fr);` with `.right-rail { grid-column: 1 / -1; }`
- Mobile (`<= 780px`): `grid-template-columns: 1fr; padding: 12px 14px 24px;` and `.dual-viewports { grid-template-columns: 1fr; }`, `.wcs-backdrop { opacity: 0.35; }`.

### 2.5 Left Rail (3 Cards: `HUB`, `MIDDLE`, `MULTI-AGENCY OVERLAYS`)
1. **Card 1 (`HUB`)**:
   - Label: `HUB`
   - `<h1 id="targetClassTitle" class="hub-title">Y4 SUB-BROWN DWARF</h1>`
   - Exact `shortClass` lookup per target:
     - `wise_0855`: `"Y4 SUB-BROWN DWARF"`
     - `barnards_star`: `"M4V RED DWARF"`
     - `epsilon_indi_b`: `"T1 + T6 BINARY BROWN DWARF"`
     - `rw_aurigae`: `"CLASSICAL T TAURI VARIABLE"`
     - `r_draconis`: `"MIRA PULSATING RED GIANT"`
     - `negative_control`: `"STATIC NEGATIVE CONTROL"`
     - custom RA/Dec: `"CUSTOM SKY CUTOUT"`
   - Mode Switch row (`<label class="mode-switch-row" for="modeSwitch">`):
     - Left text: `<span id="modeSwitchLabel"><em class="amber-dot"></em><span data-mode="motion" class="is-on">MOTION MODE</span> / <span data-mode="variability">VARIABLE MODE</span></span>`
     - Control: `<input id="modeSwitch" type="checkbox" switch class="ui-switch" aria-label="Toggle Variability Mode">`
     - Behavior: `checked === false` => `analysisMode = "motion"`; `checked === true` => `analysisMode = "variability"`. Switching targets syncs `modeSwitch.checked = (bundle.recommendedMode === "variability")`. Toggling updates `data-mode` span emphasis and highlights motion vectors (motion) or light-curve/SED diagnostics (variability).
2. **Card 2 (`MIDDLE` / `WISEVIEW RADIOMETRY`)**:
   - Labels: `MIDDLE`, `WISEVIEW RADIOMETRY`
   - Slider 1 (`<div class="radiometry-control">`):
     - Header row: `<label for="linearityRange">Linearity parameter (a)</label><output id="linearityValue" for="linearityRange">1.0</output>`
     - Native slider: `<input id="linearityRange" type="range" min="0.1" max="2.0" step="0.05" value="1.0" class="obs-range">`
     - Ruler: `<div class="tick-ruler" aria-hidden="true"></div>` (rendered with CSS repeating-linear-gradients: 41 minor vertical ticks 4px tall at `rgba(255,255,255,0.22)` and 9 major ticks 8px tall every 5th interval at `rgba(255,255,255,0.45)`).
   - Slider 2 (`<div class="radiometry-control">`):
     - Header row: `<label for="trimRange">Trim Bright Percentile (99.2%)</label><output id="trimValue" for="trimRange">99.3%</output>`
     - Native slider: `<input id="trimRange" type="range" min="90.0" max="99.9" step="0.1" value="99.3" class="obs-range">`
     - Ruler: `<div class="tick-ruler" aria-hidden="true"></div>`
   - Exact Modern Web Guidance Slider CSS:
     - Reset `appearance: none`, `background: transparent`, `block-size: 1.5rem`, `inline-size: 100%`.
     - Sync `--attr-min`, `--attr-max`, `--control-value` via JS on `input` + init, with `@supports not (opacity: progress(1, 0, 100))` fallback `calc((var(--control-value) - var(--attr-min)) / (var(--attr-max) - var(--attr-min)) * 100%)`.
     - Separate `::-webkit-slider-runnable-track`, `::-webkit-slider-thumb` (centered via `margin-block-start: calc((var(--slider-track-size) - var(--slider-thumb-size)) / 2)`), `::-moz-range-track`, `::-moz-range-progress`, and `::-moz-range-thumb` blocks (never comma-combined).
     - Visible `:focus-visible { outline: 2px solid var(--amber); outline-offset: 4px; }`.
3. **Card 3 (`MULTI-AGENCY OVERLAYS`)**:
   - Header row: `<label for="overlaysMasterSwitch">MULTI-AGENCY OVERLAYS</label><input id="overlaysMasterSwitch" type="checkbox" switch checked class="ui-switch">`
   - 3 interactive pill buttons in `.overlays-list`:
     - `<button type="button" class="overlay-pill overlay-pill--motion" data-layer="motion" aria-pressed="true"><span class="pill-dot"></span><span>SEP SUBPIXEL MOTION VECTORS</span></button>` (active border `#a46e38`, bg `rgba(92, 54, 22, 0.34)`)
     - `<button type="button" class="overlay-pill overlay-pill--gaia" data-layer="gaia" aria-pressed="true"><span class="pill-dot"></span><span>ESA GAIA DR3 EPOCH PROPAGATED</span></button>` (active border `#3d637d`, bg `rgba(22, 41, 56, 0.56)`)
     - `<button type="button" class="overlay-pill overlay-pill--neossat" data-layer="neossat" aria-pressed="true"><span class="pill-dot"></span><span>CSA / CADC NEOSSAT SURVEILLANCE</span></button>` (active border `#386475`, bg `rgba(18, 36, 46, 0.56)`)
   - State machine: Effective layer visibility is `effective[layer] = overlaysMasterSwitch.checked && pillPressed[layer]`. Toggling master OFF mutes SVG rendering and adds `.is-muted` to `.overlays-list` while preserving individual `aria-pressed` states; clicking any pill ON while master is OFF re-enables `overlaysMasterSwitch.checked = true`.
   - Switch CSS fallback: Feature-detect `'switch' in HTMLInputElement.prototype`; when `false` (Chrome/Firefox), add `.switch-fallback` on `input.ui-switch` using `appearance: none`, `width: 34px; height: 18px; border-radius: 999px; border: 1px solid rgba(255,255,255,0.28); background: rgba(255,255,255,0.08);` with `::before` sliding circular thumb (`12px`, `translateX(15px)` and amber accent when `:checked`).

### 2.6 Center Stage: Dual Canvases, Mathematical FITS Renderer & Overlays (`explorer.html`, `explorer.css`, `explorer.js`)
1. **Viewport Grid**:
   - `.dual-viewports { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; }`
   - When `displayMode !== "paired_wiseview"`, add `.dual-viewports--single` (`grid-template-columns: minmax(0, 440px); justify-content: center;`) and hide `#dipoleFrame`.
   - Both `.canvas-box` containers enforce `aspect-ratio: 1 / 1; position: relative; border: 1px solid rgba(255,255,255,0.14); background: #05070c;`.
   - `<canvas>` and `<svg>` inside `.canvas-box` use `display: block; width: 100%; height: 100%;`.
2. **Primary Canvas (`#primaryCanvas` 384×384) & Dipole Canvas (`#dipoleCanvas` 384×384) Exact Math**:
   - **Bilinear Sampler (`sampleBilinear(buf, w, h, cx, cy, outW=384, outH=384)`)**:
     - `gx = (cx / (outW - 1)) * (w - 1)`, `gy = (cy / (outH - 1)) * (h - 1)`
     - `x0 = Math.floor(gx)`, `y0 = Math.floor(gy)`, `x1 = Math.min(w - 1, x0 + 1)`, `y1 = Math.min(h - 1, y0 + 1)`
     - `tx = gx - x0`, `ty = gy - y0`
     - `val = (1 - tx) * (1 - ty) * buf[y0*w+x0] + tx * (1 - ty) * buf[y0*w+x1] + (1 - tx) * ty * buf[y1*w+x0] + tx * ty * buf[y1*w+x1]`
   - **Flags Overlay**: Nearest-neighbor sample `flagsMask[Math.round(gy) * w + Math.round(gx)] > 0`. When `showBitmaskFlags === true`, paint `#f43f5e` (`rgba(244, 63, 94)`). Raw `96×96` buffers remain unmodified for hover astrometry readout.
   - **Stretch Scale**: `const aScale = Math.max(linearityParam * 4.5, 0.45);`
   - **Primary Canvas Transfer Function**:
     - Compute `lowVal` (`2nd` percentile) and `highVal` (`trimBrightPct` percentile) from sorted stride-2 samples of the `96×96` buffer.
     - Add subtle sky micro-variation at render time: `skyMod = 0.45 * (Math.sin(gx * 0.22) * Math.cos(gy * 0.19) + Math.sin((gx + gy) * 0.11))`.
     - `norm = Math.max(0, Math.min(1, ((val + skyMod) - lowVal) / Math.max(highVal - lowVal, 1e-5)))`
     - `stretched = Math.asinh(norm * aScale) / Math.asinh(aScale)`
     - If `invertPixels`: `lum = Math.floor((1 - stretched) * 255)` -> `rgb(lum, lum, lum)`.
     - Else: compute `nirRatio = Math.max(0, Math.min(1, (scrubWavelengthUm - 0.75) / 4.25))` and proximity weight `warmMix = Math.exp(-((gx - targetX)**2 + (gy - targetY)**2) / 140)` around primary target `(targetX, targetY)` so the primary target shines warm amber-gold while distant Gaia field stars remain crisp cool blue-white:
       - `lum = stretched * 255`
       - `r = Math.min(255, Math.floor(8 + lum * (0.86 + (0.28 * warmMix + 0.14 * nirRatio))))`
       - `g = Math.min(255, Math.floor(10 + lum * (0.90 + (0.04 * warmMix - 0.06 * nirRatio))))`
       - `b = Math.min(255, Math.floor(17 + lum * (1.08 - (0.58 * warmMix + 0.24 * nirRatio))))`
   - **Dipole Difference Image (`#dipoleCanvas` 384×384) Exact Transfer Function**:
     - Underlying buffer `diffBuf` (`I_n - I_ref`, or `I_0 - 0.96 * I_1` on Epoch 1) plus a subtle physical astrometric-PSF cross-quadrupole residual `(0.42 * peak * exp(-r^2/(2*sigma^2)) * sin(2*theta))` when `displayMode !== "coadd_stack"` and target has proper motion (`dx != 0 || dy != 0`), yielding the crisp 4-lobe indigo/amber dipole-quadrupole signature at the shifted core as shown in `Gemini_Generated_Image_i80fa2i80fa2i80f.jpeg`.
     - Smooth multi-octave background cloud modulation at render time:
       `cloud = (Math.sin(gx * 0.15 + 0.5) * Math.cos(gy * 0.13 - 0.4) + 0.55 * Math.sin((gx - gy) * 0.23)) * 0.06`
     - `norm = Math.max(-1, Math.min(1, (invertPixels ? -val : val) / maxAbs + cloud))`
     - `t = Math.asinh(Math.abs(norm) * aScale) / Math.asinh(aScale)`
     - Piecewise Indigo-Amber Diverging Palette (`base = [25, 40, 104]` `#192868`):
       - If `norm >= 0`:
         - `t <= 0.45`: lerp `[25, 40, 104]` -> `[168, 74, 30]` (`u = t / 0.45`)
         - `0.45 < t <= 0.80`: lerp `[168, 74, 30]` -> `[245, 166, 56]` (`u = (t - 0.45) / 0.35`)
         - `t > 0.80`: lerp `[245, 166, 56]` -> `[255, 243, 207]` (`u = (t - 0.80) / 0.20`)
       - If `norm < 0`:
         - lerp `[25, 40, 104]` -> `[5, 7, 18]` (`u = Math.min(1, t * 1.15)`)
   - Headers:
     - Left frame: `PRIMARY BLINK CANVAS (EPOCH <span id="primaryEpochNum">03</span> / <span id="primaryEpochDate">2026-05-15</span>)`
     - Right frame: `DIPOLE DIFFERENCE IMAGE (<span id="diffLabel">I₃ − I_REF</span>)` where `#diffLabel` is `I₁ − I₂` (epoch 0), `I₂ − I_REF` (epoch 1), `I₃ − I_REF` (epoch 2), `I₄ − I_REF` (epoch 3).
3. **`#primaryOverlaySvg` (`viewBox="0 0 96 96"`) Exact Geometry**:
   - Fine `24×24` grid lines (`step=4`, `stroke="rgba(255,255,255,0.06)"`, `stroke-width="0.22"`).
   - Warm aperture glow circle (`cx="48" cy="48" r="40"`, `fill="url(#apertureGlow)"`, `stroke="rgba(232,164,84,0.68)"`, `stroke-width="0.38"`).
   - Inscribed square (`x="19.7" y="19.7" width="56.6" height="56.6"`, `stroke="rgba(255,255,255,0.58)"`, `stroke-width="0.32"`).
   - Cardinal markers: `"0.1"` at `(48, 5.5)`, `"0"` at `(6.2, 48.8)`, `"0"` at `(89.8, 48.8)`, `"↑"` at `(48, 92.2)`.
   - Lower-left inset coordinate box (`x=22.5, y=58, w=16, h=16`, `4×4` inner grid `step=4`, white star at `(34.5, 62)`, diagonal arrow `(24.5, 72) -> (35.5, 61)`).
   - `#sourcesLayer`:
     - Active target (`src[0]`): amber reticle (`r="4.0"`, `stroke="#f5a638"` or `#c084fc` if variable), name label (`x=cx+5.2, y=cy-0.5`, e.g. `WISE 0855`, `font-size="3.0"`, `fill="#f3c583"`), breadcrumb dots + proper-motion vector arrow when `effective.motion && isCandidateMoving`.
     - Field stars (`src[1..4]`): cyan-slate square (`4.4×4.4`, `stroke="#4ea8d8"`) when `effective.gaia && !isGaiaOpticalDropout`, reticle circle (`r="2.2"`), plus small motion arrow indicators.
     - NEOSSat surveillance dashed border (`x=7, y=7, width=82, height=82`, `stroke="#3aa69b"`, `stroke-dasharray="2,2"`) when `effective.neossat`.
   - `#hoverTelemetryBar`: positioned at bottom of Primary Canvas, hidden (`opacity: 0`) at rest, visible (`opacity: 1`) on pointer move with `PX(x,y) • RA ...° DEC ...° • ... MJy/sr`.
4. **Timeline Dock (`.timeline-dock`)**:
   - Top row: `TIMELINE (BELOW CANVASES)` on left; compact `.timeline-controls` cluster on right:
     - `#blinkPlayBtn` (`▶ BLINK` / `❚❚ PAUSE`, toggles `550ms` interval; default `false` on load)
     - `#prevEpochBtn` (`‹`) & `#nextEpochBtn` (`›`)
     - `#displayModeBtn` (`PAIRED` -> `BLINK` -> `DIPOLE` -> `CO-ADD`)
     - `#detectorSwitcher` (`D1`–`D6` buttons, `hidden` unless `displayMode === "coadd_stack"`)
     - `#invertBtn` (`INVERT`), `#flagsBtn` (`FLAGS`), `<button type="button" command="show-modal" commandfor="benchmarksDialog" id="matrixBtn">MATRIX</button>`, `<a id="wiseviewLink" target="_blank" rel="noopener noreferrer">WISEVIEW ↗</a>`
   - Track row: horizontal base line (`rgba(255,255,255,0.16)`), endpoint circle (left) & arrowhead (right), `#timelineArrow` (`left: 4%`, `width: (epochIdx / 3) * 92%`, glowing amber line + arrowhead), 4 `<button class="epoch-node" data-epoch="0..3">` buttons (`01`, `02`, `03`, `04`) with flanking bars `::before`/`::after` on active node, and `#timelineCaption` (`OBSERVATION 03`).
5. **Spectrum Bottom Dock (`.spectrum-dock`)**:
   - Header: `SPECTRUM (BOTTOM DOCK)`
   - Left `.spectrum-bar-panel`:
     - Native `<input id="wavelengthRange" type="range" min="0.75" max="5.00" step="0.01" value="5.00" class="spectrum-range" aria-label="LVF Wavelength Scrubber in micrometers">` styled with full-width dark chamber, central glowing warm-amber-to-white horizontal beam (`linear-gradient(90deg, rgba(255,255,255,0.22), #b96e2c 48%, #f8c67d 85%, #ffffff 100%)`), and glowing white circular thumb (`10px`, `box-shadow: 0 0 14px 3px rgba(255,235,190,0.95)`).
     - Footer labels: `0.75 µm — 5.00 µm` (left) and `<output id="wavelengthValue" for="wavelengthRange">5.00 µm</output>` (right).
   - Right `.spectrum-plot-panel`:
     - `<svg id="sedChartSvg" viewBox="0 0 220 72" aria-label="102-channel SPHEREx spectral energy distribution">` with fine grid (`dx=11, dy=12`), `102` channels (`0.75..5.00 µm`) normalized dynamically to `maxFlux * 1.15`, warm amber area gradient fill, glowing `#f3be7a` `<path>`, and vertical cursor line at `x = 8 + ((scrubWavelengthUm - 0.75) / 4.25) * 204`.

### 2.7 Right Rail: Field Note 06, Quantitative Summary, Chapters, Ask (`explorer.html`, `explorer.js`)
1. Header: `ORVYX / FIELD NOTE 06` and `<h2>THE UNIVERSE HAS A VOICE</h2>`.
2. **Quantitative Astrometric Summary**:
   - Label: `QUANTITATIVE ASTROMETRIC SUMMARY`
   - Split 2-column grid (`.summary-split`):
     - Left `#astrometricSummaryTable`:
       - Title: `<div class="summary-target-name" id="summarySourceName">WISE 0855</div>`
       - 5 exact data rows:
         1. `RA //` -> `${src.raDeg.toFixed(5)}°`
         2. `DEC //` -> `${src.decDeg.toFixed(5)}°`
         3. `PM (µ)` -> `${src.totalPmArcsecYr.toFixed(2)} "/yr`
         4. `SNR //` -> `${src.snr.toFixed(1)} σ`
         5. `GAIA` -> `src.isGaiaOpticalDropout ? "IR DROPOUT" : (src.gaiaDr3Id ? "DR3 LOCKED" : "UNMATCHED")`
     - Right `.summary-reticle-box`: `<svg viewBox="0 0 120 120">` with `12×12` grid (`step=10`), central axis hairlines, and glowing warm radial star point at `(60, 60)`.
3. **Narrative Chapters (`#narratorChaptersList`)**:
   - Scrollable region (`max-height: 290px; overflow-y: auto; scrollbar-gutter: stable; overscroll-behavior: contain;`).
   - For `wise_0855`, render the 2 signature chapters first (`CHAPTER 02 // A UNIVERSE IN MOTION` with `[ESA GAIA DR3]` pill, and `CHAPTER 03 // WHY GAIA DR3 SEES NOTHING HERE` with `[ESA GAIA DR3]` and `[NASA ADS]` pills, plus `CHAPTER 01 // WHERE ARE YOU LOOKING?` below or integrated cleanly), and render target-specific grounded chapters for every preset/custom patch.
   - Clicking a chapter selects `ch.linkedObjectId` and executes `ch.actionType` (`focus_motion` -> motion mode + paired blink, `inspect_dipole` -> paired dipole mode, `inspect_lightcurve` -> variability mode, `inspect_spectrum` -> sets `#wavelengthRange` to target's `peakUm` + triggers input update).
4. **BOTTOM Ask Input**:
   - Label: `BOTTOM`
   - `<form id="askPatchForm" class="ask-form">` with `<input id="askPatchInput" type="text" placeholder="ASK ABOUT THIS SKY PATCH USING RETRIEVED EVIDENCE" aria-label="Ask about this sky patch">` and inline magnifying-glass submit button `<button id="askPatchSubmit" type="submit" aria-label="Submit question">...</button>`.
   - Dismissible `#askPatchResponse` box below (`hidden` until asked, with close button `×`).

### 2.8 Benchmarks Dialog & Live Backend Integration (`explorer.html`, `explorer.js`)
1. **`#benchmarksDialog`**:
   - `<dialog id="benchmarksDialog" closedby="any" aria-labelledby="benchmarksTitle">`
   - Closed via `<button type="button" command="close" commandfor="benchmarksDialog">Close ✕</button>` + `dialog:modal { overscroll-behavior: contain; }` + `dialog::backdrop { overflow: hidden; overscroll-behavior: contain; }` + feature-detected `closedBy` and `commandForElement` fallbacks in `explorer.js`.
   - Table includes all 5 NASA Challenge Targets PLUS 6th row `NEGATIVE_CONTROL_BUNDLE` (`Gaia DR3 720517945437337600`, `raDeg: 134.84582`, `decDeg: 40.99470`, `totalPmArcsecYr: 0.002`, `variabilityChi2: 0.92`, `isGaiaOpticalDropout: false`), each with an `Inspect →` button that loads that bundle into the observatory and closes the dialog.
2. **Backend HTTP Integration (`http://127.0.0.1:8000/api/v1`)**:
   - `fetchBackendObservation(raDeg, decDeg, fovDeg, targetKey)` uses `AbortController` (`4000ms` timeout) calling `GET /api/v1/observe?ra=...&dec=...&fov=...&max_frames=4&propagate=true`. If HTTP 200 returns `observation_id`, stores `state.liveObservationId`, optionally decodes `<f4`/`<u1` base64 arrays if `frames.length >= 2`, and logs backend availability without blocking initial render.
   - `handleAskPatch` sends `POST /api/v1/observe/${encodeURIComponent(state.liveObservationId)}/ask` with `{ question }` (`4000ms` timeout) when a live `observation_id` exists; if unavailable/offline/404, immediately produces TSX's deterministic grounded evidence synthesis using `selectedSource` astrometry and catalog provenance.
3. **URL Query Param State**:
   - Precedence on load: `?target=` preset key > `?ra=` & `?dec=` custom coords > default `wise_0855`. `?epoch=1..4` (1-based) defaults to `3` (`epochIdx = 2`). Updates URL via `history.replaceState` and handles `popstate`.

### 2.9 Landing Page Link Update (`index.html`)
- Keep `#explorerDialog` modal wiring intact in `app.js`, updating `#explorerDialog` inside `/run/media/myler71/Daddy_s Home/Nasa/Latest ui/index.html`:
  - Eyebrow: `LIVE SCIENTIFIC OBSERVATORY`
  - Heading: `The next<br><em>perspective.</em>`
  - Body: `Launch the ORVYX 2D SPHEREx Blink Observatory to inspect all five NASA challenge targets, stretch WiseView asinh radiometry, compare multi-epoch dipole difference frames, and query the Cosmic Narrator.`
  - Note: `<i></i> Interactive 2D SPHEREx Blink Workspace ready.`
  - CTA Link: `<a class="button button-light" href="explorer.html">Open 2D Blink Observatory <svg class="icon"><use href="#i-arrow"/></svg></a>`
