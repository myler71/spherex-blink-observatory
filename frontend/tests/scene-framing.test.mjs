import test from 'node:test';
import assert from 'node:assert/strict';
import { getSceneFraming } from '../scene-framing.js';

// A sculpture's camera-space X divided by aspect determines its on-screen X.
// Fullscreen aspect changes must not move it out of its allocated visual side.
test('fullscreen and ultrawide views preserve the sculpture screen position', () => {
  const reference = 1440 / 900;
  for (const [width, height] of [[1920,1080], [3440,1440], [1080,1920], [1024,768]]) {
    const frame = getSceneFraming(width, height, false);
    const projectedCenter = 3.3 * frame.horizontalScale / (width / height);
    assert.ok(Math.abs(projectedCenter - 3.3 / reference) < 1e-12);
    assert.ok(frame.sculptureScale <= 1);
    assert.ok(frame.sculptureScale / (width / height) <= 1 / reference + 1e-12);
  }
});
test('mobile framing retains its own composition during orientation changes', () => {
  assert.deepEqual(getSceneFraming(390, 844, true), {horizontalScale:1, sculptureScale:1});
  const frame = getSceneFraming(700, 844, true);
  assert.ok(Math.abs(frame.horizontalScale - 700 / 390) < 1e-12);
  assert.equal(frame.sculptureScale, 1);
});
test('temporarily collapsed fullscreen surfaces have finite safe framing', () => {
  for (const value of [0, -1, NaN, Infinity]) {
    const frame = getSceneFraming(value, value, false);
    assert.ok(Number.isFinite(frame.horizontalScale) && frame.horizontalScale > 0);
    assert.ok(Number.isFinite(frame.sculptureScale) && frame.sculptureScale > 0);
  }
});
