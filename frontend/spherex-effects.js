// Stable renderer: the original 3D frame is drawn directly, never through
// bloom framebuffers. A lightweight CSS light layer provides the visual glow.
export function createSpherexEffects(renderer, scene, camera, initialSettings = {}) {
  let settings = {};
  const glow = document.querySelector('#safeBloom');
  function setSettings(next) {
    settings = { ...settings, ...next };
    const enabled = settings.enabled !== false;
    const bloom = Math.max(0, Math.min(100, Number(settings.bloom) || 0));
    // CSS compositing is deliberately independent of the WebGL color buffer.
    if (glow) glow.style.opacity = enabled ? String(bloom / 100 * .22) : '0';
  }
  function resize() { /* Renderer size is managed by the scene. */ }
  function render() {
    renderer.setRenderTarget(null);
    renderer.render(scene, camera);
  }
  setSettings(initialSettings);
  return { setSettings, resize, render, dispose() { if (glow) glow.style.opacity = '0'; } };
}
