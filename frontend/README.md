# ORVYX — Cinematic 3D landing experience

A self-contained four-page Three.js experience inspired by SPHEREx: Overview, Mission & Optics, Cosmic Narrator, and the separate scientific 2D Blink Observatory.

## Run locally

```bash
python3 -m http.server 4173 --bind 0.0.0.0
```

Run this command from `frontend/`, then open `http://localhost:4173`. Use HTTP, not a double-clicked `file://` HTML document: native JavaScript modules and GLB loading require an HTTP origin in a normal browser.

## Visual direction

- Real-time 3D telescope, atmosphere, spectrum sphere, observation plates, and narrator sculpture — not an image slideshow.
- The Overview opens on an illustrative introduction, then dissolves into the supplied live telescope as the user scrolls. Named scene anchors transition directly between sculptures present on each page.
- The **Orbital Noir** background is an original local asset made for this project: a muted, abstract lunar-scale optical field with subtle registration marks and aperture arcs. Its full-bleed, high-contrast photographic composition and sparse editorial UI take *stylistic* inspiration from the Oakley × Axiom Space page; no Oakley imagery, wording, or layout is reproduced.
- Background texture drifts subtly with ambient motion. Reduced-motion preferences and the Cinematic view panel pause ambient animation without disabling scrolling, manual orbit, or scientific controls.

## Important scope notes

- The background, stars, planet, ribbons, narrator, and all graphics are illustrative — they are not scientific observations.
- The supplied telescope GLB is an artistic asset, not an official NASA engineering model.
- The Cosmic Narrator accepts an observation ID and asks the local backend at `http://127.0.0.1:8000` using its retrieved observation evidence. The backend must be running and configured with an LLM provider; its response can also be a deterministic evidence-based answer.
- The page does not claim to discover Planet X.

## Main files

- `index.html` — semantic landing-page structure and dialogs
- `style.css` — responsive editorial styling, motion, and fallback art direction
- `app.js` — accessibility controls, visual-panel settings, scroll chapter state, opening dissolve
- `scene.js` — Three.js render scene, GLB loading, background drift, and scroll choreography
- `story-state.js` — pure, named-scene interpolation between measured section centers
- `scene-framing.js` — aspect-aware camera-space placement for fullscreen, portrait, and ultrawide surfaces
- `render-policy.js` — desktop/mobile quality budgets and bounded Auto degradation
- `visual-theme.css` — shared chrome tokens and progressive cross-document transitions
- `assets/orbital-noir.webp` / `assets/orbital-noir-mobile.webp` — current desktop/mobile background treatment

## Stable visuals and coordinate workspace

The previous GPU post-processing chain has been removed to avoid bloom-related black frames. The slider adjusts a decorative CSS ambient glow over the directly rendered 3D scene; it is not scientific image processing. The separate 2D Observatory retains its original radiometry, dipole canvases, SED plot, and API behavior.
