(() => {
  const root = document.querySelector('.guide-walkthrough');
  if (!root) return;
  const steps = [...root.querySelectorAll('.guide-step')];
  const panel = root.querySelector('main');
  const intro = root.querySelector('.guide-intro');
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
  const sections = ['sign-in', 'seerr', 'jellyfin', 'complete'];
  const sectionMenu = root.querySelector('.guide-sections');
  let current = -1;
  let moving = false;
  const linkedStep = sections.indexOf(location.hash.slice(1));
  if (linkedStep !== -1) current = linkedStep;

  function show(n, focus = true) {
    current = n;
    intro.hidden = current !== -1;
    panel.hidden = current === -1;
    root.classList.toggle('is-started', current !== -1);
    steps.forEach((step, i) => { step.hidden = i !== current; });
    try { sessionStorage.setItem('guide-step', String(current)); } catch {}
    history.replaceState(null, '', `${location.pathname}${location.search}${current === -1 ? '' : '#' + sections[current]}`);
    sectionMenu.querySelectorAll('a').forEach(link => {
      const activeSection = current === 0 ? 'sign-in' : current === 1 ? 'seerr' : 'jellyfin';
      if (current !== -1 && link.hash === '#' + activeSection) link.setAttribute('aria-current', 'step');
      else link.removeAttribute('aria-current');
    });
    if (focus) {
      const heading = current === -1 ? intro.querySelector('h1') : steps[current].querySelector('h2');
      heading.tabIndex = -1;
      heading.focus({ preventScroll: true });
      window.scrollTo({ top: 0, behavior: 'instant' });
    }
  }

  async function move(n) {
    n = Math.max(-1, Math.min(steps.length - 1, n));
    if (moving || n === current) return;
    if (reducedMotion.matches || !panel.animate) { show(n); return; }
    moving = true;
    const direction = n > current ? 1 : -1;
    const outgoing = current === -1 ? intro : steps[current];
    const oldHeight = outgoing.getBoundingClientRect().height;
    try {
      await outgoing.animate([{ opacity: 1, transform: 'translateX(0)' }, { opacity: 0, transform: `translateX(${-direction * 20}px)` }], { duration: 130, easing: 'ease-in' }).finished;
      window.scrollTo({ top: 0, behavior: 'instant' });
      show(n, false);
      const incoming = current === -1 ? intro : steps[current];
      const container = current === -1 ? intro : panel;
      const newHeight = incoming.getBoundingClientRect().height;
      panel.style.overflow = 'hidden';
      await Promise.all([
        container.animate([{ height: `${oldHeight}px` }, { height: `${newHeight}px` }], { duration: 260, easing: 'cubic-bezier(.22,1,.36,1)' }).finished,
        incoming.animate([{ opacity: 0, transform: `translateX(${direction * 20}px)` }, { opacity: 1, transform: 'translateX(0)' }], { duration: 260, easing: 'cubic-bezier(.22,1,.36,1)' }).finished
      ]);
    } finally {
      panel.style.overflow = '';
      moving = false;
      show(current, false);
      const heading = current === -1 ? intro.querySelector('h1') : steps[current].querySelector('h2');
      heading.tabIndex = -1;
      heading.focus({ preventScroll: true });
    }
  }
  const copyAddress = root.querySelector('#copyJellyfinAddress');
  copyAddress?.addEventListener('click', async () => {
    const value = root.querySelector('#jellyfinAddress').textContent.trim();
    const status = root.querySelector('#copyAddressStatus');
    status.textContent = '';
    try {
      if (!navigator.clipboard?.writeText) throw new Error('Clipboard unavailable');
      await navigator.clipboard.writeText(value);
      status.textContent = 'Copied. Paste this address into Jellyfin.';
    } catch {
      status.textContent = 'Could not copy automatically. Select and copy the address above.';
    }
  });

  root.addEventListener('click', event => {
    const link = event.target.closest('.guide-sections a, .welcome-actions a, .welcome-services a');
    if (link) {
      event.preventDefault();
      void move(sections.indexOf(link.hash.slice(1)));
    }
    if (event.target.closest('#startGuide')) void move(0);
    if (event.target.closest('.next-step')) void move(current + 1);
    if (event.target.closest('.previous-step')) void move(current - 1);
    if (event.target.closest('#restartGuide')) void move(-1);
  });
  window.addEventListener('hashchange', () => {
    const index = sections.indexOf(location.hash.slice(1));
    if (index !== -1) void move(index);
  });
  show(current);
})();