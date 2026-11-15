# ORVYX — Cinematic 3D landing experience

A self-contained Three.js concept landing page inspired by the way SPHEREx observes beyond visible light. It uses a supplied artistic telescope model with procedural scene elements, scroll-choreographed camera transitions, and a clearly labelled Cosmic Narrator prototype.

## Run locally

```bash
python3 -m http.server 4173 --bind 0.0.0.0
```

Run this command from `frontend/`, then open `http://localhost:4173`. Use HTTP, not a double-clicked `file://` HTML document: native JavaScript modules and GLB loading require an HTTP origin in a normal browser.

## Visual direction

- Real-time 3D telescope, atmosphere, spectrum sphere, observation plates, and narrator sculpture — not an image slideshow.
- The landing opens on the illustrative telescope image, then dissolves into the live 3D telescope as the user scrolls.
- The **Orbital Noir** background is an original local asset made for this project: a muted, abstract lunar-scale optical field with subtle registration marks and aperture arcs. Its full-bleed, high-contrast photographic composition and sparse editorial UI take *stylistic* inspiration from the Oakley × Axiom Space page; no Oakley imagery, wording, or layout is reproduced.
- Background texture shifts gently with the scroll position and is paired with a low-motion optical overlay. Reduced-motion preferences disable the ambient sweep.

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
- `assets/orbital-noir.webp` / `assets/orbital-noir-mobile.webp` — current desktop/mobile background treatment

## Stable visuals and coordinate workspace

The previous GPU post-processing chain has been removed to avoid bloom-related black frames. The slider now adjusts a decorative CSS ambient glow over the directly rendered 3D scene; it is not scientific image processing. Open the coordinate workspace from the explorer dialog: it validates ICRS decimal degrees, offers the official WISE 0855 example, and creates shareable URLs. It does not query IRSA automatically; the displayed starfield is illustrative.
