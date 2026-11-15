import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { createSpherexEffects } from './spherex-effects.js?v=stable-2';

function initScene() {
const canvas = document.querySelector('#scene');
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
  if (softwareRenderer && settings.quality === 'auto' && !settings.motionOverride) {
    settings.motion = false;
    window.dispatchEvent(new CustomEvent('orvyx:performance', { detail: { reducedAmbient: true } }));
  }
  const effectiveSettings = () => ({ ...settings, quality: softwareRenderer && settings.quality === 'auto' ? 'efficient' : settings.quality });
  let dirty = true, assetsReady = false, sceneAnnounced = false, failedModel = false;
  let mobile = innerWidth <= 700;
  const pixelRatio = () => Math.min(devicePixelRatio || 1, softwareRenderer && settings.quality === 'auto' ? 1 : settings.quality === 'high' ? 2 : settings.quality === 'efficient' ? 1 : mobile ? 1.25 : 1.5);
  renderer.setPixelRatio(pixelRatio());
  renderer.setSize(innerWidth, innerHeight);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = .94;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x05090f);
  const camera = new THREE.PerspectiveCamera(35, innerWidth / innerHeight, .1, 220);
  camera.position.set(0, .65, 16);
  camera.lookAt(.35, .1, 0);
  const loadingManager = new THREE.LoadingManager();
  loadingManager.onLoad = () => { assetsReady = true; dirty = true; };
  loadingManager.onProgress = () => { dirty = true; };
  const loader = new THREE.TextureLoader(loadingManager);
  const anisotropy = Math.min(8, renderer.capabilities.getMaxAnisotropy());
  function sizeBackground() {
    const background = scene.background;
    if (!background.isTexture || !background.image) return;
    const imageAspect = background.image.width / background.image.height, aspect = innerWidth / innerHeight;
    if (aspect < imageAspect) { background.repeat.set(aspect / imageAspect, 1); background.offset.set((1 - background.repeat.x) / 2, 0); }
    else { background.repeat.set(1, imageAspect / aspect); background.offset.set(0, (1 - background.repeat.y) / 2); }
    background.repeat.multiplyScalar(.94);
    background.offset.set((1 - background.repeat.x) / 2, (1 - background.repeat.y) / 2);
    background.updateMatrix();
  }
  const backgroundAsset = mobile ? './assets/orbital-noir-mobile.webp' : './assets/orbital-noir.webp';
  loader.load(backgroundAsset, texture => { texture.colorSpace = THREE.SRGBColorSpace; texture.matrixAutoUpdate = true; scene.background = texture; scene.backgroundIntensity = 1.08; sizeBackground(); dirty = true; });

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
  key.shadow.mapSize.set(effectiveSettings().quality === 'efficient' ? 1024 : 2048, effectiveSettings().quality === 'efficient' ? 1024 : 2048);
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
  let modelLoaded = false;
  new GLTFLoader(loadingManager).load('./assets/models/spherex.glb', gltf => {
    const model = gltf.scene;
    model.updateMatrixWorld(true);
    const bounds = new THREE.Box3().setFromObject(model);
    const dimensions = bounds.getSize(new THREE.Vector3());
    const center = bounds.getCenter(new THREE.Vector3());
    const longest = Math.max(dimensions.x, dimensions.y, dimensions.z);
    if (!(longest > 0) || !Number.isFinite(longest)) { failedModel = true; dirty = true; console.warn('ORVYX: invalid model bounds, using fallback.'); return; }
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
    dirty = true;
  }, undefined, error => { console.warn('ORVYX: using the real-time 3D fallback.', error); document.body.dataset.model = 'fallback'; failedModel = true; dirty = true; });

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
  const stars = new THREE.Points(starGeo, new THREE.ShaderMaterial({
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, vertexColors: true,
    uniforms: { time: { value: 0 }, dpr: { value: renderer.getPixelRatio() } },
    vertexShader: `attribute float aSize;varying vec3 vC;uniform float time,dpr;void main(){vC=color;float tw=.85+.15*sin(time*.7+position.x*7.);gl_PointSize=aSize*dpr*tw;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);}`,
    fragmentShader: `varying vec3 vC;void main(){float d=length(gl_PointCoord-.5);float a=pow(smoothstep(.5,0.,d),1.7);gl_FragColor=vec4(vC,a*.8);}`,
  })); scene.add(stars);

  // ---------- An illustrative Earth horizon with surface relief and cloud shell ----------
  const horizon = new THREE.Group(); horizon.visible = false; scene.add(horizon);
  const earthMap = loader.load('./assets/earth.jpg'); earthMap.colorSpace = THREE.SRGBColorSpace; earthMap.anisotropy = anisotropy;
  const earthNormal = loader.load('./assets/earth-normal.jpg'); earthNormal.anisotropy = anisotropy;
  const cloudMap = loader.load('./assets/earth-clouds.png'); cloudMap.colorSpace = THREE.SRGBColorSpace; cloudMap.anisotropy = anisotropy;
  const earth = mesh(new THREE.SphereGeometry(28, 128, 80), new THREE.MeshPhysicalMaterial({ color: 0x7896bf, map: earthMap, normalMap: earthNormal, normalScale: new THREE.Vector2(.3, .3), roughness: .86, metalness: 0, clearcoat: .12, clearcoatRoughness: .7 }), horizon, false);
  earth.position.set(-.8, -33.5, -14); earth.rotation.set(-.9, -.65, .1);
  const clouds = mesh(new THREE.SphereGeometry(28.045, 96, 64), new THREE.MeshStandardMaterial({ color: 0x8d9db2, map: cloudMap, transparent: true, opacity: .36, depthWrite: false, roughness: 1 }), horizon, false);
  clouds.position.copy(earth.position); clouds.rotation.copy(earth.rotation); clouds.userData.skipAO = true;
  const earthAtmo = atmosphere(new THREE.SphereGeometry(28.14, 112, 64), 0x4373c1, .85);
  earthAtmo.position.copy(earth.position); earthAtmo.userData.skipAO = true; horizon.add(earthAtmo);
  const sunrise = glow(horizon, [-4.4, -6.95, -11.4], [6.8, 6.8, 1], new THREE.Color(3.0, 1.1, .35), .48);
  const sunriseCore = glow(horizon, [-4.4, -6.95, -11.2], [.7, .7, 1], new THREE.Color(7, 3.8, 1.6), .9);
  glow(horizon, [-4.4, -6.95, -11.0], [11, .055, 1], new THREE.Color(1.6, .9, .45), .5);

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
  const gasTexture = canvasTexture(1024, 512, (ctx, w, h) => {
    const n = noise(42), image = ctx.createImageData(w, h), palette = [[22, 21, 48], [60, 38, 96], [134, 64, 130], [228, 142, 126], [250, 201, 157], [110, 151, 203]];
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      const turbulence = fbm(n, x / 145, y / 48) * .105 + Math.sin(x / w * 6.28318 + y / h * 7) * .045;
      const band = (.5 + .5 * Math.sin((y / h + turbulence) * 42)) * .75 + fbm(n, x / 170, y / 90, 3) * .25;
      const index = Math.min(4, Math.floor(band * 5)), blend = band * 5 - index, shade = .86 + fbm(n, x / 35, y / 30, 3) * .25;
      const p = (y * w + x) * 4;
      for (let channel = 0; channel < 3; channel++) image.data[p + channel] = (palette[index][channel] * (1 - blend) + palette[index + 1][channel] * blend) * shade;
      image.data[p + 3] = 255;
    }
    ctx.putImageData(image, 0, 0);
  }, true);
  const planet = new THREE.Group(); scene.add(planet);
  const planetBody = mesh(new THREE.SphereGeometry(1.7, 112, 80), new THREE.MeshPhysicalMaterial({ map: gasTexture, roughness: .24, metalness: .42, clearcoat: 1, clearcoatRoughness: .13, envMapIntensity: 1.5 }), planet);
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

  // ---------- Observation glass plates. Deliberately simulated, never invented data. ----------
  const observations = new THREE.Group(); scene.add(observations);
  const observationMovers = [];
  for (let k = 0; k < 3; k++) {
    const plate = new THREE.Group(); plate.position.set((k - 1) * .62, (k - 1) * .23, -k * .8); plate.rotation.set(.04, -.3, .04); observations.add(plate);
    const geometry = new THREE.PlaneGeometry(3.25, 3.25);
    const glass = mesh(geometry, new THREE.MeshPhysicalMaterial({ color: 0x708aa5, metalness: .18, roughness: .25, transparent: true, opacity: .065, side: THREE.DoubleSide, depthWrite: false }), plate, false);
    glass.userData.skipAO = true;
    const outline = new THREE.LineSegments(new THREE.EdgesGeometry(geometry), new THREE.LineBasicMaterial({ color: k === 2 ? 0xd3b493 : 0x8298b0, transparent: true, opacity: k === 2 ? .6 : .38 })); plate.add(outline);
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

  // ---------- Cosmic Narrator: an opalescent, gyroscopic celestial sculpture ----------
  const narrator = new THREE.Group(); scene.add(narrator);
  const core = new THREE.Group(); narrator.add(core);
  const coreTexture = canvasTexture(512, 256, (ctx, w, h) => {
    const n = noise(37), image = ctx.createImageData(w, h);
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) { const value = fbm(n, x / 55, y / 55, 4), vein = Math.pow(Math.abs(Math.sin(x / 44 + value * 13 + y / 67)), 16); const p = (y * w + x) * 4; image.data[p] = 26 + value * 26 + vein * 80; image.data[p + 1] = 30 + value * 28 + vein * 55; image.data[p + 2] = 44 + value * 34 + vein * 24; image.data[p + 3] = 255; }
    ctx.putImageData(image, 0, 0);
  }, true);
  const coreMaterial = new THREE.MeshPhysicalMaterial({ map: coreTexture, bumpMap: coreTexture, bumpScale: .008, emissiveMap: coreTexture, emissive: 0x485574, emissiveIntensity: .25, color: 0x9fa8c3, metalness: .62, roughness: .18, clearcoat: 1, clearcoatRoughness: .12, iridescence: .5, iridescenceIOR: 1.3, iridescenceThicknessRange: [120, 330], envMapIntensity: 1.5 });
  mesh(new THREE.SphereGeometry(1.16, 96, 64), coreMaterial, core, false);
  const narratorFilaments = [];
  for (let k = 0; k < 28; k++) {
    const points = [], latitude = -1.15 + k / 27 * 2.3, phase = k * 2.399963;
    for (let j = 0; j <= 110; j++) { const u = j / 110 * Math.PI * 2, lat = latitude + .14 * Math.sin(3 * u + phase), r = 1.18 + .018 * Math.sin(4 * u + phase); points.push(new THREE.Vector3(r * Math.cos(lat) * Math.cos(u), r * Math.sin(lat), r * Math.cos(lat) * Math.sin(u))); }
    const material = new THREE.MeshBasicMaterial({ color: new THREE.Color(k % 7 === 0 ? 0x38bdf8 : 0xc6ab8c).multiplyScalar(1.4), transparent: true, opacity: .5, blending: THREE.AdditiveBlending, depthWrite: false });
    const filament = mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(points), 115, k % 3 ? .004 : .009, 5, false), material, core, false); filament.userData.skipAO = true; narratorFilaments.push(material);
  }
  const narratorRings = [];
  const orbitMaterial = new THREE.MeshPhysicalMaterial({ color: 0xc6ab8c, metalness: .9, roughness: .25, clearcoat: .4 });
  for (let k = 0; k < 4; k++) {
    const ring = mesh(new THREE.TorusGeometry(1.48 + k * .18, .012 + k * .001, 12, 180, k === 3 ? Math.PI * 1.72 : Math.PI * 2), orbitMaterial, narrator, false);
    ring.rotation.set(.7 + k * .54, .35 + k * .28, k * .64); narratorRings.push(ring);
  }
  const dustPositions = [], dustColors = [];
  for (let k = 0; k < 180; k++) { const phi = Math.acos(1 - 2 * (k + .5) / 180), theta = k * 2.399963, r = 1.63 + (k % 7) * .075; dustPositions.push(r * Math.sin(phi) * Math.cos(theta), r * Math.cos(phi), r * Math.sin(phi) * Math.sin(theta)); dustColors.push(.7 + random() * .3, .57 + random() * .2, .43 + random() * .3); }
  const dustGeometry = new THREE.BufferGeometry(); dustGeometry.setAttribute('position', new THREE.Float32BufferAttribute(dustPositions, 3)); dustGeometry.setAttribute('color', new THREE.Float32BufferAttribute(dustColors, 3));
  const narratorDust = new THREE.Points(dustGeometry, new THREE.PointsMaterial({ map: pointTexture, vertexColors: true, size: .035, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending })); narrator.add(narratorDust);
  glow(narrator, [0, 0, -.5], [5, 5, 1], 0x525a8d, .18);

  // ---------- One cinematic pipeline, with user-adjustable finishing ----------
  const effects = createSpherexEffects(renderer, scene, camera, effectiveSettings());
  let progress = window.ORVYX_SCROLL || 0, currentProgress = progress;
  const desktopFrames = [
    { cam: [0, 1.1, 20], look: [0, .5, 0], tel: [0, -.55, -2.5], ts: 0, rot: [.62, -.18, .12], planet: [9, 0, -8], ps: 0, obs: [9, 0, -4], os: 0, narr: [3.4, .1, 0], ns: 0 },
    { cam: [0, .65, 16], look: [.35, .1, 0], tel: [3.3, -.15, 0], ts: .94, rot: [.60, -.48, .20], planet: [9, 0, -8], ps: 0, obs: [9, 0, -4], os: 0, narr: [3.4, .1, 0], ns: 0 },
    { cam: [-.6, 1.4, 13.8], look: [.7, .1, 0], tel: [3.25, .35, 0], ts: 1.03, rot: [.76, .22, -.15], planet: [9, 0, -8], ps: 0, obs: [9, 0, -4], os: 0, narr: [3.4, .1, 0], ns: 0 },
    { cam: [0, .2, 17], look: [0, 0, 0], tel: [11, -1, -12], ts: 0, rot: [.4, 1.1, .5], planet: [-3.3, .15, 0], ps: 1.34, obs: [9, 0, -4], os: 0, narr: [3.4, .1, 0], ns: 0 },
    { cam: [0, .2, 17], look: [0, 0, 0], tel: [11, -1, -12], ts: 0, rot: [.4, 1.7, .4], planet: [-10, 0, -8], ps: 0, obs: [3.35, .1, 0], os: 1.36, narr: [3.4, .1, 0], ns: 0 },
    { cam: [0, .2, 17], look: [0, 0, 0], tel: [11, -1, -12], ts: 0, rot: [.4, 1.7, .4], planet: [-10, 0, -8], ps: 0, obs: [9, 0, -5], os: 0, narr: [3.4, .1, 0], ns: 1.58 }
  ];
  const mobileFrames = [
    { cam: [0, .4, 19], look: [0, .3, 0], tel: [0, 2.3, -3], ts: 0, rot: [.62, -.3, .18], planet: [9, 0, -8], ps: 0, obs: [9, 0, -4], os: 0, narr: [0, 2.6, 0], ns: 0 },
    { cam: [0, .3, 18], look: [0, .1, 0], tel: [.72, 2.55, -1], ts: .46, rot: [.62, -.48, .22], planet: [9, 0, -8], ps: 0, obs: [9, 0, -4], os: 0, narr: [0, 2.6, 0], ns: 0 },
    { cam: [0, .3, 18], look: [0, .1, 0], tel: [0, 2.4, -.5], ts: .64, rot: [.78, .2, -.14], planet: [9, 0, -8], ps: 0, obs: [9, 0, -4], os: 0, narr: [0, 2.6, 0], ns: 0 },
    { cam: [0, .2, 18], look: [0, 0, 0], tel: [8, 0, -8], ts: 0, rot: [.4, 1.1, .5], planet: [0, 2.7, 0], ps: .61, obs: [9, 0, -4], os: 0, narr: [0, 2.6, 0], ns: 0 },
    { cam: [0, .2, 18], look: [0, 0, 0], tel: [8, 0, -8], ts: 0, rot: [.4, 1.7, .4], planet: [-8, 0, -8], ps: 0, obs: [0, 2.8, 0], os: .72, narr: [0, 2.6, 0], ns: 0 },
    { cam: [0, .2, 18], look: [0, 0, 0], tel: [8, 0, -8], ts: 0, rot: [.4, 1.7, .4], planet: [-8, 0, -8], ps: 0, obs: [8, 0, -4], os: 0, narr: [0, 2.7, 0], ns: .95 }
  ];
  const lerp = THREE.MathUtils.lerp;
  const vector = new THREE.Vector3();
  function blendVector(a, b, t) { return vector.set(lerp(a[0], b[0], t), lerp(a[1], b[1], t), lerp(a[2], b[2], t)); }
  function place(object, aPos, bPos, aScale, bScale, t) { object.position.copy(blendVector(aPos, bPos, t)); const scale = Math.max(.0001, lerp(aScale, bScale, t)); object.scale.setScalar(scale); object.visible = scale > .005; }
  const pointer = new THREE.Vector2(), pointerCurrent = new THREE.Vector2();
  let orbitOffset = 0, orbitCurrent = 0, dragging = false, dragX = 0, dragged = false;
  const interaction = document.querySelector('#objectInteraction');
  function release() { dragging = false; interaction?.classList.remove('dragging'); }
  if (interaction) {
    interaction.addEventListener('pointerdown', e => { if (e.target.closest('button')) return; if (e.pointerType === 'touch') return; dragging = true; dragged = false; dragX = e.clientX; interaction.setPointerCapture(e.pointerId); interaction.classList.add('dragging'); });
    interaction.addEventListener('pointermove', e => { if (!dragging) return; const dx = e.clientX - dragX; if (Math.abs(dx) > 2) dragged = true; orbitOffset += dx * .009; dragX = e.clientX; dirty = true; });
    interaction.addEventListener('pointerup', release); interaction.addEventListener('pointercancel', release);
  }
  document.querySelector('#orbitButton')?.addEventListener('click', () => { orbitOffset += Math.PI / 3; dirty = true; });
  window.addEventListener('pointermove', e => { pointer.set((e.clientX / innerWidth - .5) * 2, (e.clientY / innerHeight - .5) * 2); }, { passive: true });
  window.addEventListener('orvyx:scroll', e => { progress = Math.max(0, Math.min(5, e.detail)); dirty = true; });
  window.addEventListener('orvyx:visuals', e => {
    const oldQuality = settings.quality;
    settings = { ...settings, ...e.detail };
    effects.setSettings(effectiveSettings());
    if (oldQuality !== settings.quality) resize(); dirty = true;
  });
  function resize() {
    mobile = innerWidth <= 700;
    camera.aspect = innerWidth / innerHeight; camera.updateProjectionMatrix();
    sizeBackground();
    renderer.setPixelRatio(pixelRatio()); renderer.setSize(innerWidth, innerHeight);
    effects.resize(innerWidth, innerHeight, renderer.getPixelRatio());
    stars.material.uniforms.dpr.value = renderer.getPixelRatio();
    const shadowSize = effectiveSettings().quality === 'efficient' ? 1024 : 2048;
    if (key.shadow.mapSize.x !== shadowSize) {
      key.shadow.mapSize.set(shadowSize, shadowSize);
      if (key.shadow.map) { key.shadow.map.dispose(); key.shadow.map = null; }
      key.shadow.needsUpdate = true;
    } dirty = true;
  }
  window.addEventListener('resize', resize);
  window.addEventListener('orientationchange', resize);
  document.addEventListener('visibilitychange', () => { dirty = true; });
  canvas.addEventListener('webglcontextlost', e => { e.preventDefault(); ready(false); });
  canvas.addEventListener('webglcontextrestored', () => location.reload());
  const clock = new THREE.Clock(); let elapsed = 0, frames = 0, lastFrame = 0;
  function tick(now) {
    requestAnimationFrame(tick);
    if ((!assetsReady && !failedModel) || document.hidden || now - lastFrame < 32) return;
    const moving = Math.abs(progress - currentProgress) > .002 || Math.abs(orbitOffset - orbitCurrent) > .002;
    if (!settings.motion && !dirty && !moving) return;
    lastFrame = now;
    const dt = Math.min(clock.getDelta(), .065);
    dirty = false;
    if (settings.motion) elapsed += dt;
    const smooth = 1 - Math.exp(-dt * 6.5);
    const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
    const efficientAuto = softwareRenderer && settings.quality === 'auto';
    currentProgress = reduced ? Math.round(progress) : efficientAuto ? progress : lerp(currentProgress, progress, smooth);
    const frameSet = mobile ? mobileFrames : desktopFrames;
    const index = Math.min(Math.floor(currentProgress), frameSet.length - 2), fraction = THREE.MathUtils.smoothstep(currentProgress - index, 0, 1);
    const a = frameSet[index], b = frameSet[index + 1];
    camera.position.copy(blendVector(a.cam, b.cam, fraction));
    pointerCurrent.lerp(settings.motion && !mobile ? pointer : new THREE.Vector2(), smooth * .5);
    camera.position.x += pointerCurrent.x * .08; camera.position.y -= pointerCurrent.y * .045;
    camera.lookAt(blendVector(a.look, b.look, fraction));
    place(telescope, a.tel, b.tel, a.ts, b.ts, fraction);
    orbitCurrent = efficientAuto ? orbitOffset : lerp(orbitCurrent, orbitOffset, 1 - Math.exp(-dt * 8));
    const ambient = settings.motion ? Math.sin(elapsed * .25) * .045 : 0;
    telescope.rotation.set(lerp(a.rot[0], b.rot[0], fraction) + ambient * .25, lerp(a.rot[1], b.rot[1], fraction) + ambient + orbitCurrent, lerp(a.rot[2], b.rot[2], fraction));
    place(planet, a.planet, b.planet, a.ps, b.ps, fraction);
    place(observations, a.obs, b.obs, a.os, b.os, fraction);
    place(narrator, a.narr, b.narr, a.ns, b.ns, fraction);
    if (settings.motion) {
      planetBody.rotation.y += dt * .025;
      core.rotation.y += dt * .08;
      narratorRings.forEach((ring, k) => ring.rotation.z += dt * .025 * (k % 2 ? -1 : 1));
      narratorDust.rotation.y -= dt * .035;
      clouds.rotation.y += dt * .001;
    }
    const openNarrator = document.querySelector('#narratorButton')?.getAttribute('aria-expanded') === 'true' || document.querySelector('#narrator')?.classList.contains('demo-open');
    narratorFilaments.forEach((mat, k) => { mat.opacity = (openNarrator ? .7 : .45) + (settings.motion ? Math.sin(elapsed * .6 + k * .18) * .045 : 0); });
    const horizonVisibility = 1 - THREE.MathUtils.smoothstep(currentProgress, .3, 1.45);
    horizon.visible = false; // No Earth in the opening scene.
    horizon.position.y = -9 * (1 - horizonVisibility);
    const ribbonVisibility = 1 - THREE.MathUtils.smoothstep(currentProgress, 1.35, 2.75);
    ribbons.visible = ribbonVisibility > .01;
    ribbonMaterials.forEach(mat => { mat.uniforms.opacity.value = .24 * ribbonVisibility * (mobile ? .6 : 1); mat.uniforms.time.value = elapsed; });
    filamentMaterials.forEach(mat => { mat.uniforms.opacity.value = .40 * ribbonVisibility * (mobile ? .6 : 1); });
    telescopeFlare.visible = currentProgress > .25 && currentProgress < 2.3;
    const flareIn = THREE.MathUtils.smoothstep(currentProgress, .35, 1.05) * (1 - THREE.MathUtils.smoothstep(currentProgress, 1.55, 2.2));
    telescopeFlare.children.forEach((object, k) => { object.material.opacity = [.33, .85, .4][k] * flareIn; });
    skyOrbits.visible = currentProgress > .3 && currentProgress < 2.8;
    skyOrbits.rotation.z = settings.motion ? elapsed * .002 : 0;
    stars.material.uniforms.time.value = elapsed;
    stars.rotation.y = settings.motion ? elapsed * .00065 : stars.rotation.y;
    // Drift the cropped background texture with scroll and subtle ambient motion.
    if (scene.background && scene.background.isTexture && scene.background.image) {
      const bg = scene.background;
      const availableX = Math.max(0, 1 - bg.repeat.x), availableY = Math.max(0, 1 - bg.repeat.y);
      bg.offset.x = availableX * (.5 + .18 * Math.sin(currentProgress * .45 + (settings.motion ? elapsed * .025 : 0)));
      bg.offset.y = availableY * (.5 + .14 * Math.sin(currentProgress * .55));
      bg.updateMatrix();
    }
    effects.render(dt, elapsed);
    frames++;
    if (!sceneAnnounced && (modelLoaded || failedModel)) { sceneAnnounced = true; ready(true, modelLoaded); }
    window.ORVYX_DIAGNOSTICS = { webgl: true, modelLoaded, progress: Number(currentProgress.toFixed(3)), drawCalls: renderer.info.render.calls, triangles: renderer.info.render.triangles, pixelRatio: renderer.getPixelRatio(), cinematic: settings.enabled, softwareRenderer, frames };
  }
  requestAnimationFrame(tick);
}

}
// Give the local first-frame poster and typography a paint before GPU setup.
requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(initScene, 60)));
