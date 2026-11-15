export function getStoryState(anchors, viewportCenterY) {
  const endpoint = scene => ({ from: scene, to: scene, mix: 0, active: scene });
  if (!anchors.length) return endpoint('intro');
  if (viewportCenterY <= anchors[0].centerY) return endpoint(anchors[0].scene);
  const last = anchors[anchors.length - 1];
  if (viewportCenterY >= last.centerY) return endpoint(last.scene);
  for (let i = 0; i < anchors.length - 1; i++) {
    const a = anchors[i], b = anchors[i + 1];
    if (viewportCenterY === b.centerY) return endpoint(b.scene);
    if (viewportCenterY < b.centerY) {
      const mix = Math.max(0, Math.min(1, (viewportCenterY - a.centerY) / (b.centerY - a.centerY)));
      return { from: a.scene, to: b.scene, mix, active: mix < .5 ? a.scene : b.scene };
    }
  }
  return endpoint(last.scene);
}
