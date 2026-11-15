export function getRenderProfile({ quality, mobile, dpr, level }) {
  quality = ['auto', 'high', 'efficient'].includes(quality) ? quality : 'auto';
  dpr = Number.isFinite(dpr) && dpr > 0 ? dpr : 1;
  level = Number.isFinite(level) ? Math.max(0, Math.min(2, Math.floor(level))) : 0;
  const tier = quality === 'high' ? -1 : quality === 'efficient' ? 1 : level;
  const cap = tier === -1 ? (mobile ? 1.25 : 1.5)
    : tier === 0 ? (mobile ? 1 : 1.25)
    : tier === 1 ? (mobile ? .85 : 1)
    : (mobile ? .65 : .75);
  const shadowSize = tier === -1 ? 2048 : tier === 0 ? 1024 : 0;
  return { pixelRatio: Math.min(dpr, cap), shadows: shadowSize > 0, shadowSize, starCount: tier <= 0 ? 1900 : tier === 1 ? 900 : 500 };
}
