// Poses were authored at these aspect ratios. Keep their camera-space X
// proportional to the viewport, and shrink only when its visual column narrows.
export function getSceneFraming(width, height, mobile) {
  const w = Number.isFinite(width) && width > 0 ? width : 1;
  const h = Number.isFinite(height) && height > 0 ? height : 1;
  const referenceAspect = mobile ? 390 / 844 : 1440 / 900;
  const horizontalScale = (w / h) / referenceAspect;
  return { horizontalScale, sculptureScale: Math.min(1, horizontalScale) };
}
