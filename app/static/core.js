// Shared primitives: session, the fetch wrapper, the small formatters, the
// modal and toast plumbing. Everything here is used by more than one page.
//
// Loaded before app.js and panel.js, and a classic script on purpose, not a
// module: the markup still carries inline onclick handlers, which resolve
// against global scope. See the rework plan.


// ── Session ────────────────────────────────────────────────────────────────────

let _me = null;           // { user, csrf_token, auth_enabled }
let _csrf = '';
let _authEnabled = false; // false in open mode (no authentication required)

function can(permission) {
  return !!_me && _me.user.permission_names.includes(permission);
}

// Every state-changing call carries the session's CSRF token, and an expired or
// revoked session lands on the login page instead of failing silently. Wrapping
// fetch once covers every call site, including the ones written before auth
// existed.
const _nativeFetch = window.fetch.bind(window);

function _withCsrfHeader(opts, method) {
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method) && _csrf) {
    opts.headers = { ...(opts.headers || {}), 'X-CSRF-Token': _csrf };
  }
  return opts;
}

/** Re-fetch identity and CSRF token without the page-load side effects
 * (nav visibility, header). Returns false if the session itself is gone. */
async function _refreshIdentity() {
  const res = await _nativeFetch('/api/auth/me');
  if (!res.ok) return false;
  _me = await res.json();
  _csrf = _me.csrf_token;
  return true;
}

window.fetch = async (input, init) => {
  init = init || {};
  const method = (init.method || 'GET').toUpperCase();
  const isAuthCall = String(input).startsWith('/api/auth/');

  let res = await _nativeFetch(input, _withCsrfHeader(init, method));

  // A stale token — typically a tab left open across a newer login elsewhere,
  // which rotates the (browser-wide) session cookie but leaves this tab's own
  // in-memory token behind — is safe to recover from: refresh it once and
  // retry. A real permission-denied 403 carries no such header and falls
  // through untouched, since refreshing a token would never fix that.
  if (res.status === 403 && res.headers.get('X-CSRF-Retry') && !isAuthCall) {
    if (await _refreshIdentity()) {
      res = await _nativeFetch(input, _withCsrfHeader(init, method));
    }
  }

function _preservePendingJamCode() {
  try {
    const raw = (window.location.hash || '') + (window.location.search || '');
    const match = raw.match(/code=([0-9]{6})/);
    if (match && match[1]) {
      sessionStorage.setItem('fv_jam_pending_code', match[1]);
    }
  } catch (_) {}
}

  if (res.status === 401 && !isAuthCall) {
    _preservePendingJamCode();
    window.location.href = '/login';
  }
  return res;
};

async function initAuth() {
  if (!await _refreshIdentity()) {
    _preservePendingJamCode();
    window.location.href = '/login';
    return false;
  }

  _authEnabled = _me.auth_enabled !== false;

  if (_me && _me.user && _me.user.theme) {
    applyTheme(_me.user.theme, false);
  }

  const initials = (_me.user.username || '?').slice(0, 2).toUpperCase();
  const roleText = _roleLabel();

  const userInitialsEl = document.getElementById('user-initials');
  if (userInitialsEl) userInitialsEl.textContent = initials;
  const userNameEl = document.getElementById('user-name');
  if (userNameEl) userNameEl.textContent = _me.user.username;
  const userRoleEl = document.getElementById('user-role');
  if (userRoleEl) userRoleEl.textContent = roleText;

  const sbName = document.getElementById('sb-user-name');
  if (sbName) sbName.textContent = _me.user.username;
  const sbProfile = document.getElementById('sb-user-profile');
  if (sbProfile) sbProfile.textContent = roleText;
  const sbAvatar = document.getElementById('sb-user-avatar');
  if (sbAvatar) sbAvatar.textContent = initials;

  const version = document.getElementById('app-version');
  if (version) version.textContent = _me.version ? `v${_me.version}` : '';

  // Menu entries follow the permissions. This is cosmetic only — every one of
  // these endpoints is checked server-side as well.
  document.querySelectorAll('[data-perm]').forEach(el => {
    const needed = el.dataset.perm.split('|');
    el.style.display = needed.some(can) ? '' : 'none';
  });
  // The inverse: hidden *because* the user holds a permission. Someone who
  // downloads directly never files a request, so the queue of their own
  // requests is an empty page with a name.
  //
  // A followed series does file requests in their name, but that is
  // machinery, not something they asked for: the request exists so dedup, the
  // library check and the notifications keep working, it is auto-approved
  // against their own DOWNLOAD permission, and what they actually want to see
  // - the episode arriving - shows up under Download like any other job. One
  // that parks on a missing track still reaches them through the bell, which
  // carries no permission gate.
  //
  // Applied second so it can override a data-perm that just showed the
  // element.
  document.querySelectorAll('[data-hide-perm]').forEach(el => {
    if (el.dataset.hidePerm.split('|').some(can)) el.style.display = 'none';
  });
  // Without authentication there is no identity or request queue to show
  if (!_authEnabled) {
    document.querySelectorAll('[data-requires-auth]').forEach(el => { el.style.display = 'none'; });
  }
  if (window.Jam && typeof window.Jam.onUserChanged === 'function') {
    window.Jam.onUserChanged();
  }
  return true;
}

function _roleLabel() {
  if (can('MANAGE_SETTINGS') || can('DOWNLOAD')) return 'Amministratore';
  return 'Utente';
}

async function logout() {
  if (window.Jam && typeof window.Jam.leaveRoom === 'function') {
    try { window.Jam.leaveRoom(); } catch (_) {}
  }
  // Best effort: the cookie is the session, and landing on /login without
  // having managed to tell the server is still better than staying put.
  try { await api.post('/api/auth/logout'); } catch (e) { /* leaving anyway */ }
  window.location.href = '/login';
}

// ── Utilities ──────────────────────────────────────────────────────────────────

function scConfirm(msg) {
  return new Promise(resolve => {
    document.getElementById('sc-confirm-msg').textContent = msg;
    const ok = document.getElementById('sc-confirm-ok');
    const cancel = document.getElementById('sc-confirm-cancel');
    function cleanup() {
      ok.removeEventListener('click', onOk);
      cancel.removeEventListener('click', onCancel);
    }
    function onOk()     { cleanup(); hideModal('sc-confirm-modal'); resolve(true); }
    function onCancel() { cleanup(); hideModal('sc-confirm-modal'); resolve(false); }
    ok.addEventListener('click', onOk, {once:true});
    cancel.addEventListener('click', onCancel, {once:true});
    showModal('sc-confirm-modal');
  });
}

function scPrompt(msg, defaultVal='') {
  return new Promise(resolve => {
    document.getElementById('sc-prompt-msg').textContent = msg;
    const input = document.getElementById('sc-prompt-input');
    input.value = defaultVal;
    const ok = document.getElementById('sc-prompt-ok');
    const cancel = document.getElementById('sc-prompt-cancel');
    function cleanup() {
      ok.removeEventListener('click', onOk);
      cancel.removeEventListener('click', onCancel);
      input.removeEventListener('keydown', onKey);
    }
    function onOk()     { cleanup(); hideModal('sc-prompt-modal'); resolve(input.value); }
    function onCancel() { cleanup(); hideModal('sc-prompt-modal'); resolve(null); }
    function onKey(e)   { if (e.key === 'Enter') onOk(); }
    ok.addEventListener('click', onOk, {once:true});
    cancel.addEventListener('click', onCancel, {once:true});
    input.addEventListener('keydown', onKey);
    showModal('sc-prompt-modal');
    setTimeout(() => {
      try { input.focus(); input.select(); } catch (_) { try { input.focus(); } catch (_) {} }
    }, 50);
  });
}

// Universal clipboard copy with fallback for non-secure HTTP contexts (e.g. LAN / Docker)
async function copyToClipboard(text) {
  if (!text) return false;

  // 1. Try modern Async Clipboard API in secure contexts (HTTPS or localhost)
  if (window.isSecureContext && navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (e) {
      console.warn('[Clipboard] Async API failed, falling back:', e);
    }
  }

  // 2. Fallback using temporary textarea + execCommand('copy')
  try {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.setAttribute('readonly', '');
    ta.style.cssText = 'position:fixed;top:-9999px;left:-9999px;opacity:0;pointer-events:none;z-index:-1;';
    document.body.appendChild(ta);

    // iOS selection compatibility
    if (navigator.userAgent.match(/ipad|ipod|iphone/i)) {
      const range = document.createRange();
      range.selectNodeContents(ta);
      const sel = window.getSelection();
      if (sel) {
        sel.removeAllRanges();
        sel.addRange(range);
      }
      ta.setSelectionRange(0, 999999);
    } else {
      ta.focus();
      ta.select();
      ta.setSelectionRange(0, text.length);
    }

    const success = document.execCommand('copy');
    document.body.removeChild(ta);
    if (success) return true;
  } catch (err) {
    console.warn('[Clipboard] execCommand fallback failed:', err);
  }

  return false;
}

function escapeHtml(s) {
  if (!s) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function formatSize(bytes) {
  if (bytes == null) return '—';
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1048576) return (bytes/1024).toFixed(1) + ' KB';
  if (bytes < 1073741824) return (bytes/1048576).toFixed(1) + ' MB';
  return (bytes/1073741824).toFixed(2) + ' GB';
}
function fmtEta(sec) {
  if (sec == null || sec <= 0) return '';
  if (sec < 60) return `${sec}s`;
  const m = Math.floor(sec / 60), s = sec % 60;
  if (m < 60) return `${m}m ${s.toString().padStart(2,'0')}s`;
  const h = Math.floor(m / 60), rm = m % 60;
  return `${h}h ${rm}m`;
}

// ── Modal helpers ──────────────────────────────────────────────────────────────

function showModal(id) {
  const el = document.getElementById(id);
  if (!el) return;
  // Blur currently focused element so button clicks don't swallow Space/keys
  if (document.activeElement && typeof document.activeElement.blur === 'function') {
    document.activeElement.blur();
  }
  el.style.display = 'block';
  el.classList.add('show');
  el.setAttribute('aria-modal', 'true');
  el.removeAttribute('aria-hidden');
  if (!document.querySelector('.modal-backdrop')) {
    const bd = document.createElement('div');
    bd.className = 'modal-backdrop fade show';
    document.body.appendChild(bd);
  }
  document.body.classList.add('modal-open');

  const v = el.querySelector('video');
  if (v) {
    setTimeout(() => {
      try { v.focus(); } catch (_) {}
    }, 100);
  }
}
function hideModal(id) {
  const el = document.getElementById(id);
  if (!el) return;

  // Immediately stop, pause and detach any audio/video elements inside this modal
  el.querySelectorAll('video, audio').forEach(media => {
    try {
      media.pause();
      media.currentTime = 0;
      media.removeAttribute('src');
      media.load();
    } catch (err) {}
  });

  // Also clean up any active iframes (e.g. streaming embeds) to stop background playback
  el.querySelectorAll('iframe').forEach(iframe => {
    try {
      iframe.src = 'about:blank';
    } catch (err) {}
  });

  el.style.display = 'none';
  el.classList.remove('show');
  el.setAttribute('aria-hidden', 'true');
  el.removeAttribute('aria-modal');
  document.querySelector('.modal-backdrop')?.remove();
  document.body.classList.remove('modal-open');

  try {
    el.dispatchEvent(new CustomEvent('hidden.bs.modal', { bubbles: true }));
    el.dispatchEvent(new CustomEvent('modal:hidden', { detail: { id }, bubbles: true }));
  } catch (err) {}
}
document.addEventListener('click', (e) => {
  if (e.target.classList.contains('modal') && (e.target.classList.contains('show') || e.target.style.display === 'block'))
    hideModal(e.target.id);
  if (e.target.closest('[data-bs-dismiss="modal"]')) {
    const modal = e.target.closest('.modal');
    if (modal) hideModal(modal.id);
  }
});

// Close open modal on Escape key (only if not currently exiting browser fullscreen)
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' || e.key === 'Esc') {
    if (document.fullscreenElement || document.webkitFullscreenElement || document.mozFullScreenElement || document.msFullscreenElement) {
      return;
    }
    const openModals = document.querySelectorAll('.modal.show, .modal[style*="display: block"]');
    openModals.forEach(m => hideModal(m.id));
  }
});

// ── Global Video Player Controls & Hotkeys ───────────────────────────────────

function isTypingContext(target) {
  if (!target) return false;
  const tag = target.tagName;
  if (tag === 'INPUT') {
    const type = (target.type || 'text').toLowerCase();
    return !['checkbox', 'radio', 'button', 'submit', 'reset', 'range'].includes(type);
  }
  if (tag === 'TEXTAREA' || tag === 'SELECT') return true;
  if (target.isContentEditable) return true;
  return false;
}

function getActiveVideoPlayer() {
  const fsEl = document.fullscreenElement || document.webkitFullscreenElement || document.mozFullScreenElement || document.msFullscreenElement;
  if (fsEl) {
    if (fsEl.tagName === 'VIDEO') return fsEl;
    const vInFs = fsEl.querySelector('video');
    if (vInFs) return vInFs;
  }
  const streamVideo = document.getElementById('stream-video-player');
  if (streamVideo && streamVideo.webkitDisplayingFullscreen) return streamVideo;
  const localVideo = document.getElementById('video-player');
  if (localVideo && localVideo.webkitDisplayingFullscreen) return localVideo;

  const streamModal = document.getElementById('stream-player-modal');
  if (streamModal && (streamModal.classList.contains('show') || streamModal.style.display === 'block')) {
    if (streamVideo && streamVideo.style.display !== 'none') return streamVideo;
  }
  const playerModal = document.getElementById('player-modal');
  if (playerModal && (playerModal.classList.contains('show') || playerModal.style.display === 'block')) {
    if (localVideo && localVideo.style.display !== 'none') return localVideo;
  }
  const videos = document.querySelectorAll('video');
  for (const v of videos) {
    if (!v.paused && v.offsetWidth > 0 && v.offsetHeight > 0) return v;
  }
  if (streamModal && (streamModal.classList.contains('show') || streamModal.style.display === 'block')) {
    if (streamVideo) return streamVideo;
  }
  if (playerModal && (playerModal.classList.contains('show') || playerModal.style.display === 'block')) {
    if (localVideo) return localVideo;
  }
  return null;
}

function refocusActivePlayer() {
  const fsEl = document.fullscreenElement || document.webkitFullscreenElement || document.mozFullScreenElement || document.msFullscreenElement;
  const video = fsEl ? (fsEl.tagName === 'VIDEO' ? fsEl : fsEl.querySelector('video')) : getActiveVideoPlayer();
  if (video) {
    if (document.activeElement && document.activeElement !== video) {
      try { document.activeElement.blur(); } catch (_) {}
    }
    try {
      video.focus({ preventScroll: true });
    } catch (_) {
      try { video.focus(); } catch (_) {}
    }
  }
}

function togglePlayerFullscreen(specificVideo) {
  const video = specificVideo || getActiveVideoPlayer();
  if (!video) return;

  const isFullscreen = !!(document.fullscreenElement || document.webkitFullscreenElement || document.mozFullScreenElement || document.msFullscreenElement);
  if (!isFullscreen) {
    if (video.requestFullscreen) {
      video.requestFullscreen().catch(() => {
        if (document.documentElement.requestFullscreen) document.documentElement.requestFullscreen().catch(() => {});
      });
    } else if (video.webkitRequestFullscreen) {
      video.webkitRequestFullscreen();
    } else if (video.msRequestFullscreen) {
      video.msRequestFullscreen();
    } else if (document.documentElement.requestFullscreen) {
      document.documentElement.requestFullscreen().catch(() => {});
    }
  } else {
    if (document.exitFullscreen) {
      document.exitFullscreen().catch(() => {});
    } else if (document.webkitExitFullscreen) {
      document.webkitExitFullscreen();
    } else if (document.msExitFullscreen) {
      document.msExitFullscreen();
    }
  }
}

// When entering or exiting fullscreen, refocus the video and update UI button icons
['fullscreenchange', 'webkitfullscreenchange', 'mozfullscreenchange', 'MSFullscreenChange'].forEach(evt => {
  document.addEventListener(evt, () => {
    const isFullscreen = !!(document.fullscreenElement || document.webkitFullscreenElement || document.mozFullScreenElement || document.msFullscreenElement);
    document.querySelectorAll('#stream-player-fs-btn i, #player-fs-btn i').forEach(icon => {
      icon.className = isFullscreen ? 'ti ti-minimize' : 'ti ti-maximize';
    });
    refocusActivePlayer();
    setTimeout(refocusActivePlayer, 50);
    setTimeout(refocusActivePlayer, 150);
  });
});

let _lastHandledKeyTime = 0;
let _lastHandledKey = '';

function handlePlayerKeyDown(e) {
  if (isTypingContext(e.target)) return;

  const key = e.key;
  const code = e.code;
  const isSpace = code === 'Space' || key === ' ' || key === 'Spacebar';
  const isPlayPause = isSpace || key === 'k' || key === 'K';
  const isSeekRight = key === 'ArrowRight' || key === 'l' || key === 'L';
  const isSeekLeft = key === 'ArrowLeft' || key === 'j' || key === 'J';
  const isVolUp = key === 'ArrowUp';
  const isVolDown = key === 'ArrowDown';
  const isMute = key === 'm' || key === 'M';
  const isFs = key === 'f' || key === 'F';

  if (!isPlayPause && !isSeekRight && !isSeekLeft && !isVolUp && !isVolDown && !isMute && !isFs) {
    return;
  }

  const video = getActiveVideoPlayer();
  if (!video) return;

  // Discard key repetitions for toggle actions (play/pause, fullscreen, mute)
  if (e.repeat && (isPlayPause || isFs || isMute)) {
    e.preventDefault();
    return;
  }

  e.preventDefault();
  e.stopImmediatePropagation();

  if (document.activeElement && document.activeElement !== video && document.activeElement.tagName === 'BUTTON') {
    try { document.activeElement.blur(); } catch (_) {}
  }

  // Spacebar or 'k' / 'K': Play / Pause toggle
  if (isPlayPause) {
    if (video.paused) {
      video.play().catch(() => {});
    } else {
      video.pause();
    }
    return;
  }

  // ArrowRight or 'l' / 'L': Seek +10 seconds
  if (isSeekRight) {
    video.currentTime = Math.min(video.duration || Infinity, video.currentTime + 10);
    return;
  }

  // ArrowLeft or 'j' / 'J': Seek -10 seconds
  if (isSeekLeft) {
    video.currentTime = Math.max(0, video.currentTime - 10);
    return;
  }

  // ArrowUp: Volume +10%
  if (isVolUp) {
    video.volume = Math.min(1, Math.round((video.volume + 0.1) * 10) / 10);
    video.muted = false;
    return;
  }

  // ArrowDown: Volume -10%
  if (isVolDown) {
    video.volume = Math.max(0, Math.round((video.volume - 0.1) * 10) / 10);
    return;
  }

  // 'm' or 'M': Mute / Unmute
  if (isMute) {
    video.muted = !video.muted;
    return;
  }

  // 'f' or 'F': Fullscreen toggle directly on the video element (pure video, full screen)
  if (isFs) {
    togglePlayerFullscreen(video);
    return;
  }
}

// Intercept hotkeys on window in capture phase
window.addEventListener('keydown', handlePlayerKeyDown, true);

// Focus video on pointerdown to guarantee it receives keyboard input
document.addEventListener('pointerdown', (e) => {
  if (e.target && e.target.tagName === 'VIDEO') {
    try { e.target.focus({ preventScroll: true }); } catch (_) {}
  }
}, true);

// Auto-focus video when a modal opens
document.addEventListener('shown.bs.modal', (e) => {
  const vid = e.target && e.target.querySelector ? e.target.querySelector('video') : null;
  if (vid) {
    try { vid.focus({ preventScroll: true }); } catch (_) {}
  }
});

// Double click directly on video in fullscreen toggles fullscreen
window.addEventListener('dblclick', (e) => {
  if (e.target && e.target.tagName === 'VIDEO') {
    const video = e.target;
    const rect = video.getBoundingClientRect();
    const isNearBottom = (e.clientY - rect.top) > (rect.height - 58);
    if (!isNearBottom) {
      e.preventDefault();
      togglePlayerFullscreen(video);
    }
  }
}, true);

// ── Toast ──────────────────────────────────────────────────────────────────────

function showToast(message, type = 'info') {
  const colors = { success:'bg-success', danger:'bg-danger', info:'bg-info', warning:'bg-warning' };
  const toast = document.createElement('div');
  toast.style.cssText = 'position:fixed;bottom:1rem;right:1rem;left:auto;z-index:9999;min-width:220px;max-width:calc(100vw - 2rem)';
  toast.innerHTML = `<div class="alert ${colors[type]||'bg-info'} alert-dismissible text-white mb-0 shadow" role="alert">
    ${escapeHtml(message)}
    <button type="button" class="btn-close btn-close-white" data-action="toast:dismiss"></button>
  </div>`;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 4000);
}

// ── Artwork ───────────────────────────────────────────────────────────────────
//
// Stills and posters travel through /api/image/, which reaches the source's
// CDN on the server's behalf. A single failure there is usually transient, so
// a missing image should not collapse the row it belongs to: the slot stays,
// a placeholder holds it, and the fetch is retried a couple of times before
// giving up quietly.

const _THUMB_RETRIES = 2;

function thumbHtml(src, cls, alt = '') {
  if (!src) return `<span class="${cls} thumb is-failed" aria-hidden="true"></span>`;
  // No onload: the image is visible from the start and the placeholder simply
  // sits behind it. Gating visibility on a handler meant a missed load event
  // hid the picture permanently.
  return `<span class="${cls} thumb">
    <img src="${escapeHtml(src)}" alt="${escapeHtml(alt)}" loading="lazy"
         data-src="${escapeHtml(src)}" onerror="thumbError(this)">
  </span>`;
}

function thumbError(img) {
  const tries = Number(img.dataset.tries || 0);
  if (tries >= _THUMB_RETRIES) { img.parentElement?.classList.add('is-failed'); return; }
  img.dataset.tries = String(tries + 1);
  // A cache-busting query, not a fragment: a fragment change does not make
  // the browser ask again.
  const base = img.dataset.src;
  const sep = base.includes('?') ? '&' : '?';
  img.parentElement?.classList.remove('is-failed');
  setTimeout(() => { img.src = `${base}${sep}_retry=${tries + 1}`; }, 500 * (tries + 1));
}

// A poster that will not load: reveal the placeholder already sitting behind
// it and take the broken image out. Named, rather than three statements
// written into an onerror attribute — error does not bubble, so this one
// genuinely cannot be delegated, but it does not have to be inline JS either.
function posterError(img) {
  const wrap = img.closest('.poster-wrap');
  const placeholder = wrap && wrap.querySelector('.poster-noimg');
  if (placeholder) placeholder.style.display = 'flex';
  img.style.display = 'none';
}

// A title's poster. AnimeUnity sends an absolute URL; StreamingCommunity sends
// a bare filename that /api/image/ resolves against the current source host -
// which is why it must not be hardcoded anywhere.
function posterUrl(item) {
  const p = item && item.poster;
  if (!p) return '';
  return p.startsWith('http') ? p : `/api/image/${p}`;
}


// ── Delegated actions ────────────────────────────────────────────────────────
//
// One listener on the document, instead of an onclick= per button. Two reasons
// beyond tidiness: an inline handler interpolates its arguments into an HTML
// attribute with no escaping, so a title containing an apostrophe used to break
// the button it was rendered into; and a row that is re-rendered mid-interaction
// keeps working, because nothing is bound to the node that went away.
//
// Additive on purpose: it coexists with the inline handlers that have not been
// converted yet. A page converts its own markup when it is reworked, never in a
// sweep across all of them at once.
//
// Arguments travel as data-* attributes and arrive as the element's dataset, so
// they are strings: a handler that wants a number converts it.
const _ACTIONS = Object.create(null);

function registerActions(map) { Object.assign(_ACTIONS, map); }

// A checkbox's click event carries its own activation: cancelling it un-checks
// the box the user just checked. So the default is only suppressed for things
// that have no useful default of their own.
const _KEEPS_ITS_DEFAULT = new Set(['INPUT', 'SELECT', 'TEXTAREA', 'OPTION', 'LABEL']);

function _dispatchAction(event, attribute) {
  const el = event.target.closest(`[${attribute}]`);
  if (!el || el.disabled) return;
  const handler = _ACTIONS[el.getAttribute(attribute)];
  if (!handler) return;
  // Only swallow the event once something is actually going to handle it: an
  // unregistered name must look broken, not silently eat the click.
  if (event.type === 'click' && !_KEEPS_ITS_DEFAULT.has(el.tagName)) event.preventDefault();
  handler(el.dataset, el, event);
}

document.addEventListener('click', e => _dispatchAction(e, 'data-action'));
document.addEventListener('change', e => _dispatchAction(e, 'data-change'));
document.addEventListener('input', e => _dispatchAction(e, 'data-input'));

// Two keys, because those are the two a text field answers: Enter runs the
// thing, Escape abandons it. Anything more belongs to the field itself.
document.addEventListener('keydown', e => {
  if (e.key === 'Enter') _dispatchAction(e, 'data-enter');
  else if (e.key === 'Escape') _dispatchAction(e, 'data-escape');
});


// ── Language names ───────────────────────────────────────────────────────────
//
// Shared, not owned by a page: the title page names the tracks you are picking
// and the request pages name the tracks a request was made with. This lived in
// the detail view until splitting the scripts showed the request rows reaching
// across for it.
//
// Anything not listed is shown as the source spelled it, rather than dropped.

const LANG_NAMES = {
  ita:'Italiano', eng:'English', fra:'Français', spa:'Español',
  deu:'Deutsch', por:'Português', jpn:'日本語', zho:'中文',
  ara:'العربية', rus:'Русский', kor:'한국어',
};
const langName = c => c.startsWith('forced-')
  ? `${langName(c.slice(7))} (forzati)`
  : LANG_NAMES[c] || c;


// formatSize() stops at GB and is used for file rows; volumes are routinely in
// terabytes, so the disk readout gets its own scale.
function fmtBytes(bytes) {
  if (bytes == null) return '—';
  const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
  let value = bytes, i = 0;
  while (value >= 1024 && i < units.length - 1) { value /= 1024; i++; }
  return `${value.toFixed(value >= 100 || i === 0 ? 0 : 1).replace('.', ',')} ${units[i]}`;
}


// How full is too full, in one place. The sidebar bar and the file page's bar
// were each carrying their own pair of numbers, and they had already drifted
// apart: the same volume read amber in one and fine in the other.
//
// Past 92% a 4K season may not fit, which is the number worth a red bar.
function diskLevel(pct) {
  if (pct >= 92) return 'is-critical';
  if (pct >= 80) return 'is-warning';
  return '';
}


registerActions({
  'session:logout': () => logout(),
  // The button sits inside the .alert; the positioned wrapper is its parent,
  // and that is what has to go, or an invisible box keeps covering the corner.
  'toast:dismiss':  (d, el) => el.closest('.alert')?.parentElement?.remove(),
  'theme:toggle':   () => toggleThemePanel(),
  'theme:select':   d => {
    applyTheme(d.theme);
    const th = THEMES.find(t => t.id === d.theme);
    showToast(`Tema "${th ? th.name : d.theme}" applicato`, 'success');
  },
  'player:toggleFullscreen': () => togglePlayerFullscreen(),
});


// ── Theming System ─────────────────────────────────────────────────────────────

const THEMES = [
  {
    id: 'default',
    name: 'Blu Notte',
    tag: 'Classico',
    desc: 'L\'iconica palette dark navy con accenti blu cobalto e bagliori al neon.',
    bg: '#070A12',
    surface: '#10151F',
    accent: '#3D6BF5',
    isLight: false,
  },
  {
    id: 'rose',
    name: 'Rosa Neon',
    tag: 'Cyberpunk',
    desc: 'Atmosfera dark velvet con intensi riflessi rosa acceso e sfumature prugna.',
    bg: '#0E0713',
    surface: '#170D20',
    accent: '#F43F85',
    isLight: false,
  },
  {
    id: 'emerald',
    name: 'Verde Smeraldo',
    tag: 'Matrix',
    desc: 'Fondo ossidiana e riflessi verde smeraldo / menta ad alta visibilità.',
    bg: '#05120B',
    surface: '#0A1E14',
    accent: '#10B981',
    isLight: false,
  },
  {
    id: 'amber',
    name: 'Arancione Fuoco',
    tag: 'Solare',
    desc: 'Tonalità calde carbone con contrasti solari ambra e arancione tramonto.',
    bg: '#120904',
    surface: '#1C1108',
    accent: '#F97316',
    isLight: false,
  },
  {
    id: 'light',
    name: 'Bianco Perla',
    tag: 'Luminoso',
    desc: 'Stile chiaro, pulito e moderno con superfici bianco porcellana e blu zaffiro.',
    bg: '#EDF1F7',
    surface: '#FFFFFF',
    accent: '#2563EB',
    isLight: true,
  },
  {
    id: 'purple',
    name: 'Viola Galassia',
    tag: 'Cosmico',
    desc: 'Nero galattico con riflessi ultravioletti e ametista misteriosi ed eleganti.',
    bg: '#0B0716',
    surface: '#130D26',
    accent: '#9333EA',
    isLight: false,
  },
  {
    id: 'cyan',
    name: 'Ciano Abissale',
    tag: 'Vaporwave',
    desc: 'Nero abisso profondo con accenti ciano elettrico e bagliori oceanici.',
    bg: '#040E14',
    surface: '#091822',
    accent: '#06B6D4',
    isLight: false,
  },
  {
    id: 'oled',
    name: 'Nero OLED',
    tag: 'AMOLED',
    desc: 'Nero assoluto 100% per il massimo risparmio energetico e contrasto crimson.',
    bg: '#000000',
    surface: '#09090B',
    accent: '#E11D48',
    isLight: false,
  },
  {
    id: 'crimson',
    name: 'Rosso Rubino',
    tag: 'Passione',
    desc: 'Tonalità dark crimson sofisticata con accenti rosso fuoco decisi.',
    bg: '#110608',
    surface: '#1D0B0F',
    accent: '#DC2626',
    isLight: false,
  },
];

function getCurrentTheme() {
  return document.documentElement.getAttribute('data-theme') || 'default';
}

function applyTheme(themeId, saveToServer = true) {
  const targetTheme = THEMES.some(t => t.id === themeId) ? themeId : 'default';

  if (targetTheme === 'default') {
    document.documentElement.removeAttribute('data-theme');
  } else {
    document.documentElement.setAttribute('data-theme', targetTheme);
  }

  try {
    localStorage.setItem('sc_theme', targetTheme);
  } catch (e) {}

  updateThemeUI(targetTheme);

  if (saveToServer && _me && _me.user && _me.user.id) {
    _saveThemeToServer(targetTheme);
  }
}

async function _saveThemeToServer(themeId) {
  try {
    const res = await _nativeFetch('/api/auth/theme', _withCsrfHeader({
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ theme: themeId }),
    }, 'PUT'));
    if (res.ok && _me && _me.user) {
      _me.user.theme = themeId;
    }
  } catch (err) {
    console.warn('Could not save theme to server', err);
  }
}

function updateThemeUI(activeTheme = getCurrentTheme()) {
  const currentObj = THEMES.find(t => t.id === activeTheme) || THEMES[0];

  // Update header theme panel items
  renderHeaderThemeOptions(activeTheme);

  // Update Settings page badge and cards if rendered
  const currentBadge = document.getElementById('current-theme-name');
  if (currentBadge) currentBadge.textContent = currentObj.name;

  document.querySelectorAll('.theme-card').forEach(card => {
    const isThis = card.dataset.theme === activeTheme;
    card.classList.toggle('is-active', isThis);
    const btn = card.querySelector('.btn-theme-apply');
    if (btn) {
      btn.className = isThis ? 'btn btn-sm btn-primary' : 'btn btn-sm btn-secondary';
      btn.innerHTML = isThis ? '<i class="ti ti-check me-1"></i>Attivo' : 'Seleziona';
    }
  });
}

function renderHeaderThemeOptions(activeTheme = getCurrentTheme()) {
  const container = document.getElementById('theme-options-list');
  if (!container) return;

  container.innerHTML = THEMES.map(t => {
    const isActive = t.id === activeTheme;
    return `
      <button class="theme-option-btn ${isActive ? 'is-active' : ''}" data-action="theme:select" data-theme="${t.id}" type="button">
        <div class="theme-swatch-pill" style="background:${t.bg}; border-color:${t.isLight ? 'rgba(0,0,0,.15)' : 'rgba(255,255,255,.15)'}">
          <div class="theme-swatch-dot" style="background:${t.accent}; color:${t.accent};"></div>
        </div>
        <div class="theme-option-info">
          <div class="theme-option-name">${escapeHtml(t.name)}</div>
          <div class="theme-option-desc">${escapeHtml(t.tag)} &bull; ${escapeHtml(t.desc)}</div>
        </div>
        <i class="ti ti-check theme-option-check"></i>
      </button>
    `;
  }).join('');
}

function toggleThemePanel() {
  const panel = document.getElementById('theme-panel');
  if (!panel) return;
  const opening = panel.style.display === 'none' || !panel.style.display;
  panel.style.display = opening ? 'block' : 'none';
  if (opening) {
    renderHeaderThemeOptions();
    // Close notifications panel if open
    const notif = document.getElementById('notif-panel');
    if (notif) notif.style.display = 'none';
  }
}

document.addEventListener('click', event => {
  const panel = document.getElementById('theme-panel');
  if (!panel || panel.style.display === 'none') return;
  if (!event.target.closest('#theme-panel') && !event.target.closest('[data-action="theme:toggle"]')) {
    panel.style.display = 'none';
  }
});

