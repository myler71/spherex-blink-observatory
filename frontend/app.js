(() => {
  'use strict';
  document.documentElement.classList.add('js');
  const $ = (selector) => document.querySelector(selector);
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
  const defaults = { enabled: true, bloom: 35, grain: 18, quality: 'auto', motion: !reducedMotion.matches, motionOverride: false };
  let stored = {};
  try { stored = JSON.parse(localStorage.getItem('orvyx-visual-studio-v1') || '{}'); } catch (_) {}
  let settings = { ...defaults, ...stored };
  settings.bloom = Math.max(0, Math.min(100, Number(settings.bloom) || 0));
  settings.grain = Math.max(0, Math.min(100, Number(settings.grain) || 0));
  settings.quality = ['auto', 'high', 'efficient'].includes(settings.quality) ? settings.quality : 'auto';
  settings.enabled = Boolean(settings.enabled);
  settings.motion = reducedMotion.matches ? false : Boolean(settings.motion);
  let comparing = false;
  const panel = $('#visualPanel'), toggle = $('#visualToggle');
  let panelOpener = toggle;

  function updateUI() {
    $('#finishToggle').checked = settings.enabled;
    $('#atmosphereRange').value = settings.bloom;
    $('#grainRange').value = settings.grain;
    $('#atmosphereValue').textContent = `${settings.bloom}%`;
    $('#grainValue').textContent = `${settings.grain}%`;
    $('#atmosphereRange').style.setProperty('--range-progress', `${settings.bloom}%`);
    $('#grainRange').style.setProperty('--range-progress', `${settings.grain}%`);
    $('#qualitySelect').value = settings.quality;
    $('#motionToggle').checked = settings.motion;
    document.body.classList.toggle('finish-disabled', !settings.enabled || comparing);
    $('#lookStatus').textContent = comparing ? 'RAW' : settings.enabled ? 'ON' : 'OFF';
    $('#lookName').textContent = comparing ? 'Original render' : 'Cinematic finish';
    $('#compareLook').classList.toggle('comparing', comparing);
    $('#compareLook').textContent = comparing ? 'Original render' : 'Hold to compare';
    document.documentElement.style.setProperty('--grain-opacity', settings.enabled && !comparing ? settings.grain / 750 : 0);
    document.querySelectorAll('.range-setting').forEach(el => el.classList.toggle('disabled', !settings.enabled));
    $('#atmosphereRange').disabled = !settings.enabled;
    $('#grainRange').disabled = !settings.enabled;
  }

  function applySettings(persist = true) {
    const current = { ...settings, enabled: settings.enabled && !comparing };
    window.ORVYX_SETTINGS = current;
    updateUI();
    window.dispatchEvent(new CustomEvent('orvyx:visuals', { detail: current }));
    if (persist) try { localStorage.setItem('orvyx-visual-studio-v1', JSON.stringify(settings)); } catch (_) {}
  }

  function openPanel(opener = toggle) {
    panelOpener = opener;
    panel.hidden = false;
    toggle.setAttribute('aria-expanded', 'true');
    $('#closeVisual').focus({ preventScroll: true });
  }
  function closePanel(restoreFocus = true) {
    panel.hidden = true;
    toggle.setAttribute('aria-expanded', 'false');
    endCompare();
    if (restoreFocus) panelOpener.focus({ preventScroll: true });
  }
  toggle.addEventListener('click', () => panel.hidden ? openPanel(toggle) : closePanel());
  $('#heroLookButton').addEventListener('click', () => panel.hidden ? openPanel($('#heroLookButton')) : closePanel());
  $('#closeVisual').addEventListener('click', () => closePanel());
  document.addEventListener('pointerdown', e => {
    if (!panel.hidden && !panel.contains(e.target) && !$('#visualDock').contains(e.target) && !$('#heroLookButton').contains(e.target)) closePanel(false);
  });
  $('#finishToggle').addEventListener('change', e => { settings.enabled = e.target.checked; applySettings(); });
  $('#atmosphereRange').addEventListener('input', e => { settings.bloom = Number(e.target.value); applySettings(); });
  $('#grainRange').addEventListener('input', e => { settings.grain = Number(e.target.value); applySettings(); });
  $('#qualitySelect').addEventListener('change', e => { settings.quality = e.target.value; applySettings(); });
  $('#motionToggle').addEventListener('change', e => { settings.motion = e.target.checked; settings.motionOverride = true; applySettings(); });
  $('#resetLook').addEventListener('click', () => {
    settings = { ...defaults };
    comparing = false;
    applySettings();
    $('#announcer').textContent = 'The original ORVYX cinematic finish has been restored.';
  });
  function startCompare() { comparing = true; applySettings(false); }
  function endCompare() { if (!comparing) return; comparing = false; applySettings(false); }
  const compareButton = $('#compareLook');
  compareButton.addEventListener('pointerdown', e => { e.preventDefault(); compareButton.setPointerCapture(e.pointerId); startCompare(); });
  compareButton.addEventListener('pointerup', endCompare);
  compareButton.addEventListener('pointercancel', endCompare);
  compareButton.addEventListener('lostpointercapture', endCompare);
  compareButton.addEventListener('keydown', e => { if (e.code === 'Space' || e.code === 'Enter') { e.preventDefault(); startCompare(); } });
  compareButton.addEventListener('keyup', e => { if (e.code === 'Space' || e.code === 'Enter') { e.preventDefault(); endCompare(); } });
  compareButton.addEventListener('blur', endCompare);
  window.addEventListener('blur', endCompare);

  const menuButton = $('#menuButton'), mobileNav = $('#mobileNav');
  function closeMenu() { mobileNav.hidden = true; menuButton.setAttribute('aria-expanded', 'false'); menuButton.setAttribute('aria-label', 'Open navigation'); }
  menuButton.addEventListener('click', () => {
    const open = mobileNav.hidden;
    mobileNav.hidden = !open;
    menuButton.setAttribute('aria-expanded', String(open));
    menuButton.setAttribute('aria-label', open ? 'Close navigation' : 'Open navigation');
  });
  mobileNav.querySelectorAll('a').forEach(a => a.addEventListener('click', closeMenu));
  document.addEventListener('pointerdown', e => { if (!mobileNav.hidden && !mobileNav.contains(e.target) && !menuButton.contains(e.target)) closeMenu(); });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') { if (!panel.hidden) closePanel(); closeMenu(); }
  });

  const explorerDialog = $('#explorerDialog'), creditsDialog = $('#creditsDialog');
  document.querySelectorAll('[data-explorer]').forEach(button => button.addEventListener('click', () => { closePanel(false); explorerDialog.showModal(); }));
  $('#creditsButton').addEventListener('click', () => creditsDialog.showModal());
  document.querySelectorAll('[data-close-dialog]').forEach(button => button.addEventListener('click', () => button.closest('dialog').close()));
  document.querySelectorAll('dialog').forEach(dialog => dialog.addEventListener('click', e => {
    const rect = dialog.getBoundingClientRect();
    if (e.target === dialog && (e.clientX < rect.left || e.clientX > rect.right || e.clientY < rect.top || e.clientY > rect.bottom)) dialog.close();
  }));
  $('#narratorButton').addEventListener('click', () => {
    const demo = $('#narratorDemo'), open = demo.hidden;
    demo.hidden = !open;
    $('#narratorButton').setAttribute('aria-expanded', String(open));
    $('#narratorButton').firstChild.textContent = open ? 'Close the preview ' : 'Meet your guide ';
    $('#narrator').classList.toggle('demo-open', open);
    requestAnimationFrame(updateScroll);
  });
  $('#narratorForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const answer = $('#narratorAnswer');
    const button = form.querySelector('button[type="submit"]');
    const observation = $('#observationId').value.trim();
    const question = $('#narratorQuestion').value.trim();
    button.disabled = true;
    answer.textContent = 'Retrieving observation evidence and preparing an answer…';
    document.getElementById('narratorSources')?.remove();
    try {
      const apiOrigin = window.ORVYX_API_ORIGIN || new URLSearchParams(location.search).get('api_origin') || (location.port === '8000' ? location.origin : 'http://127.0.0.1:8000');
      const response = await fetch(`${apiOrigin.replace(/\/$/, '')}/api/v1/observe/${encodeURIComponent(observation)}/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error?.message || `Backend returned ${response.status}`);
      answer.textContent = result.answer;
      if (result.sources?.length) {
        const list = document.createElement('ul');
        list.id = 'narratorSources';
        list.setAttribute('aria-label', 'Retrieved NASA sources');
        for (const source of result.sources) {
          const item = document.createElement('li');
          const link = document.createElement('a');
          link.href = source.url;
          link.target = '_blank';
          link.rel = 'noopener noreferrer';
          link.textContent = source.source_name;
          item.append(link);
          list.append(item);
        }
        answer.after(list);
      }
    } catch (error) {
      answer.textContent = `Could not answer: ${error.message}`;
    } finally {
      button.disabled = false;
    }
  });


  const sections = [...document.querySelectorAll('[data-scene]')];
  const chapterLinks = [...document.querySelectorAll('.chapter')];
  let ticking = false;
  function updateScroll() {
    ticking = false;
    const centers = sections.map(s => s.offsetTop + s.offsetHeight / 2);
    const center = scrollY + innerHeight / 2;
    let i = 0;
    while (i < centers.length - 2 && center > centers[i + 1]) i++;
    const fraction = Math.max(0, Math.min(1, (center - centers[i]) / (centers[i + 1] - centers[i])));
    const progress = i + fraction;
    const nearest = Math.round(progress);
    chapterLinks.forEach((link, n) => { link.classList.toggle('active', n === nearest); if (n === nearest) link.setAttribute('aria-current', 'step'); else link.removeAttribute('aria-current'); });
    $('#readingProgress').style.transform = `scaleX(${Math.max(0, Math.min(1, scrollY / (document.documentElement.scrollHeight - innerHeight)))})`;
    document.documentElement.style.setProperty('--scene-progress', progress.toFixed(3));
    document.body.dataset.chapter = nearest;
    // Opening slide exit: the logo lifts away and the telescope picture
    // zooms + dissolves while the real 3D telescope grows in behind it.
    const intro = sections[0];
    if (intro && intro.classList.contains('intro-section')) {
      const rect = intro.getBoundingClientRect();
      const exit = Math.max(0, Math.min(1, -rect.top / (innerHeight * .75)));
      intro.style.setProperty('--exit', exit.toFixed(3));
      const introCopy = intro.querySelector('.intro-copy');
      if (introCopy) introCopy.style.pointerEvents = exit > .55 ? 'none' : '';
      const introScroll = intro.querySelector('.intro-scroll');
      if (introScroll) introScroll.style.pointerEvents = exit > .3 ? 'none' : '';
    }
    window.ORVYX_SCROLL = progress;
    window.dispatchEvent(new CustomEvent('orvyx:scroll', { detail: progress }));
  }
  window.addEventListener('scroll', () => { if (!ticking) { ticking = true; requestAnimationFrame(updateScroll); } }, { passive: true });
  window.addEventListener('resize', () => { updateScroll(); if (!document.body.classList.contains('scene-fallback')) $('#orbitButton span').textContent = innerWidth <= 700 ? 'TAP TO ORBIT' : 'DRAG TO ORBIT'; });
  $('#orbitButton span').textContent = innerWidth <= 700 ? 'TAP TO ORBIT' : 'DRAG TO ORBIT';
  const observer = new IntersectionObserver(entries => entries.forEach(entry => { if (entry.isIntersecting) entry.target.classList.add('is-visible'); }), { threshold: 0.12 });
  document.querySelectorAll('.reveal').forEach(el => observer.observe(el));
  const resizeObserver = new ResizeObserver(updateScroll);
  sections.forEach(section => resizeObserver.observe(section));
  window.addEventListener('orvyx:performance', e => {
    if (e.detail.reducedAmbient && !settings.motionOverride && settings.quality === 'auto') { settings.motion = false; defaults.motion = false; applySettings(false); }
  });
  window.addEventListener('orvyx:ready', e => {
    document.body.classList.toggle('scene-ready', e.detail.webgl);
    document.body.classList.toggle('scene-fallback', !e.detail.webgl);
    $('#orbitButton').disabled = !e.detail.webgl;
    $('#orbitButton span').textContent = e.detail.webgl ? innerWidth <= 700 ? 'TAP TO ORBIT' : 'DRAG TO ORBIT' : 'STATIC PREVIEW';
    if (!e.detail.webgl) {
      $('#objectInteraction').setAttribute('aria-label', 'Static preview of the artistic SPHEREx model. WebGL is unavailable.');
      ['finishToggle','atmosphereRange','grainRange','qualitySelect','motionToggle','compareLook','resetLook'].forEach(id => { document.getElementById(id).disabled = true; });
      $('.panel-footnote').textContent = 'Static preview. Live visual controls require a browser with WebGL.';
    }
    $('#renderStatus').textContent = e.detail.webgl ? 'REAL-TIME 3D' : 'STATIC PREVIEW';
  });
  reducedMotion.addEventListener('change', e => { if (e.matches) { settings.motion = false; applySettings(); } });
  applySettings(false);
  updateScroll();
  window.ORVYX = { getSettings: () => ({ ...settings }), getProgress: () => window.ORVYX_SCROLL, openVisualStudio: () => openPanel(toggle) };
})();

// A restrained parallax drift on original editorial imagery; no scroll hijacking.
(() => {
  const layers = [...document.querySelectorAll('[data-parallax]')];
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  let pending = false;
  function renderParallax() {
    pending = false;
    if (reduced.matches) { layers.forEach(el => el.style.transform = ''); return; }
    for (const layer of layers) {
      const rect = layer.parentElement.getBoundingClientRect();
      if (rect.bottom < 0 || rect.top > innerHeight) continue;
      const distance = (innerHeight / 2 - (rect.top + rect.height / 2)) * .065;
      layer.style.transform = `translate3d(0,${Math.max(-55, Math.min(55,distance))}px,0) scale(1.03)`;
    }
  }
  addEventListener('scroll', () => { if (!pending) {pending = true; requestAnimationFrame(renderParallax);} }, {passive:true});
  addEventListener('resize', renderParallax);
  renderParallax();
})();
