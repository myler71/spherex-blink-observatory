import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { createSpherexEffects } from './spherex-effects.js?v=cinematic-4';
import { getRenderProfile } from './render-policy.js';
import { getSceneFraming } from './scene-framing.js';

function initScene() {
const canvas = document.querySelector('#scene');
const stage = canvas.parentElement;
const ready = (webgl, model = false) => window.dispatchEvent(new CustomEvent('orvyx:ready', { detail: { webgl, model } }));
let renderer;
try {
  renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false, powerPreference: 'high-performance' });
} catch (error) {
  console.warn('ORVYX: real-time 3D is unavailable in this browser.', error);
  ready(false);
}

if (renderer) {
  let settings = { enabled: true, bloom: 40, grain: 30, quality: 'auto', motion: !matchMedia('(prefers-reduced-motion: reduce)').matches, ...window.ORVYX_SETTINGS };
  const gl = renderer.getContext();
  const debugRenderer = gl.getExtension('WEBGL_debug_renderer_info');
  const softwareRenderer = Boolean(debugRenderer && /swiftshader|llvmpipe|software/i.test(gl.getParameter(debugRenderer.UNMASKED_RENDERER_WEBGL)));
  let qualityLevel = softwareRenderer ? 1 : 0;
  const effectiveSettings = () => settings;
  let dirty = true, sceneAnnounced = false, announcedModelState = '', failedModel = false;
  let frameRequest = 0, sceneVisible = true, pageHidden = false, contextLost = false, disposed = false;
  let mobile = innerWidth <= 700;
  let viewportWidth = Math.max(1, stage.clientWidth), viewportHeight = Math.max(1, stage.clientHeight);
  let framing = getSceneFraming(viewportWidth, viewportHeight, mobile);
  const profile = () => getRenderProfile({ quality: settings.quality, mobile, dpr: devicePixelRatio, level: qualityLevel });
  let currentProfile = profile();
  const pixelRatio = () => currentProfile.pixelRatio;
  renderer.setPixelRatio(pixelRatio());
  renderer.setSize(viewportWidth, viewportHeight, false);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = .94;
  renderer.shadowMap.enabled = currentProfile.shadows;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x05090f);
  const camera = new THREE.PerspectiveCamera(35, viewportWidth / viewportHeight, .1, 220);
  camera.position.set(0, .65, 16);
  camera.lookAt(.35, .1, 0);
  const loadingManager = new THREE.LoadingManager();
  loadingManager.onLoad = invalidate;
  loadingManager.onProgress = invalidate;
  const loader = new THREE.TextureLoader(loadingManager);
  const anisotropy = Math.min(8, renderer.capabilities.getMaxAnisotropy());
  function sizeBackground() {
    const background = scene.background;
    if (!background.isTexture || !background.image) return;
    const imageAspect = background.image.width / background.image.height, aspect = viewportWidth / viewportHeight;
    if (aspect < imageAspect) { background.repeat.set(aspect / imageAspect, 1); background.offset.set((1 - background.repeat.x) / 2, 0); }
    else { background.repeat.set(1, imageAspect / aspect); background.offset.set(0, (1 - background.repeat.y) / 2); }
    background.repeat.multiplyScalar(.94);
    background.offset.set((1 - background.repeat.x) / 2, (1 - background.repeat.y) / 2);
    background.updateMatrix();
  }
  const backgroundAsset = mobile ? './assets/orbital-noir-mobile.webp' : './assets/orbital-noir.webp';
  loader.load(backgroundAsset, texture => { texture.colorSpace = THREE.SRGBColorSpace; texture.matrixAutoUpdate = true; scene.background = texture; scene.backgroundIntensity = 1.08; sizeBackground(); invalidate(); });

  // Soft HDR reflections keep the insulation and metal dimensional, without
  // painting fake highlights into the model's textures.
  const environment = new THREE.Scene();
  environment.background = new THREE.Color(.035, .045, .065);
  function reflectionCard(width, height, position, radiance) {
    const card = new THREE.Mesh(new THREE.PlaneGeometry(width, height), new THREE.MeshBasicMaterial({ color: new THREE.Color(...radiance), side: THREE.DoubleSide }));
    card.position.fromArray(position); card.lookAt(0, 0, 0); environment.add(card);
  }
  reflectionCard(6, 11, [-8, 7, 9], [6.5, 6.0, 5.3]);
  reflectionCard(2, 10, [8, 3, -5], [2.8, 2.1, 1.5]);
  reflectionCard(9, 3, [0, -7, 3], [.35, .55, .9]);
  const pmrem = new THREE.PMREMGenerator(renderer);
  const environmentTarget = pmrem.fromScene(environment, .045);
  scene.environment = environmentTarget.texture;
  scene.environmentIntensity = .85;
  environment.traverse(obj => { if (obj.isMesh) { obj.geometry.dispose(); obj.material.dispose(); } });
  pmrem.dispose();
  const key = new THREE.DirectionalLight(0xfff3e3, 2.2);
  key.position.set(-5, 9, 9);
  key.castShadow = true;
  key.shadow.mapSize.set(currentProfile.shadowSize || 1024, currentProfile.shadowSize || 1024);
  Object.assign(key.shadow.camera, { left: -8, right: 8, top: 8, bottom: -8, near: .5, far: 38 });
  key.shadow.camera.updateProjectionMatrix();
  key.shadow.bias = -.00015;
  key.shadow.normalBias = .018;
  key.shadow.radius = 3;
  scene.add(key);
  const rim = new THREE.DirectionalLight(0xffcf9b, 2.8);
  rim.position.set(8, 6, -5); scene.add(rim);
  const fill = new THREE.DirectionalLight(0x7c9fcf, .5);
  fill.position.set(8, -2, 6); scene.add(fill);
  const earthBounce = new THREE.HemisphereLight(0x657fa6, 0x5d4032, .3); scene.add(earthBounce);

  let seed = 170;
  function random() { seed = (seed * 16807) % 2147483647; return (seed - 1) / 2147483646; }
  function canvasTexture(width, height, draw, color = false) {
    const c = document.createElement('canvas'); c.width = width; c.height = height;
    draw(c.getContext('2d'), width, height);
    const texture = new THREE.CanvasTexture(c);
    texture.colorSpace = color ? THREE.SRGBColorSpace : THREE.NoColorSpace;
    texture.anisotropy = anisotropy;
    return texture;
  }
  const glowTexture = canvasTexture(256, 256, (ctx, w) => {
    const g = ctx.createRadialGradient(w / 2, w / 2, 0, w / 2, w / 2, w / 2);
    g.addColorStop(0, 'rgba(255,255,255,1)');
    g.addColorStop(.04, 'rgba(255,255,255,.9)');
    g.addColorStop(.13, 'rgba(255,255,255,.28)');
    g.addColorStop(.35, 'rgba(255,255,255,.06)');
    g.addColorStop(1, 'rgba(255,255,255,0)');
    ctx.fillStyle = g; ctx.fillRect(0, 0, w, w);
  });
  const pointTexture = canvasTexture(64, 64, (ctx, w) => {
    const g = ctx.createRadialGradient(w / 2, w / 2, 0, w / 2, w / 2, w / 2);
    g.addColorStop(0, 'rgba(255,255,255,1)'); g.addColorStop(.2, 'rgba(255,255,255,.8)'); g.addColorStop(1, 'rgba(255,255,255,0)');
    ctx.fillStyle = g; ctx.fillRect(0, 0, w, w);
  });
  function mesh(geometry, material, parent, shadows = true) {
    const object = new THREE.Mesh(geometry, material);
    object.castShadow = shadows; object.receiveShadow = shadows;
    parent.add(object); return object;
  }
  function glow(parent, position, scale, color, opacity) {
    const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTexture, color, opacity, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false }));
    sprite.position.fromArray(position); sprite.scale.fromArray(scale); sprite.userData.skipAO = true; parent.add(sprite); return sprite;
  }
  function atmosphere(geometry, tint, intensity = 1) {
    return new THREE.Mesh(geometry, new THREE.ShaderMaterial({
      transparent: true, side: THREE.BackSide, blending: THREE.AdditiveBlending, depthWrite: false,
      uniforms: { tint: { value: new THREE.Color(tint) }, strength: { value: intensity } },
      vertexShader: `varying vec3 vP,vN;void main(){vec4 world=modelMatrix*vec4(position,1.);vP=world.xyz;vN=normalize(mat3(modelMatrix)*normal);gl_Position=projectionMatrix*viewMatrix*world;}`,
      fragmentShader: `uniform vec3 tint;uniform float strength;varying vec3 vP,vN;void main(){vec3 viewDir=normalize(cameraPosition-vP);float f=pow(1.-abs(dot(normalize(vN),viewDir)),3.8);float day=.3+.7*max(dot(normalize(vN),normalize(vec3(-.6,1.,.6))),0.);gl_FragColor=vec4(tint*f*day*strength,f*.8);}`
    }));
  }

  // ---------- The supplied GLB, with its original research-guided geometry ----------
  const telescope = new THREE.Group(); scene.add(telescope);
  let modelLoaded = false;
  if (document.querySelector('[data-scene="telescope"], [data-scene="mission"]')) {
  const fallback = new THREE.Group(); telescope.add(fallback);
  const silver = new THREE.MeshPhysicalMaterial({ color: 0xc6cbd1, metalness: .95, roughness: .27, side: THREE.DoubleSide, clearcoat: .2 });
  for (let i = 0; i < 3; i++) {
    const radius = 2 - i * .35;
    const cone = mesh(new THREE.CylinderGeometry(radius, .7 - i * .1, 2.7 - i * .35, 96, 1, true), silver, fallback);
    cone.position.y = .35 + i * .17;
    const ring = mesh(new THREE.TorusGeometry(radius, .025, 10, 100), silver, fallback); ring.rotation.x = Math.PI / 2; ring.position.y = 1.7;
  }
  const foil = new THREE.MeshStandardMaterial({ color: 0xc79b43, metalness: .9, roughness: .39 });
  const bus = mesh(new THREE.CylinderGeometry(.77, .8, 1.2, 6), foil, fallback); bus.position.y = -1.6;
  const cellMat = new THREE.MeshPhysicalMaterial({ color: 0x111e3a, metalness: .4, roughness: .2, clearcoat: 1 });
  for (const x of [-1.4, 1.4]) { const panel = mesh(new THREE.BoxGeometry(1.05, 1.2, .04), cellMat, fallback); panel.position.set(x, -1.45, -.55); }
  new GLTFLoader(loadingManager).load('./assets/models/spherex.glb', gltf => {
    const model = gltf.scene;
    model.updateMatrixWorld(true);
    const bounds = new THREE.Box3().setFromObject(model);
    const dimensions = bounds.getSize(new THREE.Vector3());
    const center = bounds.getCenter(new THREE.Vector3());
    const longest = Math.max(dimensions.x, dimensions.y, dimensions.z);
    if (!(longest > 0) || !Number.isFinite(longest)) { failedModel = true; document.body.dataset.model = 'fallback'; invalidate(); console.warn('ORVYX: invalid model bounds, using fallback.'); return; }
    const scale = 5.8 / longest;
    model.scale.setScalar(scale);
    model.position.sub(center.multiplyScalar(scale));
    model.traverse(object => {
      if (!object.isMesh) return;
      object.castShadow = true; object.receiveShadow = true;
      const materials = Array.isArray(object.material) ? object.material : [object.material];
      materials.forEach((material, i) => {
        const name = material.name || '';
        if (name.includes('Photovoltaic')) {
          const physical = new THREE.MeshPhysicalMaterial();
          THREE.MeshStandardMaterial.prototype.copy.call(physical, material);
          physical.clearcoat = .85; physical.clearcoatRoughness = .13;
          physical.roughness = .25;
          materials[i] = physical;
        }
        const current = materials[i];
        current.envMapIntensity = name.includes('Black') ? .6 : 1.1;
        if (name.includes('Reflective aluminium')) { current.roughness = .30; current.metalness = 1; }
        if (name.includes('White thermal')) { current.roughness = .49; current.envMapIntensity = .8; }
        ['map', 'normalMap', 'roughnessMap', 'metalnessMap'].forEach(key => { if (current[key]) current[key].anisotropy = anisotropy; });
      });
      object.material = Array.isArray(object.material) ? materials : materials[0];
    });
    fallback.visible = false;
    telescope.add(model);
    modelLoaded = true; dirty = true;
    document.body.dataset.model = 'loaded';
    invalidate();
  }, undefined, error => { console.warn('ORVYX: using the real-time 3D fallback.', error); document.body.dataset.model = 'fallback'; failedModel = true; invalidate(); });
  }

  // ---------- A quiet field of stars, with real depth and subpixel light falloff ----------
  const starCount = 1900;
  const positions = new Float32Array(starCount * 3), colors = new Float32Array(starCount * 3), sizes = new Float32Array(starCount);
  for (let i = 0; i < starCount; i++) {
    const r = 65 + random() * 100, theta = random() * Math.PI * 2, phi = Math.acos(2 * random() - 1);
    positions.set([r * Math.sin(phi) * Math.cos(theta), r * Math.sin(phi) * Math.sin(theta), r * Math.cos(phi)], i * 3);
    const color = new THREE.Color().setHSL(.56 + random() * .14, .05 + random() * .15, .48 + random() * .38);
    colors.set([color.r, color.g, color.b], i * 3); sizes[i] = random() < .025 ? 2.3 : .6 + random() * .8;
  }
  const starGeo = new THREE.BufferGeometry();
  starGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  starGeo.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  starGeo.setAttribute('aSize', new THREE.BufferAttribute(sizes, 1));
  starGeo.setDrawRange(0, currentProfile.starCount);
  const stars = new THREE.Points(starGeo, new THREE.ShaderMaterial({
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, vertexColors: true,
    uniforms: { time: { value: 0 }, dpr: { value: renderer.getPixelRatio() } },
    vertexShader: `attribute float aSize;varying vec3 vC;uniform float time,dpr;void main(){vC=color;float tw=.85+.15*sin(time*.7+position.x*7.);gl_PointSize=aSize*dpr*tw;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);}`,
    fragmentShader: `varying vec3 vC;void main(){float d=length(gl_PointCoord-.5);float a=pow(smoothstep(.5,0.,d),1.7);gl_FragColor=vec4(vC,a*.8);}`,
  })); scene.add(stars);


  // ---------- Silk-like spectral sheets and filaments: geometry, not an image ----------
  const ribbons = new THREE.Group(); scene.add(ribbons);
  const ribbonMaterials = [], filamentMaterials = [];
  const ribbonColors = [0xaa704f, 0xd79b6c, 0xb77b85, 0x8b75a2, 0x667faa, 0x729eab, 0x7a84ad, 0xb3869f, 0xd9aa7d];
  for (let k = 0; k < 9; k++) {
    const points = [];
    for (let j = 0; j <= 90; j++) {
      const u = j / 90;
      points.push(new THREE.Vector3(-.4 + u * 15, -4.1 + Math.sin(u * 5.3 - .5) * 1.2 + u * 9.1 + (k - 4) * .22, -4.8 + Math.sin(u * 4.5 + k * .035) * .65 + k * .04));
    }
    const curve = new THREE.CatmullRomCurve3(points);
    const vertices = [], uvs = [], indices = [], width = .12 + (k % 3) * .04;
    for (let j = 0; j <= 120; j++) {
      const u = j / 120, p = curve.getPoint(u);
      for (const side of [-1, 1]) { vertices.push(p.x, p.y + side * width, p.z + side * .035); uvs.push(u, (side + 1) / 2); }
      if (j < 120) { const n = j * 2; indices.push(n, n + 1, n + 2, n + 1, n + 3, n + 2); }
    }
    const geometry = new THREE.BufferGeometry(); geometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3)); geometry.setAttribute('uv', new THREE.Float32BufferAttribute(uvs, 2)); geometry.setIndex(indices);
    const mat = new THREE.ShaderMaterial({
      transparent: true, side: THREE.DoubleSide, blending: THREE.AdditiveBlending, depthWrite: false,
      uniforms: { color: { value: new THREE.Color(ribbonColors[k]) }, opacity: { value: .24 }, time: { value: 0 } },
      vertexShader: `varying vec2 vUv;uniform float time;void main(){vUv=uv;vec3 p=position;p.y+=sin(uv.x*10.+time*.16)*.025;gl_Position=projectionMatrix*modelViewMatrix*vec4(p,1.);}`,
      fragmentShader: `uniform vec3 color;uniform float opacity;varying vec2 vUv;void main(){float fade=smoothstep(0.,.2,vUv.x)*(1.-smoothstep(.8,1.,vUv.x));float silk=pow(sin(vUv.y*3.14159),1.4);vec3 c=color*(.8+silk*.7);gl_FragColor=vec4(c,fade*silk*opacity);}`,
    });
    const ribbon = new THREE.Mesh(geometry, mat); ribbon.userData.skipAO = true; ribbons.add(ribbon); ribbonMaterials.push(mat);
    const filamentMat = new THREE.ShaderMaterial({ transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, uniforms: { color: { value: new THREE.Color(ribbonColors[k]).multiplyScalar(1.7) }, opacity: { value: .4 } }, vertexShader: `varying vec2 vUv;void main(){vUv=uv;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);}`, fragmentShader: `uniform vec3 color;uniform float opacity;varying vec2 vUv;void main(){float fade=smoothstep(0.,.2,vUv.x)*(1.-smoothstep(.85,1.,vUv.x));gl_FragColor=vec4(color,fade*opacity);}` });
    const filament = new THREE.Mesh(new THREE.TubeGeometry(curve, 110, k % 3 === 0 ? .013 : .006, 5, false), filamentMat); filament.userData.skipAO = true; ribbons.add(filament); filamentMaterials.push(filamentMat);
  }
  const telescopeFlare = new THREE.Group(); scene.add(telescopeFlare);
  glow(telescopeFlare, [5.0, 2.55, -3.5], [5.0, 5.0, 1], new THREE.Color(1.7, 1.1, .6), .33);
  glow(telescopeFlare, [5.0, 2.55, -3.4], [.45, .45, 1], new THREE.Color(7, 4.8, 2.3), .85);
  glow(telescopeFlare, [5.0, 2.55, -3.3], [5.5, .035, 1], new THREE.Color(1.5, 1.0, .6), .4);
  const skyOrbits = new THREE.Group(); scene.add(skyOrbits);
  for (let k = 0; k < 3; k++) {
    const points = []; for (let j = 0; j <= 180; j++) { const a = j / 180 * Math.PI * 2; points.push(new THREE.Vector3(Math.cos(a) * (5.6 + k * .55), Math.sin(a) * (4.0 + k * .38), 0)); }
    const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints(points), new THREE.LineBasicMaterial({ color: 0x9da6b8, transparent: true, opacity: .065 - k * .014 }));
    line.rotation.set(.12, .30, -.48); skyOrbits.add(line);
  }
  skyOrbits.position.set(4.1, .6, -6);

  // ---------- Procedural textures for the illustrative outer-world chapter ----------
  function noise(seedValue) {
    let s = seedValue; const grid = [];
    for (let i = 0; i < 4096; i++) { s = s * 16807 % 2147483647; grid.push(s / 2147483647); }
    return (x, y) => { const ix = Math.floor(x), iy = Math.floor(y), fx = x - ix, fy = y - iy, u = fx * fx * (3 - 2 * fx), v = fy * fy * (3 - 2 * fy); const g = (a, b) => grid[(a & 63) + (b & 63) * 64]; return (g(ix, iy) * (1 - u) + g(ix + 1, iy) * u) * (1 - v) + (g(ix, iy + 1) * (1 - u) + g(ix + 1, iy + 1) * u) * v; };
  }
  function fbm(n, x, y, octaves = 4) { let result = 0, amplitude = .5, total = 0; for (let i = 0; i < octaves; i++) { result += n(x, y) * amplitude; total += amplitude; amplitude *= .5; x *= 2.07; y *= 2.07; } return result / total; }
  const planet = new THREE.Group(); scene.add(planet);
  let planetBody = null, planetPrepared = false, observationsPrepared = false, narratorPrepared = false;
  const coolWavelength = new THREE.Color('#8da4d0'), warmWavelength = new THREE.Color('#ffd0a0');
  let currentWavelength = Number.isFinite(window.ORVYX_WAVELENGTH) ? window.ORVYX_WAVELENGTH : 4.3;
  function applyWavelength(value) {
    if (!Number.isFinite(value)) return;
    currentWavelength = Math.max(.75, Math.min(5, value));
    if (planetBody) {
      const t = (currentWavelength - .75) / 4.25;
      planetBody.material.color.copy(coolWavelength).lerp(warmWavelength, t);
      planetBody.material.emissive.copy(planetBody.material.color);
      planetBody.material.emissiveIntensity = .03 + .09 * t;
    }
    invalidate();
  }
  window.addEventListener('orvyx:wavelength', e => applyWavelength(e.detail));
  const yieldWork = () => globalThis.scheduler?.yield ? globalThis.scheduler.yield() : new Promise(resolve => setTimeout(resolve, 0));
  async function initPlanet() {
    const w = 1024, h = 512, canvas = document.createElement('canvas');
    canvas.width = w; canvas.height = h;
    const ctx = canvas.getContext('2d');
    const n = noise(42), image = ctx.createImageData(w, h), palette = [[8,10,17], [34,38,63], [101,70,92], [167,117,82], [217,176,135], [85,107,123]];
    let rows = 16;
    for (let start = 0; start < h;) {
      const started = performance.now(), end = Math.min(h, start + rows);
      for (let y = start; y < end; y++) for (let x = 0; x < w; x++) {
      const turbulence = fbm(n, x / 145, y / 48) * .105 + Math.sin(x / w * 6.28318 + y / h * 7) * .045;
      const band = (.5 + .5 * Math.sin((y / h + turbulence) * 42)) * .75 + fbm(n, x / 170, y / 90, 3) * .25;
      const index = Math.min(4, Math.floor(band * 5)), blend = band * 5 - index, shade = .86 + fbm(n, x / 35, y / 30, 3) * .25;
      const p = (y * w + x) * 4;
      for (let channel = 0; channel < 3; channel++) image.data[p + channel] = (palette[index][channel] * (1 - blend) + palette[index + 1][channel] * blend) * shade;
      image.data[p + 3] = 255;
      }
      start = end;
      if (performance.now() - started > 50) rows = Math.max(1, Math.floor(rows / 2));
      await yieldWork();
    }
    ctx.putImageData(image, 0, 0);
    const gasTexture = new THREE.CanvasTexture(canvas);
    gasTexture.colorSpace = THREE.SRGBColorSpace; gasTexture.anisotropy = anisotropy;
    planetBody = mesh(new THREE.SphereGeometry(1.7, 112, 80), new THREE.MeshPhysicalMaterial({ map: gasTexture, roughness: .24, metalness: .42, clearcoat: 1, clearcoatRoughness: .13, envMapIntensity: 1.5 }), planet);
    applyWavelength(currentWavelength);
  const planetAtmo = atmosphere(new THREE.SphereGeometry(1.75, 96, 64), 0x8f96c5, .7); planetAtmo.userData.skipAO = true; planet.add(planetAtmo);
  const ringTexture = canvasTexture(512, 8, (ctx, w, h) => {
    const n = noise(91);
    for (let x = 0; x < w; x++) { const value = fbm(n, x / 6, 2, 3); const gap = x > 177 && x < 189 || x > 336 && x < 343; ctx.fillStyle = `rgba(${170 + value * 65},${154 + value * 61},${148 + value * 57},${gap ? .025 : .18 + value * .72})`; ctx.fillRect(x, 0, 1, h); }
  }, true);
  const ringGeometry = new THREE.RingGeometry(2.2, 3.4, 180);
  const ringUV = ringGeometry.attributes.uv, ringPos = ringGeometry.attributes.position;
  for (let i = 0; i < ringUV.count; i++) ringUV.setXY(i, (Math.hypot(ringPos.getX(i), ringPos.getY(i)) - 2.2) / 1.2, .5);
  const rings = mesh(ringGeometry, new THREE.MeshStandardMaterial({ map: ringTexture, transparent: true, opacity: .88, side: THREE.DoubleSide, roughness: .85, depthWrite: false }), planet, false);
  rings.visible = false; planet.rotation.z = .33;
  // Fine gyroscopic lines keep the sphere sculptural rather than a Saturn lookalike.
  for (let j = 0; j < 5; j++) {
    const orbit = mesh(new THREE.TorusGeometry(1.92 + j * .12, .004, 6, 160), new THREE.MeshBasicMaterial({color: 0xc9b2d4, transparent: true, opacity: .16 - j * .02, depthWrite: false}), planet, false);
    orbit.rotation.set(.8 + j * .33, .25, j * .42);
  }
    planetPrepared = true; invalidate();
  }

  // ---------- Observation glass plates. Deliberately simulated, never invented data. ----------
  const observations = new THREE.Group(); scene.add(observations);
  const observationMovers = [], observationOutlines = [];
  let selectedObservation = Number.isInteger(window.ORVYX_OBSERVATION) ? window.ORVYX_OBSERVATION : 1;
  function applyObservation(index) {
    if (!Number.isInteger(index) || index < 0 || index > 2) return;
    selectedObservation = index;
    observationOutlines.forEach((outline, i) => { outline.material.opacity = i === index ? .85 : .25; });
    observationMovers.forEach((mover, i) => { mover.material.opacity = i === index ? 1 : .4; });
    invalidate();
  }
  window.addEventListener('orvyx:observation', e => applyObservation(e.detail));
  function initObservations() {
  for (let k = 0; k < 3; k++) {
    const plate = new THREE.Group(); plate.position.set((k - 1) * .62, (k - 1) * .23, -k * .8); plate.rotation.set(.04, -.3, .04); observations.add(plate);
    const geometry = new THREE.PlaneGeometry(3.25, 3.25);
    const glass = mesh(geometry, new THREE.MeshPhysicalMaterial({ color: 0x708aa5, metalness: .18, roughness: .25, transparent: true, opacity: .065, side: THREE.DoubleSide, depthWrite: false }), plate, false);
    glass.userData.skipAO = true;
    const outline = new THREE.LineSegments(new THREE.EdgesGeometry(geometry), new THREE.LineBasicMaterial({ color: k === 2 ? 0xd3b493 : 0x8298b0, transparent: true, opacity: .25 })); plate.add(outline); observationOutlines.push(outline);
    const coords = [], starColors = [];
    for (let j = 0; j < 85; j++) { coords.push(((j * 37) % 97) / 97 * 2.95 - 1.475, ((j * 71) % 89) / 89 * 2.95 - 1.475, .02); const c = .35 + (j % 8) * .08; starColors.push(c, c, c * 1.05); }
    const fieldGeometry = new THREE.BufferGeometry(); fieldGeometry.setAttribute('position', new THREE.Float32BufferAttribute(coords, 3)); fieldGeometry.setAttribute('color', new THREE.Float32BufferAttribute(starColors, 3));
    const field = new THREE.Points(fieldGeometry, new THREE.PointsMaterial({ map: pointTexture, vertexColors: true, size: .065, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending })); plate.add(field);
    const gridPositions = [];
    for (let j = 1; j < 5; j++) { const p = -1.625 + j * .65; gridPositions.push(-1.625, p, .01, 1.625, p, .01, p, -1.625, .01, p, 1.625, .01); }
    const grid = new THREE.LineSegments(new THREE.BufferGeometry().setAttribute('position', new THREE.Float32BufferAttribute(gridPositions, 3)), new THREE.LineBasicMaterial({ color: 0x8b9fbd, transparent: true, opacity: .07 })); plate.add(grid);
    const mover = glow(plate, [-.45 + k * .28, .2, .07], [.3, .3, 1], new THREE.Color(3.0, 1.8, .8), .9); observationMovers.push(mover);
    const labelTexture = canvasTexture(512, 64, (ctx, w) => { ctx.fillStyle = '#a6b1be'; ctx.font = '17px monospace'; ctx.fillText(`OBSERVATION / 0${k + 1}                       SIMULATED`, 4, 37); }, true);
    const label = mesh(new THREE.PlaneGeometry(2.9, .36), new THREE.MeshBasicMaterial({ map: labelTexture, transparent: true, opacity: .7, depthWrite: false }), plate, false); label.position.set(0, -1.87, .03); label.userData.skipAO = true;
  }
    const points = observationMovers.map(mover => { mover.parent.updateMatrix(); return mover.position.clone().applyMatrix4(mover.parent.matrix); });
    observations.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(points), new THREE.LineBasicMaterial({ color: 0xf59e0b, transparent: true, opacity: .7 })));
    applyObservation(selectedObservation);
    observationsPrepared = true; invalidate();
  }

  // ---------- Cosmic Narrator: an opalescent, gyroscopic celestial sculpture ----------
  const narrator = new THREE.Group(); scene.add(narrator);
  const core = new THREE.Group(); narrator.add(core);
  let narratorDust;
  const narratorFilaments = [], narratorRings = [];
  async function initNarrator() {
    const w = 512, h = 256, canvas = document.createElement('canvas');
    canvas.width = w; canvas.height = h;
    const ctx = canvas.getContext('2d'), n = noise(37), image = ctx.createImageData(w, h);
    let rows = 16;
    for (let start = 0; start < h;) {
      const started = performance.now(), end = Math.min(h, start + rows);
      for (let y = start; y < end; y++) for (let x = 0; x < w; x++) { const value = fbm(n, x / 55, y / 55, 4), vein = Math.pow(Math.abs(Math.sin(x / 44 + value * 13 + y / 67)), 16); const p = (y * w + x) * 4; image.data[p] = 26 + value * 26 + vein * 80; image.data[p + 1] = 30 + value * 28 + vein * 55; image.data[p + 2] = 44 + value * 34 + vein * 24; image.data[p + 3] = 255; }
      start = end;
      if (performance.now() - started > 50) rows = Math.max(1, Math.floor(rows / 2));
      await yieldWork();
    }
    ctx.putImageData(image, 0, 0);
    const coreTexture = new THREE.CanvasTexture(canvas);
    coreTexture.colorSpace = THREE.SRGBColorSpace; coreTexture.anisotropy = anisotropy;
  const coreMaterial = new THREE.MeshPhysicalMaterial({ map: coreTexture, bumpMap: coreTexture, bumpScale: .008, emissiveMap: coreTexture, emissive: 0x485574, emissiveIntensity: .25, color: 0x9fa8c3, metalness: .62, roughness: .18, clearcoat: 1, clearcoatRoughness: .12, iridescence: .5, iridescenceIOR: 1.3, iridescenceThicknessRange: [120, 330], envMapIntensity: 1.5 });
  mesh(new THREE.SphereGeometry(1.16, 96, 64), coreMaterial, core, false);
  for (let k = 0; k < 28; k++) {
    const points = [], latitude = -1.15 + k / 27 * 2.3, phase = k * 2.399963;
    for (let j = 0; j <= 110; j++) { const u = j / 110 * Math.PI * 2, lat = latitude + .14 * Math.sin(3 * u + phase), r = 1.18 + .018 * Math.sin(4 * u + phase); points.push(new THREE.Vector3(r * Math.cos(lat) * Math.cos(u), r * Math.sin(lat), r * Math.cos(lat) * Math.sin(u))); }
    const material = new THREE.MeshBasicMaterial({ color: new THREE.Color(k % 7 === 0 ? 0x38bdf8 : 0xc6ab8c).multiplyScalar(1.4), transparent: true, opacity: .5, blending: THREE.AdditiveBlending, depthWrite: false });
    const filament = mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(points), 115, k % 3 ? .004 : .009, 5, false), material, core, false); filament.userData.skipAO = true; narratorFilaments.push(material);
  }
  const orbitMaterial = new THREE.MeshPhysicalMaterial({ color: 0xc6ab8c, metalness: .9, roughness: .25, clearcoat: .4 });
  for (let k = 0; k < 4; k++) {
    const ring = mesh(new THREE.TorusGeometry(1.48 + k * .18, .012 + k * .001, 12, 180, k === 3 ? Math.PI * 1.72 : Math.PI * 2), orbitMaterial, narrator, false);
    ring.rotation.set(.7 + k * .54, .35 + k * .28, k * .64); narratorRings.push(ring);
  }
  const dustPositions = [], dustColors = [];
  for (let k = 0; k < 180; k++) { const phi = Math.acos(1 - 2 * (k + .5) / 180), theta = k * 2.399963, r = 1.63 + (k % 7) * .075; dustPositions.push(r * Math.sin(phi) * Math.cos(theta), r * Math.cos(phi), r * Math.sin(phi) * Math.sin(theta)); dustColors.push(.7 + random() * .3, .57 + random() * .2, .43 + random() * .3); }
  const dustGeometry = new THREE.BufferGeometry(); dustGeometry.setAttribute('position', new THREE.Float32BufferAttribute(dustPositions, 3)); dustGeometry.setAttribute('color', new THREE.Float32BufferAttribute(dustColors, 3));
  narratorDust = new THREE.Points(dustGeometry, new THREE.PointsMaterial({ map: pointTexture, vertexColors: true, size: .035, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending })); narrator.add(narratorDust);
  glow(narrator, [0, 0, -.5], [5, 5, 1], 0x525a8d, .18);
    narratorPrepared = true; invalidate();
  }
  let familiesQueued = false;
  function preparePageFamilies() {
    if (document.querySelector('[data-scene="infrared"]')) initPlanet();
    if (document.querySelector('[data-scene="compare"]')) initObservations();
    if (document.querySelector('[data-scene="narrator"]')) initNarrator();
  }

  // ---------- One cinematic pipeline, with user-adjustable finishing ----------
  const effects = createSpherexEffects(renderer, scene, camera, effectiveSettings());
  let story = window.ORVYX_STORY || { from: 'intro', to: 'intro', mix: 0, active: 'intro' };
  const sceneNames = ['intro', 'telescope', 'mission', 'infrared', 'compare', 'narrator'];
  const desktopFrames = Object.fromEntries([
    { cam: [0, 1.1, 20], look: [0, .5, 0], tel: [0, -.55, -2.5], ts: 0, rot: [.62, -.18, .12], planet: [9, 0, -8], ps: 0, obs: [9, 0, -4], os: 0, narr: [3.4, .1, 0], ns: 0 },
    { cam: [0, .65, 16], look: [.35, .1, 0], tel: [3.3, -.15, 0], ts: .94, rot: [.60, -.48, .20], planet: [9, 0, -8], ps: 0, obs: [9, 0, -4], os: 0, narr: [3.4, .1, 0], ns: 0 },
    { cam: [-.6, 1.4, 13.8], look: [.7, .1, 0], tel: [3.25, .35, 0], ts: 1.03, rot: [.76, .22, -.15], planet: [9, 0, -8], ps: 0, obs: [9, 0, -4], os: 0, narr: [3.4, .1, 0], ns: 0 },
    { cam: [0, .2, 17], look: [0, 0, 0], tel: [11, -1, -12], ts: 0, rot: [.4, 1.1, .5], planet: [-3.3, .15, 0], ps: 1.34, obs: [9, 0, -4], os: 0, narr: [3.4, .1, 0], ns: 0 },
    { cam: [0, .2, 17], look: [0, 0, 0], tel: [11, -1, -12], ts: 0, rot: [.4, 1.7, .4], planet: [-10, 0, -8], ps: 0, obs: [3.35, .1, 0], os: 1.36, narr: [3.4, .1, 0], ns: 0 },
    { cam: [0, .2, 17], look: [0, 0, 0], tel: [11, -1, -12], ts: 0, rot: [.4, 1.7, .4], planet: [-10, 0, -8], ps: 0, obs: [9, 0, -5], os: 0, narr: [3.4, .1, 0], ns: 1.58 }
  ].map((frame, index) => [sceneNames[index], frame]));
  const mobileFrames = Object.fromEntries([
    { cam: [0, .4, 19], look: [0, .3, 0], tel: [0, 2.3, -3], ts: 0, rot: [.62, -.3, .18], planet: [9, 0, -8], ps: 0, obs: [9, 0, -4], os: 0, narr: [0, 2.6, 0], ns: 0 },
    { cam: [0, .3, 18], look: [0, .1, 0], tel: [.72, 2.55, -1], ts: .46, rot: [.62, -.48, .22], planet: [9, 0, -8], ps: 0, obs: [9, 0, -4], os: 0, narr: [0, 2.6, 0], ns: 0 },
    { cam: [0, .3, 18], look: [0, .1, 0], tel: [0, 2.4, -.5], ts: .64, rot: [.78, .2, -.14], planet: [9, 0, -8], ps: 0, obs: [9, 0, -4], os: 0, narr: [0, 2.6, 0], ns: 0 },
    { cam: [0, .2, 18], look: [0, 0, 0], tel: [8, 0, -8], ts: 0, rot: [.4, 1.1, .5], planet: [0, 2.7, 0], ps: .61, obs: [9, 0, -4], os: 0, narr: [0, 2.6, 0], ns: 0 },
    { cam: [0, .2, 18], look: [0, 0, 0], tel: [8, 0, -8], ts: 0, rot: [.4, 1.7, .4], planet: [-8, 0, -8], ps: 0, obs: [0, 2.8, 0], os: .72, narr: [0, 2.6, 0], ns: 0 },
    { cam: [0, .2, 18], look: [0, 0, 0], tel: [8, 0, -8], ts: 0, rot: [.4, 1.7, .4], planet: [-8, 0, -8], ps: 0, obs: [8, 0, -4], os: 0, narr: [0, 2.7, 0], ns: .95 }
  ].map((frame, index) => [sceneNames[index], frame]));
  const ribbonWeights = { intro: 1, telescope: 1, mission: 0, infrared: 0, compare: 0, narrator: 0 };
  const flareWeights = { intro: 0, telescope: 1, mission: .5, infrared: 0, compare: 0, narrator: 0 };
  const narratorButton = document.querySelector('#narratorButton'), narratorSection = document.querySelector('#narrator');
  const lerp = THREE.MathUtils.lerp;
  const vector = new THREE.Vector3();
  function blendVector(a, b, t) { return vector.set(lerp(a[0], b[0], t), lerp(a[1], b[1], t), lerp(a[2], b[2], t)); }
  function place(object, aPos, bPos, aScale, bScale, t) {
    object.position.copy(blendVector(aPos, bPos, t)).applyMatrix4(camera.matrixWorldInverse);
    object.position.x *= framing.horizontalScale;
    object.position.applyMatrix4(camera.matrixWorld);
    const scale = Math.max(.0001, lerp(aScale, bScale, t)) * framing.sculptureScale;
    object.scale.setScalar(scale); object.visible = scale > .005;
  }
  const pointer = new THREE.Vector2(), pointerCurrent = new THREE.Vector2();
  const orbitKeys = ['telescope', 'planet', 'observations', 'narrator'];
  const orbitOffset = { telescope: 0, planet: 0, observations: 0, narrator: 0 };
  const orbitCurrent = { telescope: 0, planet: 0, observations: 0, narrator: 0 };
  let dragging = null, dragX = 0;
  document.querySelectorAll('[data-orbit-target]').forEach(target => {
    const key = target.dataset.orbitTarget;
    function release() { dragging = null; target.classList.remove('dragging'); }
    target.addEventListener('pointerdown', e => {
      if (e.pointerType === 'touch' || e.button !== 0 || e.target.closest('button,a,input,select,textarea')) return;
      dragging = key; dragX = e.clientX; target.setPointerCapture(e.pointerId); target.classList.add('dragging');
    });
    target.addEventListener('pointermove', e => { if (dragging !== key) return; orbitOffset[key] += (e.clientX - dragX) * .009; dragX = e.clientX; invalidate(); });
    target.addEventListener('pointerup', release);
    target.addEventListener('pointercancel', release);
    target.addEventListener('lostpointercapture', release);
    target.addEventListener('keydown', e => {
      if (e.target !== target) return;
      if (e.key === 'Home') orbitOffset[key] = 0;
      else if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') orbitOffset[key] += (e.key === 'ArrowRight' ? 1 : -1) * Math.PI / 12;
      else return;
      e.preventDefault(); invalidate();
    });
    target.querySelector('[data-orbit-step]').addEventListener('click', () => { orbitOffset[key] += Math.PI / 3; invalidate(); });
  });
  window.addEventListener('pointermove', e => { pointer.set((e.clientX / innerWidth - .5) * 2, (e.clientY / innerHeight - .5) * 2); if (settings.motion) invalidate(); }, { passive: true });
  window.addEventListener('orvyx:story', e => { story = e.detail; invalidate(); });
  window.addEventListener('orvyx:visuals', e => {
    const oldQuality = settings.quality;
    settings = { ...settings, ...e.detail };
    effects.setSettings(effectiveSettings());
    if (e.detail.resetAuto && settings.quality === 'auto') qualityLevel = 0;
    if (oldQuality !== settings.quality || e.detail.resetAuto) resize(); invalidate();
  });
  function resize() {
    mobile = innerWidth <= 700;
    viewportWidth = Math.max(1, stage.clientWidth); viewportHeight = Math.max(1, stage.clientHeight);
    framing = getSceneFraming(viewportWidth, viewportHeight, mobile);
    currentProfile = profile();
    camera.aspect = viewportWidth / viewportHeight; camera.updateProjectionMatrix();
    sizeBackground();
    renderer.setPixelRatio(pixelRatio()); renderer.setSize(viewportWidth, viewportHeight, false);
    effects.resize(viewportWidth, viewportHeight, renderer.getPixelRatio());
    stars.material.uniforms.dpr.value = renderer.getPixelRatio();
    starGeo.setDrawRange(0, currentProfile.starCount);
    renderer.shadowMap.enabled = currentProfile.shadows;
    const shadowSize = currentProfile.shadowSize || 1024;
    if (key.shadow.mapSize.x !== shadowSize) {
      key.shadow.mapSize.set(shadowSize, shadowSize);
      if (key.shadow.map) { key.shadow.map.dispose(); key.shadow.map = null; }
      key.shadow.needsUpdate = true;
    } invalidate();
  }
  window.addEventListener('resize', resize);
  window.addEventListener('orientationchange', resize);
  document.addEventListener('fullscreenchange', resize);
  const surfaceObserver = new ResizeObserver(resize);
  surfaceObserver.observe(stage);
  document.addEventListener('visibilitychange', () => { lastFrame = 0; resetSampling(); if (document.hidden) stopFrame(); else invalidate(); });
  canvas.addEventListener('webglcontextlost', e => { e.preventDefault(); contextLost = true; stopFrame(); ready(false); });
  canvas.addEventListener('webglcontextrestored', () => { contextLost = false; lastFrame = 0; resetSampling(); ready(true, modelLoaded); invalidate(); });
  let elapsed = 0, frames = 0, lastFrame = 0;
  const zeroPointer = new THREE.Vector2();
  const diagnostics = { webgl: true, modelLoaded: false, activeScene: story.active, sceneReady: false, qualityLevel, averageFps: 0, p95FrameMs: 0, paused: false, lastRenderTime: 0, drawCalls: 0, triangles: 0, pixelRatio: renderer.getPixelRatio(), cinematic: settings.enabled, softwareRenderer, frames: 0 };
  window.ORVYX_DIAGNOSTICS = diagnostics;
  const frameIntervals = new Float64Array(120);
  let intervalCount = 0, intervalCursor = 0, warmStart = 0, windowStart = 0, badWindows = 0;
  function resetSampling() { intervalCount = 0; intervalCursor = 0; warmStart = 0; windowStart = 0; badWindows = 0; }
  function stopFrame() {
    if (frameRequest) cancelAnimationFrame(frameRequest);
    frameRequest = 0; lastFrame = 0; diagnostics.paused = true;
  }
  function invalidate() {
    dirty = true;
    if (!frameRequest && !document.hidden && !pageHidden && !contextLost && !disposed && sceneVisible) frameRequest = requestAnimationFrame(tick);
  }
  const visibleSections = new Set();
  const visibilityObserver = new IntersectionObserver(entries => {
    for (const entry of entries) entry.isIntersecting ? visibleSections.add(entry.target) : visibleSections.delete(entry.target);
    sceneVisible = visibleSections.size > 0;
    if (sceneVisible) { lastFrame = 0; resetSampling(); invalidate(); }
    else { stopFrame(); resetSampling(); }
  });
  document.querySelectorAll('.story-section').forEach(section => visibilityObserver.observe(section));
  window.addEventListener('pagehide', event => {
    pageHidden = true; stopFrame(); resetSampling();
    if (!event.persisted) {
      disposed = true; visibilityObserver.disconnect(); surfaceObserver.disconnect(); effects.dispose();
      scene.traverse(object => {
        if (object.geometry) object.geometry.dispose();
        const materials = object.material ? (Array.isArray(object.material) ? object.material : [object.material]) : [];
        for (const material of materials) {
          for (const value of Object.values(material)) if (value?.isTexture) value.dispose();
          material.dispose();
        }
      });
      if (scene.background?.isTexture) scene.background.dispose();
      environmentTarget.dispose(); renderer.dispose();
    }
  });
  window.addEventListener('pageshow', event => { if (event.persisted) { pageHidden = false; story = window.ORVYX_STORY || story; lastFrame = 0; resetSampling(); invalidate(); } });
  function tick(now) {
    frameRequest = 0;
    if (document.hidden || pageHidden || contextLost || disposed || !sceneVisible) { stopFrame(); return; }
    const moving = orbitKeys.some(key => Math.abs(orbitOffset[key] - orbitCurrent[key]) > .002);
    if (!settings.motion && !dirty && !moving) { stopFrame(); resetSampling(); return; }
    diagnostics.paused = false;
    const frameMs = lastFrame ? now - lastFrame : 0;
    const dt = Math.min(frameMs / 1000, .05);
    lastFrame = now;
    dirty = false;
    if (settings.motion) elapsed += dt;
    const smooth = 1 - Math.exp(-dt * 6.5);
    const efficientAuto = softwareRenderer && settings.quality === 'auto';
    const frameSet = mobile ? mobileFrames : desktopFrames;
    const fraction = THREE.MathUtils.smoothstep(story.mix, 0, 1);
    const a = frameSet[story.from], b = frameSet[story.to];
    const ribbonVisibility = lerp(ribbonWeights[story.from], ribbonWeights[story.to], fraction);
    const flareIn = lerp(flareWeights[story.from], flareWeights[story.to], fraction);
    camera.position.copy(blendVector(a.cam, b.cam, fraction));
    pointerCurrent.lerp(settings.motion && !mobile ? pointer : zeroPointer, smooth * .5);
    camera.position.x += pointerCurrent.x * .08; camera.position.y -= pointerCurrent.y * .045;
    camera.lookAt(blendVector(a.look, b.look, fraction));
    camera.updateMatrixWorld();
    place(telescope, a.tel, b.tel, a.ts, b.ts, fraction);
    key.castShadow = currentProfile.shadows && telescope.visible;
    for (const key of orbitKeys) orbitCurrent[key] = lerp(orbitCurrent[key], orbitOffset[key], 1 - Math.exp(-dt * 8));
    const ambient = settings.motion ? Math.sin(elapsed * .25) * .045 : 0;
    telescope.rotation.set(lerp(a.rot[0], b.rot[0], fraction) + ambient * .25, lerp(a.rot[1], b.rot[1], fraction) + ambient + orbitCurrent.telescope, lerp(a.rot[2], b.rot[2], fraction));
    place(planet, a.planet, b.planet, a.ps, b.ps, fraction);
    place(observations, a.obs, b.obs, a.os, b.os, fraction);
    place(narrator, a.narr, b.narr, a.ns, b.ns, fraction);
    planet.rotation.y = orbitCurrent.planet;
    observations.rotation.y = orbitCurrent.observations;
    narrator.rotation.y = orbitCurrent.narrator;
    if (settings.motion) {
      if (planet.visible && planetBody) planetBody.rotation.y += dt * .025;
      if (narrator.visible && narratorPrepared) {
        core.rotation.y += dt * .08;
        narratorRings.forEach((ring, k) => ring.rotation.z += dt * .025 * (k % 2 ? -1 : 1));
        narratorDust.rotation.y -= dt * .035;
      }
    }
    const openNarrator = narratorButton?.getAttribute('aria-expanded') === 'true' || narratorSection?.classList.contains('demo-open');
    narratorFilaments.forEach((mat, k) => { mat.opacity = (openNarrator ? .7 : .45) + (settings.motion ? Math.sin(elapsed * .6 + k * .18) * .045 : 0); });
    ribbons.visible = ribbonVisibility > .01;
    ribbonMaterials.forEach(mat => { mat.uniforms.opacity.value = .24 * ribbonVisibility * (mobile ? .6 : 1); mat.uniforms.time.value = elapsed; });
    filamentMaterials.forEach(mat => { mat.uniforms.opacity.value = .40 * ribbonVisibility * (mobile ? .6 : 1); });
    telescopeFlare.visible = flareIn > .01;
    telescopeFlare.children.forEach((object, k) => { object.material.opacity = [.33, .85, .4][k] * flareIn; });
    skyOrbits.visible = flareIn > .01;
    skyOrbits.rotation.z = settings.motion ? elapsed * .002 : 0;
    stars.material.uniforms.time.value = elapsed;
    stars.rotation.y = settings.motion ? elapsed * .00065 : stars.rotation.y;
    // Drift the cropped background texture with scroll and subtle ambient motion.
    if (scene.background && scene.background.isTexture && scene.background.image) {
      const bg = scene.background;
      const availableX = Math.max(0, 1 - bg.repeat.x), availableY = Math.max(0, 1 - bg.repeat.y);
      bg.offset.x = availableX * (.5 + .18 * Math.sin((settings.motion ? elapsed * .025 : 0)));
      bg.offset.y = availableY * .5;
      bg.updateMatrix();
    }
    effects.render(dt, elapsed);
    frames++;
    if (!familiesQueued) { familiesQueued = true; requestAnimationFrame(preparePageFamilies); }
    const sceneReady = story.active === 'intro' || (story.active === 'telescope' || story.active === 'mission' ? modelLoaded || failedModel : story.active === 'infrared' ? planetPrepared : story.active === 'compare' ? observationsPrepared : narratorPrepared);
    const modelState = failedModel ? 'fallback' : modelLoaded ? 'loaded' : 'pending';
    if (sceneReady && (!sceneAnnounced || announcedModelState !== modelState)) { sceneAnnounced = true; announcedModelState = modelState; ready(true, modelLoaded); }
    diagnostics.modelLoaded = modelLoaded; diagnostics.activeScene = story.active;
    diagnostics.drawCalls = renderer.info.render.calls; diagnostics.triangles = renderer.info.render.triangles;
    diagnostics.pixelRatio = renderer.getPixelRatio(); diagnostics.cinematic = settings.enabled; diagnostics.frames = frames;
    diagnostics.sceneReady = sceneReady; diagnostics.qualityLevel = qualityLevel; diagnostics.lastRenderTime = now;
    if (settings.motion || moving) {
      if (!warmStart) warmStart = now;
      if (now - warmStart >= 2000) {
        if (!windowStart) windowStart = now;
        if (frameMs > 0) { frameIntervals[intervalCursor] = frameMs; intervalCursor = (intervalCursor + 1) % frameIntervals.length; intervalCount = Math.min(frameIntervals.length, intervalCount + 1); }
        if (now - windowStart >= 2000 && intervalCount) {
          const values = Array.from(frameIntervals.subarray(0, intervalCount)).sort((x, y) => x - y);
          diagnostics.averageFps = 1000 * intervalCount / values.reduce((sum, value) => sum + value, 0);
          diagnostics.p95FrameMs = values[Math.ceil(values.length * .95) - 1];
          badWindows = diagnostics.averageFps < 35 || diagnostics.p95FrameMs > 33.4 ? badWindows + 1 : 0;
          intervalCount = 0; intervalCursor = 0; windowStart = now;
          if (settings.quality === 'auto' && badWindows >= 2 && qualityLevel < 2) { qualityLevel++; badWindows = 0; resize(); }
        }
      }
      if (!frameRequest) frameRequest = requestAnimationFrame(tick);
    } else { lastFrame = 0; diagnostics.paused = true; resetSampling(); }
  }
  invalidate();
}

}
// Give the local first-frame poster and typography a paint before GPU setup.
requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(initScene, 60)));
