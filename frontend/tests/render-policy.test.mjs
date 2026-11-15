import test from 'node:test';
import assert from 'node:assert/strict';
import { getRenderProfile } from '../render-policy.js';

const profile = (quality, mobile, dpr, level) => getRenderProfile({ quality, mobile, dpr, level });
test('auto levels have exact desktop and mobile budgets', () => {
  assert.deepEqual(profile('auto', false, 3, 0), {pixelRatio:1.25,shadows:true,shadowSize:1024,starCount:1900});
  assert.deepEqual(profile('auto', true, 3, 0), {pixelRatio:1,shadows:true,shadowSize:1024,starCount:1900});
  assert.deepEqual(profile('auto', false, 3, 1), {pixelRatio:1,shadows:false,shadowSize:0,starCount:900});
  assert.deepEqual(profile('auto', true, 3, 1), {pixelRatio:.85,shadows:false,shadowSize:0,starCount:900});
  assert.deepEqual(profile('auto', false, 3, 2), {pixelRatio:.75,shadows:false,shadowSize:0,starCount:500});
  assert.deepEqual(profile('auto', true, 3, 2), {pixelRatio:.65,shadows:false,shadowSize:0,starCount:500});
});
test('manual settings and lower device DPR are respected', () => {
  assert.deepEqual(profile('high', false, 2, 2), {pixelRatio:1.5,shadows:true,shadowSize:2048,starCount:1900});
  assert.deepEqual(profile('high', true, 2, 2), {pixelRatio:1.25,shadows:true,shadowSize:2048,starCount:1900});
  assert.deepEqual(profile('efficient', true, .7, 0), {pixelRatio:.7,shadows:false,shadowSize:0,starCount:900});
});
test('invalid values and levels are clamped', () => {
  assert.deepEqual(profile('invalid', false, NaN, NaN), {pixelRatio:1,shadows:true,shadowSize:1024,starCount:1900});
  assert.deepEqual(profile('auto', false, 0, 9), {pixelRatio:.75,shadows:false,shadowSize:0,starCount:500});
  assert.deepEqual(profile('auto', false, 2, 1.9), {pixelRatio:1,shadows:false,shadowSize:0,starCount:900});
  assert.deepEqual(profile('auto', false, -1, -3), {pixelRatio:1,shadows:true,shadowSize:1024,starCount:1900});
});
