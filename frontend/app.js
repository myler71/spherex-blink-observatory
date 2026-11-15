import { getStoryState } from './story-state.js';

(() => {
  'use strict';
  document.documentElement.classList.add('js');
  const $ = (selector) => document.querySelector(selector);
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
  const defaults = { enabled: true, bloom: 40, grain: 30, quality: 'auto', motion: !reducedMotion.matches, motionOverride: false };
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
  const nativePopover = Boolean(panel && typeof panel.showPopover === 'function');
  if (panel && !nativePopover) panel.hidden = true;
  let restorePanelFocus = true;
  const panelOpen = () => nativePopover ? panel.matches(':popover-open') : !panel.hidden;
  let panelOpener = toggle;

  function updateUI() {
    document.body.classList.toggle('finish-disabled', !settings.enabled || comparing);
    document.body.classList.toggle('ambient-paused', !settings.motion || reducedMotion.matches);
    document.documentElement.style.setProperty('--grain-opacity', settings.enabled && !comparing ? Math.min(.035, settings.grain / 1500) : 0);
    if (!panel || !toggle) return;
    $('#finishToggle').checked = settings.enabled;
    $('#atmosphereRange').value = settings.bloom;
    $('#grainRange').value = settings.grain;
    $('#atmosphereValue').textContent = `${settings.bloom}%`;
    $('#grainValue').textContent = `${settings.grain}%`;
    $('#atmosphereRange').style.setProperty('--range-progress', `${settings.bloom}%`);
    $('#grainRange').style.setProperty('--range-progress', `${settings.grain}%`);
    $('#qualitySelect').value = settings.quality;
    $('#motionToggle').checked = settings.motion;
    $('#motionToggle').disabled = reducedMotion.matches || document.body.classList.contains('scene-fallback');
    $('#motionNote').textContent = reducedMotion.matches ? 'Disabled by your reduced-motion preference.' : '';
    $('#lookStatus').textContent = comparing ? 'RAW' : settings.enabled ? 'ON' : 'OFF';
    $('#lookName').textContent = comparing ? 'Original render' : 'Cinematic finish';
    $('#compareLook').classList.toggle('comparing', comparing);
    $('#compareLook').textContent = comparing ? 'Original render' : 'Hold to compare';
    document.querySelectorAll('.range-setting').forEach(el => el.classList.toggle('disabled', !settings.enabled));
    $('#atmosphereRange').disabled = !settings.enabled;
    $('#grainRange').disabled = !settings.enabled;
  }

  function applySettings(persist = true, resetAuto = false) {
    const current = { ...settings, enabled: settings.enabled && !comparing };
    window.ORVYX_SETTINGS = current;
    updateUI();
    window.dispatchEvent(new CustomEvent('orvyx:visuals', { detail: { ...current, resetAuto } }));
    if (persist) try { localStorage.setItem('orvyx-visual-studio-v1', JSON.stringify(settings)); } catch (_) {}
  }

  function openPanel(opener = toggle) {
    if (!panel || !toggle) return;
    panelOpener = opener;
    restorePanelFocus = true;
    if (nativePopover) { if (!panelOpen()) panel.showPopover(); }
    else { panel.hidden = false; toggle.setAttribute('aria-expanded', 'true'); $('#closeVisual')?.focus({ preventScroll: true }); }
  }
  function closePanel(restoreFocus = true) {
    if (!panel || !toggle) return;
    restorePanelFocus = restoreFocus;
    if (nativePopover) { if (panelOpen()) panel.hidePopover(); }
    else { panel.hidden = true; toggle.setAttribute('aria-expanded', 'false'); endCompare(); if (restoreFocus && panelOpener) panelOpener.focus({ preventScroll: true }); }
  }
  function startCompare() { comparing = true; applySettings(false); }
  function endCompare() { if (!comparing) return; comparing = false; applySettings(false); }
  if (panel && toggle) {
    if (nativePopover) {
      panel.addEventListener('toggle', event => {
        const open = event.newState === 'open';
        toggle.setAttribute('aria-expanded', String(open));
        if (open) { panelOpener = document.activeElement === toggle ? toggle : panelOpener; $('#closeVisual')?.focus({ preventScroll: true }); }
        else { endCompare(); if (restorePanelFocus && panelOpener) panelOpener.focus({ preventScroll: true }); restorePanelFocus = true; }
      });
    } else {
      toggle.addEventListener('click', () => panel.hidden ? openPanel(toggle) : closePanel());
      $('#closeVisual')?.addEventListener('click', () => closePanel());
      document.addEventListener('pointerdown', e => { if (!panel.hidden && !panel.contains(e.target) && !$('#visualDock')?.contains(e.target)) closePanel(false); });
    }
    $('#heroLookButton')?.addEventListener('click', () => panelOpen() ? closePanel() : openPanel($('#heroLookButton')));
    $('#finishToggle')?.addEventListener('change', e => { settings.enabled = e.target.checked; applySettings(); });
    $('#atmosphereRange')?.addEventListener('input', e => { settings.bloom = Number(e.target.value); applySettings(); });
    $('#grainRange')?.addEventListener('input', e => { settings.grain = Number(e.target.value); applySettings(); });
    $('#qualitySelect')?.addEventListener('change', e => { settings.quality = e.target.value; applySettings(true, settings.quality === 'auto'); });
    $('#motionToggle')?.addEventListener('change', e => { settings.motion = e.target.checked; settings.motionOverride = true; applySettings(); });
    $('#resetLook')?.addEventListener('click', () => {
      settings = { ...defaults };
      comparing = false;
      applySettings(true, true);
      if ($('#announcer')) $('#announcer').textContent = 'Default visual finish restored.';
    });
    const compareButton = $('#compareLook');
    if (compareButton) {
      compareButton.addEventListener('pointerdown', e => { e.preventDefault(); compareButton.setPointerCapture(e.pointerId); startCompare(); });
      compareButton.addEventListener('pointerup', endCompare);
      compareButton.addEventListener('pointercancel', endCompare);
      compareButton.addEventListener('lostpointercapture', endCompare);
      compareButton.addEventListener('keydown', e => { if (e.code === 'Space' || e.code === 'Enter') { e.preventDefault(); startCompare(); } });
      compareButton.addEventListener('keyup', e => { if (e.code === 'Space' || e.code === 'Enter') { e.preventDefault(); endCompare(); } });
      compareButton.addEventListener('blur', endCompare);
    }
  }
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
    if (e.key === 'Escape') { if (panel && !nativePopover && !panel.hidden) closePanel(); closeMenu(); }
  });

  const explorerDialog = $('#explorerDialog'), creditsDialog = $('#creditsDialog');
  document.querySelectorAll('[data-explorer]').forEach(button => button.addEventListener('click', () => { closePanel(false); explorerDialog?.showModal(); }));
  $('#creditsButton')?.addEventListener('click', () => creditsDialog?.showModal());
  document.querySelectorAll('[data-close-dialog]').forEach(button => button.addEventListener('click', () => button.closest('dialog')?.close()));
  document.querySelectorAll('dialog').forEach(dialog => dialog.addEventListener('click', e => {
    const rect = dialog.getBoundingClientRect();
    if (e.target === dialog && (e.clientX < rect.left || e.clientX > rect.right || e.clientY < rect.top || e.clientY > rect.bottom)) dialog.close();
  }));
  $('#narratorButton')?.addEventListener('click', () => {
    const demo = $('#narratorDemo');
    if (!demo) return;
    const open = demo.hidden;
    demo.hidden = !open;
    $('#narratorButton')?.setAttribute('aria-expanded', String(open));
    if ($('#narratorButton')?.firstChild) $('#narratorButton').firstChild.textContent = open ? 'Close the preview ' : 'Meet your guide ';
    $('#narrator')?.classList.toggle('demo-open', open);
    if (open) $('#narratorQuestion')?.focus();
    requestAnimationFrame(updateScroll);
  });
  const wavelength = $('#illustrativeWavelength');
  function publishWavelength() {
    const number = Number(wavelength.value);
    if (!Number.isFinite(number)) return;
    const value = Math.min(5, Math.max(.75, number));
    wavelength.value = String(value);
    wavelength.setAttribute('aria-valuetext', `${value.toFixed(2)} micrometres, illustrative view`);
    wavelength.style.setProperty('--control-value', value);
    wavelength.style.setProperty('--attr-min', .75);
    wavelength.style.setProperty('--attr-max', 5);
    wavelength.style.setProperty('--range-progress', `${(value - .75) / 4.25 * 100}%`);
    $('#wavelengthValue').textContent = `${value.toFixed(2)} µm`;
    window.ORVYX_WAVELENGTH = value;
    window.dispatchEvent(new CustomEvent('orvyx:wavelength', { detail: value }));
  }
  if (wavelength) { wavelength.addEventListener('input', publishWavelength); publishWavelength(); }
  const observationButtons = [...document.querySelectorAll('[data-observation]')];
  function selectObservation(index) {
    if (!Number.isInteger(index) || index < 0 || index > 2) return;
    observationButtons.forEach(button => button.setAttribute('aria-pressed', String(Number(button.dataset.observation) === index)));
    window.ORVYX_OBSERVATION = index;
    window.dispatchEvent(new CustomEvent('orvyx:observation', { detail: index }));
  }
  observationButtons.forEach(button => button.addEventListener('click', () => selectObservation(Number(button.dataset.observation))));
  if (observationButtons.length) selectObservation(1);
  const narratorTargetSelect = $('#narratorTargetSelect');
  const observationIdInput = $('#observationId');
  if (narratorTargetSelect && observationIdInput) {
    const syncNarratorTarget = () => { observationIdInput.value = narratorTargetSelect.value; };
    narratorTargetSelect.addEventListener('change', syncNarratorTarget);
    syncNarratorTarget();
  }
  $('#narratorForm')?.addEventListener('submit', async (event) => {
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
      const targetLabel = $('#narratorTargetSelect')?.selectedOptions?.[0]?.textContent?.split('—')?.[0]?.trim() || 'this SPHEREx sky region';
      const cleanedAnswer = String(result.answer || '')
        .replace(/Deterministic pipeline analysis for SPHEREx observation obs_[a-zA-Z0-9]+:\s*/i, `Archive analysis for ${targetLabel}:\n`)
        .replace(/SPHEREx observation obs_[a-zA-Z0-9]+/g, targetLabel)
        .replace(/\bobs_[a-zA-Z0-9]+\b/g, targetLabel);
      answer.textContent = cleanedAnswer;
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
    } catch {
      answer.textContent = 'The narrator could not complete that response right now. Please try another sky patch or question shortly.';
    } finally {
      button.disabled = false;
    }
  });


  const sections = [...document.querySelectorAll('[data-scene]')];
  const chapterLinks = [...document.querySelectorAll('.chapter')];
  let ticking = false;
  let anchors = [];
  function cacheAnchors() {
    anchors = sections.map(section => ({ scene: section.dataset.scene, centerY: section.getBoundingClientRect().top + scrollY + section.offsetHeight / 2 }));
    updateScroll();
  }
  function updateScroll() {
    ticking = false;
    const state = getStoryState(anchors, scrollY + innerHeight / 2);
    const scrollMax = Math.max(1, document.documentElement.scrollHeight - innerHeight);
    const previous = window.ORVYX_STORY;
    chapterLinks.forEach(link => {
      const active = link.dataset.chapterTarget === state.active;
      link.classList.toggle('active', active);
      if (active) link.setAttribute('aria-current', 'step'); else link.removeAttribute('aria-current');
    });
    const reading = $('#readingProgress');
    if (reading) reading.style.transform = `scaleX(${Math.max(0, Math.min(1, scrollY / scrollMax))})`;
    document.body.dataset.activeScene = state.active;
    const intro = sections[0];
    if (intro?.classList.contains('intro-section')) {
      const exit = state.from === 'intro' && state.to === 'telescope' ? state.mix : state.active === 'intro' ? 0 : 1;
      intro.style.setProperty('--exit', exit.toFixed(3));
      const introCopy = intro.querySelector('.intro-copy');
      if (introCopy) introCopy.style.pointerEvents = exit > .55 ? 'none' : '';
      const introScroll = intro.querySelector('.intro-scroll');
      if (introScroll) introScroll.style.pointerEvents = exit > .3 ? 'none' : '';
    }
    if (!previous || previous.from !== state.from || previous.to !== state.to || previous.mix !== state.mix || previous.active !== state.active) {
      window.ORVYX_STORY = state;
      window.dispatchEvent(new CustomEvent('orvyx:story', { detail: state }));
    }
  }
  cacheAnchors();
  window.addEventListener('scroll', () => { if (!ticking) { ticking = true; requestAnimationFrame(updateScroll); } }, { passive: true });
  const orbitTargets = [...document.querySelectorAll('[data-orbit-target]')];
  orbitTargets.forEach(target => { target.dataset.interactiveLabel = target.getAttribute('aria-label'); });
  function updateOrbitLabels(webgl = !document.body.classList.contains('scene-fallback')) {
    orbitTargets.forEach(target => {
      target.setAttribute('aria-disabled', String(!webgl));
      target.tabIndex = webgl ? 0 : -1;
      target.setAttribute('aria-label', webgl ? target.dataset.interactiveLabel : 'Static preview of the illustrative sculpture. WebGL is unavailable.');
      const button = target.querySelector('[data-orbit-step]');
      button.disabled = !webgl;
      button.querySelector('span').textContent = webgl ? innerWidth <= 700 ? 'TAP TO ORBIT' : 'DRAG TO ORBIT' : 'STATIC PREVIEW';
    });
  }
  window.addEventListener('resize', () => { cacheAnchors(); updateOrbitLabels(); });
  updateOrbitLabels();
  const observer = new IntersectionObserver(entries => entries.forEach(entry => { if (entry.isIntersecting) entry.target.classList.add('is-visible'); }), { threshold: 0.12 });
  document.querySelectorAll('.reveal').forEach(el => observer.observe(el));
  const resizeObserver = new ResizeObserver(cacheAnchors);
  sections.forEach(section => resizeObserver.observe(section));
  document.fonts.ready.then(cacheAnchors);
  window.addEventListener('orvyx:ready', e => {
    document.body.classList.toggle('scene-ready', e.detail.webgl);
    document.body.classList.toggle('scene-fallback', !e.detail.webgl);
    updateOrbitLabels(e.detail.webgl);
    ['finishToggle','atmosphereRange','grainRange','qualitySelect','motionToggle','compareLook','resetLook'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.disabled = !e.detail.webgl;
    });
    if (e.detail.webgl) updateUI();
    if ($('.panel-footnote')) $('.panel-footnote').textContent = e.detail.webgl ? 'Illustrative visual finish; scientific data is unchanged.' : 'Static preview. Live visual controls require a browser with WebGL.';
    if ($('#renderStatus')) $('#renderStatus').textContent = !e.detail.webgl ? 'STATIC PREVIEW' : document.body.dataset.model === 'fallback' ? '3D FALLBACK' : 'REAL-TIME 3D';
  });
  reducedMotion.addEventListener('change', e => { if (e.matches) settings.motion = false; applySettings(); });
  applySettings(false);
  updateScroll();
  window.ORVYX = { getSettings: () => ({ ...settings }), getStoryState: () => window.ORVYX_STORY, openVisualStudio: () => openPanel(toggle) };
})();

