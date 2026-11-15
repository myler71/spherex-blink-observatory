import test from 'node:test';
import assert from 'node:assert/strict';
import { getStoryState } from '../story-state.js';

const point = scene => ({ from: scene, to: scene, mix: 0, active: scene });
test('empty and single scene pages have stable endpoints', () => {
  assert.deepEqual(getStoryState([], 10), point('intro'));
  assert.deepEqual(getStoryState([{scene: 'narrator', centerY: 100}], 200), point('narrator'));
});
test('sparse overview scenes transition directly to comparison in either direction', () => {
  const a = [{scene:'telescope',centerY:100}, {scene:'compare',centerY:300}];
  assert.deepEqual(getStoryState(a, 0), point('telescope'));
  assert.deepEqual(getStoryState(a, 100), point('telescope'));
  assert.deepEqual(getStoryState(a, 150), {from:'telescope',to:'compare',mix:.25,active:'telescope'});
  assert.deepEqual(getStoryState(a, 200), {from:'telescope',to:'compare',mix:.5,active:'compare'});
  assert.deepEqual(getStoryState(a, 250), {from:'telescope',to:'compare',mix:.75,active:'compare'});
  assert.deepEqual(getStoryState(a, 300), point('compare'));
  assert.deepEqual(getStoryState(a, 400), point('compare'));
  assert.deepEqual(getStoryState(a, 150), {from:'telescope',to:'compare',mix:.25,active:'telescope'});
});
test('mission transitions directly to infrared', () => {
  const a = [{scene:'mission',centerY:40}, {scene:'infrared',centerY:140}];
  assert.deepEqual(getStoryState(a, 90), {from:'mission',to:'infrared',mix:.5,active:'infrared'});
});
