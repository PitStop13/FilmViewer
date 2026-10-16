/* StreamingCommunity Web Panel — page-search.js */
//
// The search page: the source selector, the query, the result grid and its
// filters, and the shelves the start page shows with the box empty.

// What a title is, in the source's own word. StreamingCommunity says movie/tv;
// AnimeUnity says Movie/TV/OVA/ONA/Special and keeps it in media_type, beside a
// type that is always "anime". Looked up lower case so one table serves both.
// One colour per kind, so a grid can be read at a glance instead of word by word.
const KIND_BADGES = {
  movie:   {label: 'Film',     cls: 'bg-blue-lt'},
  tv:      {label: 'Serie TV', cls: 'bg-green-lt'},
};
function kindBadge(item) {
  const key = String(item.media_type || item.type || '').toLowerCase();
  return KIND_BADGES[key] || {label: item.media_type || item.type || '?',
                              cls: 'bg-secondary-lt'};
}

// ── Source & Category selector ────────────────────────────────────────────────

let _homeCategory = 'all'; // 'all' | 'movie' | 'tv'

function setSource(src) {
  currentSource = 'streamingcommunity';
  document.getElementById('src-sc')?.classList.toggle('active', true);
  document.getElementById('src-au')?.classList.toggle('active', false);
  const input = document.getElementById('search-input');
  if (input) input.placeholder = 'Cerca film o serie TV per titolo...';
  document.getElementById('search-results').innerHTML = '';
  _searchResults = [];
  _requestStatus = {};
  _searchPage = 1;
  _searchExhausted = false;
  _kindFilter = '';
  _dubOnly = false;
  renderSearchFilters();
  _setMoreVisible(false);
  _rerunSearch();
  syncHash();
}

function setHomeCategory(cat) {
  _homeCategory = cat || 'all';
  document.getElementById('cat-all')?.classList.toggle('active', _homeCategory === 'all');
  document.getElementById('cat-movie')?.classList.toggle('active', _homeCategory === 'movie');
  document.getElementById('cat-tv')?.classList.toggle('active', _homeCategory === 'tv');
  syncHash();
  showStartPage();
}

// ── Search ─────────────────────────────────────────────────────────────────────

let _searchAbort = null;
let _searchDebounceTimer = null;

function setupSearchDebounce() {
  const input = document.getElementById('search-input');
  if (!input) return;
  input.addEventListener('input', () => {
    clearTimeout(_searchDebounceTimer);
    const q = input.value.trim();
    if (q.length >= 3) {
      _searchDebounceTimer = setTimeout(() => doSearch(), 400);
    } else if (q.length === 0) {
      // Only on empty, never on one or two characters: that is somebody on
      // their way to a three-letter query, and swapping the page out from
      // under them is worse than a blank pause.
      _searchDebounceTimer = setTimeout(() => showStartPage(), 200);
    }
  });
}

function _showSearchSkeletons() {
  const container = document.getElementById('search-results');
  container.innerHTML = '';
  for (let i = 0; i < 6; i++) {
    const col = document.createElement('div');
    col.className = 'col-6 col-sm-4 col-md-3 col-lg-2';
    col.innerHTML = '<div class="skeleton skeleton-card"></div>';
    container.appendChild(col);
  }
}

// ── Result filters and paging ─────────────────────────────────────────────────

let _searchPage = 1;
let _searchExhausted = false;
let _loadingMore = false;
let _kindFilter = '';   // '' | movie | tv
let _dubOnly = false;

const KIND_FILTERS = [
  ['', 'Tutti i risultati'],
  ['movie', '🎬 Solo Film'],
  ['tv', '📺 Solo Serie TV'],
];

function renderSearchFilters() {
  const bar = document.getElementById('search-filters');
  if (!bar) return;
  const chips = KIND_FILTERS.map(([value, label]) =>
    `<button class="source-btn${value === _kindFilter ? ' active' : ''}" ` +
    `data-action="search:kind" data-kind="${value}">${label}</button>`).join('');
  bar.innerHTML = chips;
}

function setKindFilter(kind) {
  if (kind === _kindFilter) return;
  _kindFilter = kind;
  renderSearchFilters();
  _afterFilterChange();
}

function setDubOnly(on) {
  _dubOnly = !!on;
  renderSearchFilters();
  _afterFilterChange();
}

function _rerunSearch() {
  const input = document.getElementById('search-input');
  if (input && input.value.trim()) doSearch();
  else showStartPage();
}

// With a query the filter belongs to the source, or paging and filtering stop
// composing: a page of sixty narrowed to four in the browser would page through
// a window that has already been narrowed. On the rails there is nothing to
// page, so it is applied where the cards already are.
function _afterFilterChange() {
  syncHash();
  const input = document.getElementById('search-input');
  if (input && input.value.trim()) doSearch();
  else applyClientFilter();
}

// A plain object for api.url, which drops undefined and keeps ''. That
// distinction matters here: an empty media_type must be *absent*, not sent
// blank, so the optional filters resolve to undefined rather than ''.
function _searchParams(q, page) {
  return {
    q, source: 'streamingcommunity', page: String(page),
    media_type: _kindFilter || undefined,
  };
}

function _setMoreVisible(on) {
  const wrap = document.getElementById('search-more');
  if (wrap) wrap.style.display = on ? '' : 'none';
}

// Cards are rendered from a base index rather than from the array, so a page
// appended later indexes into the same flat _searchResults and card n keeps
// pointing at title n forever.
function renderResultCards(items, container, baseIndex,
                           wrapperClass = 'col-6 col-sm-4 col-md-3 col-lg-2') {
  items.forEach((item, i) => {
    const idx = baseIndex + i;
    const isMovie = item.type === 'movie';
    const kind = kindBadge(item);
    const year = itemYear(item);
    const score = item.score ? parseFloat(item.score).toFixed(1) : null;
    const posterUrl = item.poster
      ? (item.poster.startsWith('http') ? item.poster : `/api/image/${item.poster}`)
      : '';
    const card = document.createElement('div');
    card.className = wrapperClass;
    card.dataset.idx = String(idx);
    const posterHtml = posterUrl
      ? `<img src="${posterUrl}" alt="" loading="lazy" decoding="async" onerror="posterError(this)">`
      : '';
    // Movie cards carry no status ribbon: a movie can be requested again
    // freely (denied/failed/cancelled never block it), so a "richiesto" chip
    // would just read as blocked when it is not. TV and anime keep it — their
    // status is read from the grouped request rows anyway, not per-title.
    const ribbonHtml = isMovie
      ? ''
      : `<div class="status-ribbon" data-ribbon-for="${escapeHtml(String(item.id))}"></div>`;
    card.innerHTML = `
      <div class="result-card" data-action="search:open" data-idx="${idx}">
        <div class="poster-wrap">
          ${posterHtml}
          <div class="poster-noimg" style="${posterUrl?'display:none':''}">&#127916;</div>
          <div class="poster-overlay"></div>
          ${ribbonHtml}
          <div class="poster-play"><i class="ti ti-player-play-filled" style="font-size:16px"></i></div>
        </div>
        <div class="card-meta">
          <div class="card-title-text" title="${escapeHtml(item.name)}">${escapeHtml(item.name)}</div>
          <div class="card-badges">
            <span class="badge ${kind.cls}">${escapeHtml(kind.label)}</span>
            ${score?`<span class="badge bg-yellow-lt">★ ${score}</span>`:''}
            ${year?`<span style="font-size:10px;color:var(--text-muted)">${year}</span>`:''}
          </div>
        </div>
      </div>`;
    container.appendChild(card);
  });
}

async function doSearch(options) {
  const append = !!(options && options.append);
  const q = document.getElementById('search-input').value.trim();
  if (!q) return;
  // The boot no longer blocks routing on the domain, so a search restored
  // from the address can start before it is known. Asking costs nothing once
  // it is: ensureDomain() shares the one request.
  await ensureDomain();
  if (!currentDomain) { openSettings(); return; }
  if (append && (_loadingMore || _searchExhausted)) return;

  if (!append) {
    // Only a fresh search cancels what is in flight. A load-more must not abort
    // itself, and must not be aborted by the debounce still pending from the
    // last keystroke.
    if (_searchAbort) _searchAbort.abort();
    _searchAbort = new AbortController();
    _searchPage = 1;
    _searchExhausted = false;
    _searchResults = [];
    _requestStatus = {};
    _setStartPageVisible(false);
  }

  const container = document.getElementById('search-results');
  const btn = document.getElementById('search-btn');
  const moreBtn = document.getElementById('search-more-btn');
  const moreLabel = moreBtn ? moreBtn.innerHTML : '';
  if (append) {
    _loadingMore = true;
    if (moreBtn) {
      moreBtn.disabled = true;
      moreBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Carico...';
    }
  } else {
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Cerca';
    _showSearchSkeletons();
    _setMoreVisible(false);
  }

  try {
    let results;
    try {
      results = await api.get('/api/search', _searchParams(q, _searchPage),
                              append ? undefined : {signal: _searchAbort.signal});
    } catch (e) {
      if (e.name === 'AbortError') throw e;   // handled by the catch below
      const detail = escapeHtml(errText(e));
      if (append) showToast(detail, 'danger');
      else container.innerHTML = `<div class="col-12"><div class="alert alert-danger">${detail}</div></div>`;
      return;
    }
    if (!append) container.innerHTML = '';

    renderResultCards(results, container, _searchResults.length);
    _searchResults = _searchResults.concat(results);
    syncHash();

    // A filtered page coming back empty means "none of that kind here", not
    // "no more results". StreamingCommunity has no filter of its own, so the
    // panel applies one per page, and the source groups its results by kind:
    // measured, a query whose first page is sixty series has its films on a
    // later one. AnimeUnity filters at the source, where the offset walks the
    // filtered catalogue, so there an empty page really is the end.
    const filterIsPerPage = !!_kindFilter;
    _searchExhausted = !results.length && !filterIsPerPage;

    if (!_searchResults.length) {
      container.innerHTML = '<div class="col-12"><p class="text-muted">Nessun risultato.</p></div>';
    } else if (append && !results.length) {
      showToast('Nessun altro risultato', 'info');
    }
    _setMoreVisible(!_searchExhausted);

    loadRequestStatuses(results.filter(r => r.type !== 'movie').map(r => String(r.id)));
  } catch(e) {
    if (e.name === 'AbortError') return; // cancelled by new search
    if (append) showToast('Errore di rete', 'danger');
    else container.innerHTML=`<div class="col-12"><div class="alert alert-danger">Errore: ${escapeHtml(e.message)}</div></div>`;
  } finally {
    if (append) {
      _loadingMore = false;
      if (moreBtn) { moreBtn.disabled = false; moreBtn.innerHTML = moreLabel; }
    } else {
      btn.disabled=false; btn.innerHTML='<i class="ti ti-search me-1"></i>Cerca';
    }
  }
}

async function loadMoreResults() {
  if (_loadingMore || _searchExhausted) return;
  _searchPage += 1;
  await doSearch({append: true});
}

// ── Start page ────────────────────────────────────────────────────────────────
//
// With nothing typed, the source's own front page: what is trending, what was
// added lately, today's top ten, the latest anime episodes. It is decoration, so
// it degrades to a bare search box rather than to an error banner — a red box
// where a carousel was is worse than no carousel.

let _homeAbort = null;
const _homeCache = {};   // source -> shelves, for a switch back and forth

// ── Continua a guardare (Continue Watching) ──────────────────────────────────

let _continueWatchingItems = [];
let _currentCwModalItem = null;

function formatCwTime(seconds) {
  const s = Math.round(seconds || 0);
  if (s < 60) return '< 1 min';
  const mins = Math.floor(s / 60);
  if (mins < 60) return `${mins} min`;
  const hrs = Math.floor(mins / 60);
  const remMins = mins % 60;
  return remMins > 0 ? `${hrs}h ${remMins}m` : `${hrs}h`;
}

async function loadContinueWatching() {
  const section = document.getElementById('continue-watching-section');
  if (!section) return;
  try {
    const res = await api.get('/api/continue-watching');
    _continueWatchingItems = res.items || [];
    renderContinueWatchingRail();
  } catch (err) {
    console.warn('Error loading continue watching:', err);
  }
}

function refreshContinueWatching() {
  loadContinueWatching();
}
window.refreshContinueWatching = refreshContinueWatching;

function renderContinueWatchingRail() {
  const section = document.getElementById('continue-watching-section');
  const rail = document.getElementById('continue-watching-rail');
  const badge = document.getElementById('cw-count-badge');
  if (!section || !rail) return;

  const isSearchEmpty = !document.getElementById('search-input')?.value?.trim();
  if (!_continueWatchingItems.length || !isSearchEmpty) {
    section.style.display = 'none';
    rail.innerHTML = '';
    return;
  }

  section.style.display = '';
  if (badge) {
    badge.textContent = `${_continueWatchingItems.length}`;
    badge.style.display = 'inline-block';
  }

  rail.innerHTML = '';
  _continueWatchingItems.forEach((item) => {
    const col = document.createElement('div');
    col.className = 'shelf-item cw-item';
    col.dataset.cwId = item.id;

    const pUrl = item.poster ? posterUrl(item) : '';
    const remStr = `${formatCwTime(item.remaining_seconds)} rimasti`;
    const pct = Math.min(100, Math.max(0, item.percentage || 0));

    let typeBadgeLabel = 'Film';
    let typeBadgeCls = 'bg-blue';
    if (item.content_type === 'tv') {
      typeBadgeLabel = item.season_number ? `S${item.season_number}:E${item.episode_number || 1}` : 'Serie TV';
      typeBadgeCls = 'bg-green';
    }

    col.innerHTML = `
      <div class="result-card cw-card" data-action="cw:open-details" data-cw-id="${escapeHtml(item.id)}" title="${escapeHtml(item.title)}">
        <div class="poster-wrap">
          ${pUrl ? `<img src="${encodeURI(pUrl)}" alt="${escapeHtml(item.title)}" loading="lazy">` : `<div class="poster-noimg"><i class="ti ti-movie"></i></div>`}
          <div class="poster-overlay"></div>
          <div class="cw-badge-top">
            <span class="badge ${typeBadgeCls}">${typeBadgeLabel}</span>
          </div>
          <div class="cw-quick-play" title="Continua a guardare subito" data-action="cw:quick-resume" data-cw-id="${escapeHtml(item.id)}">
            <i class="ti ti-player-play-filled"></i>
          </div>
          <div class="cw-progress-bar-wrap">
            <div class="cw-progress-bar" style="width: ${pct}%"></div>
          </div>
        </div>
        <div class="card-meta">
          <div class="card-title-text">${escapeHtml(item.title)}</div>
          <div class="d-flex align-items-center justify-content-between" style="font-size:11px; color:var(--text-dim);">
            <span>${remStr}</span>
            <span class="text-success fw-bold">${pct}%</span>
          </div>
          ${item.content_type === 'tv' && item.episode_title ? `
            <div class="text-truncate mt-1" style="font-size:11px; color:var(--text-muted);" title="${escapeHtml(item.episode_title)}">
              ${escapeHtml(item.episode_title)}
            </div>
          ` : ''}
        </div>
      </div>
    `;

    rail.appendChild(col);
  });

  _wireShelfArrows(section);
}

function openContinueWatchingDetails(cwId) {
  const item = _continueWatchingItems.find(i => i.id === cwId);
  if (!item) return;
  _currentCwModalItem = item;

  const modal = document.getElementById('continue-watching-modal');
  if (!modal) return;

  const posterEl = document.getElementById('cw-modal-poster');
  const titleEl = document.getElementById('cw-modal-title');
  const subtitleEl = document.getElementById('cw-modal-subtitle');
  const typeBadgeEl = document.getElementById('cw-modal-type-badge');
  const timeBadgeEl = document.getElementById('cw-modal-time-badge');
  const progTextEl = document.getElementById('cw-modal-progress-text');
  const progPctEl = document.getElementById('cw-modal-progress-pct');
  const progBarEl = document.getElementById('cw-modal-progress-bar');

  const pUrl = item.poster ? posterUrl(item) : '';
  if (posterEl) {
    posterEl.src = pUrl || '';
    posterEl.style.display = pUrl ? 'block' : 'none';
  }

  if (titleEl) titleEl.textContent = item.title;

  if (item.content_type === 'tv') {
    if (typeBadgeEl) {
      typeBadgeEl.textContent = item.season_number ? `Stagione ${item.season_number}` : 'Serie TV';
      typeBadgeEl.className = 'badge bg-green-lt';
    }
    if (subtitleEl) {
      const epNum = item.episode_number ? `Episodio ${item.episode_number}` : 'Episodio';
      subtitleEl.textContent = item.episode_title ? `${epNum} — ${item.episode_title}` : epNum;
      subtitleEl.style.display = 'block';
    }
  } else {
    if (typeBadgeEl) {
      typeBadgeEl.textContent = 'Film';
      typeBadgeEl.className = 'badge bg-blue-lt';
    }
    if (subtitleEl) subtitleEl.style.display = 'none';
  }

  const posStr = formatCwTime(item.position_seconds);
  const durStr = formatCwTime(item.duration_seconds);
  const remStr = formatCwTime(item.remaining_seconds);
  const pct = Math.min(100, Math.max(0, item.percentage || 0));

  if (timeBadgeEl) timeBadgeEl.textContent = `${remStr} rimanenti`;
  if (progTextEl) progTextEl.textContent = `${posStr} di ${durStr}`;
  if (progPctEl) progPctEl.textContent = `${pct}%`;
  if (progBarEl) {
    progBarEl.style.width = `${pct}%`;
  }

  showModal('continue-watching-modal');
}

function resumeContinueWatching(cwId) {
  const item = _continueWatchingItems.find(i => i.id === cwId);
  if (!item) return;

  hideModal('continue-watching-modal');

  if (typeof openStreamPlayer === 'function') {
    openStreamPlayer({
      type: item.content_type,
      id: item.content_id,
      slug: item.slug || '',
      title: item.title,
      poster: item.poster,
      episodeId: item.episode_id,
      episodeNumber: item.episode_number,
      seasonNumber: item.season_number,
      episodeTitle: item.episode_title,
      startTime: item.position_seconds,
    });
  }
}

function restartContinueWatching(cwId) {
  const item = _continueWatchingItems.find(i => i.id === cwId);
  if (!item) return;

  hideModal('continue-watching-modal');

  if (typeof openStreamPlayer === 'function') {
    openStreamPlayer({
      type: item.content_type,
      id: item.content_id,
      slug: item.slug || '',
      title: item.title,
      poster: item.poster,
      episodeId: item.episode_id,
      episodeNumber: item.episode_number,
      seasonNumber: item.season_number,
      episodeTitle: item.episode_title,
      startTime: 0,
    });
  }
}

async function deleteContinueWatching(cwId) {
  const item = _continueWatchingItems.find(i => i.id === cwId);
  if (!item) return;

  hideModal('continue-watching-modal');

  try {
    await api.post('/api/continue-watching/delete', {
      content_type: item.content_type,
      content_id: item.content_id,
    });
    _continueWatchingItems = _continueWatchingItems.filter(i => i.id !== cwId);
    renderContinueWatchingRail();
  } catch (err) {
    console.error('Failed to delete continue watching item', err);
  }
}

function gotoCwTitle() {
  if (!_currentCwModalItem) return;
  const item = _currentCwModalItem;
  hideModal('continue-watching-modal');
  const kind = item.content_type === 'movie' ? 'movie' : 'tv';
  _tpSeed = {
    id: item.content_id,
    type: kind,
    slug: item.slug || '',
    name: item.title,
    poster: item.poster,
    cw: item,
  };
  navigate('detail', [kind, item.content_id, item.slug || '']);
}

function _setStartPageVisible(on) {
  const shelves = document.getElementById('home-shelves');
  const results = document.getElementById('search-results');
  const hero = document.getElementById('search-hero');
  const filters = document.getElementById('search-filters');
  const categories = document.getElementById('home-categories');
  const cwSection = document.getElementById('continue-watching-section');
  if (hero) hero.style.display = on ? '' : 'none';
  if (categories) categories.style.display = on ? '' : 'none';
  if (filters) filters.style.display = on ? 'none' : '';
  if (shelves) shelves.style.display = on ? '' : 'none';
  if (results) results.style.display = on ? 'none' : '';
  if (cwSection) cwSection.style.display = (on && _continueWatchingItems && _continueWatchingItems.length) ? '' : 'none';
  if (on) _setMoreVisible(false);
}

function resetSearchHome() {
  const input = document.getElementById('search-input');
  if (input) input.value = '';
  _searchResults = [];
  _searchPage = 1;
  _searchExhausted = false;
  _kindFilter = '';
  _dubOnly = false;
  const res = document.getElementById('search-results');
  if (res) res.innerHTML = '';
  renderSearchFilters();
  showStartPage();
  if (typeof syncHash === 'function') syncHash('search');
}
window.resetSearchHome = resetSearchHome;

// What happens on arriving at the search/home page, from the nav or from a link.
function searchPageEnter() {
  const input = document.getElementById('search-input');
  const route = typeof parseHash === 'function' ? parseHash() : null;
  const hasQueryInUrl = Boolean(route && route.page === 'search' && route.params && route.params.q && route.params.q.trim());

  if (!hasQueryInUrl && input && input.value) {
    input.value = '';
    _searchResults = [];
    const res = document.getElementById('search-results');
    if (res) res.innerHTML = '';
  }

  if (!input || !input.value.trim()) { showStartPage(); return; }
  if (!_searchResults.length) doSearch();
  else _setStartPageVisible(false);
}


let _currentSpotlightItem = null;
let _spotlightCandidates = [];
let _spotlightIdx = 0;

function _updateSpotlight(item) {
  _currentSpotlightItem = item;
  const spotlightEl = document.getElementById('sh-spotlight');
  const defaultEl = document.getElementById('sh-default-hero');
  if (!item || !spotlightEl) {
    if (spotlightEl) spotlightEl.style.display = 'none';
    if (defaultEl) defaultEl.style.display = '';
    return;
  }

  const titleEl = document.getElementById('sh-spotlight-title');
  const scoreEl = document.getElementById('sh-spotlight-score');
  const yearEl = document.getElementById('sh-spotlight-year');
  const typeEl = document.getElementById('sh-spotlight-type');
  const plotEl = document.getElementById('sh-spotlight-plot');

  if (titleEl) titleEl.textContent = item.name || 'Titolo consigliato';
  if (scoreEl) {
    if (item.score) {
      scoreEl.style.display = 'inline-flex';
      scoreEl.innerHTML = `<i class="ti ti-star-filled me-1 text-warning"></i>${escapeHtml(item.score)}`;
    } else {
      scoreEl.style.display = 'none';
    }
  }
  const year = item.release_date?.substring(0, 4) || item.last_air_date?.substring(0, 4) || '';
  if (yearEl) yearEl.textContent = year;
  if (typeEl) {
    typeEl.textContent = item.type === 'movie' ? 'Film' : 'Serie TV';
    typeEl.className = item.type === 'movie' ? 'badge bg-blue-lt' : 'badge bg-green-lt';
  }
  if (plotEl) {
    plotEl.textContent = item.plot || 'Guarda subito in streaming ad alta definizione sul nostro player in-app senza interruzioni o scarica con un click.';
  }

  const art = document.getElementById('search-hero-art');
  if (art && item.poster) {
    const poster = posterUrl(item);
    art.innerHTML = `<span style="background-image:url('${encodeURI(poster)}'); opacity:0.38; filter:blur(1px); transform:scale(1.08);"></span>`;
  }

  if (defaultEl) defaultEl.style.display = 'none';
  spotlightEl.style.display = 'block';
}

function _shelfSkeletons() {
  const card = '<div class="shelf-item"><div class="skeleton skeleton-card"></div></div>';
  return ('<div class="shelf"><div class="shelf-head"><div class="skeleton" style="width:200px; height:24px; border-radius:4px;"></div></div><div class="shelf-rail-wrap"><div class="shelf-rail">' + card.repeat(8) + '</div></div></div>').repeat(3);
}

async function showStartPage() {
  const host = document.getElementById('home-shelves');
  if (!host) return;
  await ensureDomain();
  if (!currentDomain) { _setStartPageVisible(false); return; }

  _setStartPageVisible(true);
  loadContinueWatching();
  const cat = _homeCategory || 'all';
  const cacheKey = `sc_${cat}`;

  if (_homeCache[cacheKey] && _homeCache[cacheKey].length) {
    renderShelves();
    return;
  }

  if (_homeAbort) _homeAbort.abort();
  _homeAbort = new AbortController();
  host.innerHTML = _shelfSkeletons();
  try {
    const body = await api.get('/api/home', {source: 'streamingcommunity', category: cat}, {signal: _homeAbort.signal});
    _homeCache[cacheKey] = body.shelves || [];
    renderShelves();
  } catch (e) {
    if (e.name === 'AbortError') return;
    host.innerHTML = '<div class="p-4 text-center text-muted">Impossibile caricare i titoli della home. Riprova tra poco.</div>';
  }
}

// The start page's own backdrop: a handful of titles the source is showing
// today, behind the headline. Decoration, so it is drawn from what has
// already been fetched and simply stays empty when there is nothing.
function _renderHeroArt(items) {
  const art = document.getElementById('search-hero-art');
  if (!art) return;
  const withArt = items.filter(i => i.poster);
  if (!withArt.length) { art.innerHTML = ''; return; }
  const pool = [...withArt];
  const picked = [];
  while (picked.length < 7 && pool.length) {
    picked.push(pool.splice(Math.floor(Math.random() * pool.length), 1)[0]);
  }
  art.innerHTML = picked
    .map(i => `<span style="background-image:url('${encodeURI(posterUrl(i))}')"></span>`)
    .join('');
}

function renderShelves() {
  const host = document.getElementById('home-shelves');
  const cat = _homeCategory || 'all';
  const cacheKey = `sc_${cat}`;
  const shelves = _homeCache[cacheKey] || [];
  host.innerHTML = '';
  // One flat array across every rail, reset once here and appended to in order,
  // so openTitle(idx) needs no special case for the start page.
  _searchResults = [];
  _requestStatus = {};
  const ribbonIds = [];
  const spotlightPool = [];

  _shelfSyncs = [];
  shelves.forEach(shelf => {
    const section = document.createElement('div');
    section.className = 'shelf';
    section.dataset.shelfCategory = shelf.category || 'all';

    let catBadge = '';
    if (shelf.category === 'movie') {
      catBadge = '<span class="badge bg-blue-lt ms-2" style="font-size:11px;font-weight:600;padding:2px 8px;border-radius:4px">Film</span>';
    } else if (shelf.category === 'tv') {
      catBadge = '<span class="badge bg-green-lt ms-2" style="font-size:11px;font-weight:600;padding:2px 8px;border-radius:4px">Serie TV</span>';
    }

    section.innerHTML =
      `<div class="shelf-head"><div class="shelf-title d-flex align-items-center">${escapeHtml(shelf.title)}${catBadge}</div></div>` +
      '<div class="shelf-rail-wrap">' +
        '<button class="shelf-arrow shelf-arrow-prev" hidden aria-label="Titoli precedenti">' +
          '<i class="ti ti-chevron-left"></i></button>' +
        '<div class="shelf-rail"></div>' +
        '<button class="shelf-arrow shelf-arrow-next" hidden aria-label="Titoli successivi">' +
          '<i class="ti ti-chevron-right"></i></button>' +
      '</div>';
    renderResultCards(shelf.items, section.querySelector('.shelf-rail'),
                      _searchResults.length, 'shelf-item');
    _searchResults = _searchResults.concat(shelf.items);
    shelf.items.forEach(i => {
      if (i.type !== 'movie') ribbonIds.push(String(i.id));
      if (i.poster) spotlightPool.push(i);
    });
    host.appendChild(section);
    _shelfSyncs.push(_wireShelfArrows(section));
  });

  // Setup Netflix Spotlight candidates
  if (spotlightPool.length) {
    _spotlightCandidates = spotlightPool.slice(0, 15);
    _spotlightIdx = 0;
    _updateSpotlight(_spotlightCandidates[0]);
  } else {
    _updateSpotlight(null);
  }

  loadRequestStatuses(ribbonIds);
}

// The arrows scroll a few titles at a time rather than a whole screenful: the
// rail is a browse, and losing your place in it is worse than taking two clicks.
// Each one hides itself at the end it points at, so a rail that already fits
// shows neither.
let _shelfSyncs = [];

function _wireShelfArrows(section) {
  const rail = section.querySelector('.shelf-rail');
  const prev = section.querySelector('.shelf-arrow-prev');
  const next = section.querySelector('.shelf-arrow-next');

  function step() {
    const card = rail.querySelector('.shelf-item:not(.d-none)');
    const one = (card ? card.offsetWidth : 132) + 12;   // the rail's gap
    return Math.max(one, Math.min(one * 3, Math.floor(rail.clientWidth / one) * one));
  }

  function sync() {
    const max = rail.scrollWidth - rail.clientWidth;
    const scrollable = max > 4;   // a couple of pixels of rounding is not overflow
    prev.hidden = !scrollable || rail.scrollLeft <= 2;
    next.hidden = !scrollable || rail.scrollLeft >= max - 2;
  }

  let ticking = false;
  function onScroll() {
    if (!ticking) {
      window.requestAnimationFrame(() => {
        sync();
        ticking = false;
      });
      ticking = true;
    }
  }

  prev.addEventListener('click', () => rail.scrollBy({left: -step(), behavior: 'smooth'}));
  next.addEventListener('click', () => rail.scrollBy({left: step(), behavior: 'smooth'}));
  rail.addEventListener('scroll', onScroll, {passive: true});

  // Smooth mouse drag-to-scroll support
  let isDown = false;
  let startX = 0;
  let scrollLeftStart = 0;
  let hasMoved = false;

  rail.addEventListener('mousedown', (e) => {
    if (e.button !== 0 || e.target.closest('button')) return;
    isDown = true;
    hasMoved = false;
    startX = e.pageX - rail.offsetLeft;
    scrollLeftStart = rail.scrollLeft;
  });

  const onGlobalMouseUp = () => {
    if (isDown) {
      isDown = false;
      rail.classList.remove('is-dragging');
    }
  };
  window.addEventListener('mouseup', onGlobalMouseUp);

  rail.addEventListener('mousemove', (e) => {
    if (!isDown) return;
    const x = e.pageX - rail.offsetLeft;
    const walk = (x - startX);
    if (Math.abs(walk) > 4) {
      hasMoved = true;
      rail.classList.add('is-dragging');
      rail.scrollLeft = scrollLeftStart - walk;
    }
  });

  rail.addEventListener('click', (e) => {
    if (hasMoved) {
      e.preventDefault();
      e.stopPropagation();
      hasMoved = false;
    }
  }, true);

  sync();
  return sync;
}

function _syncShelfArrows() {
  _shelfSyncs.forEach(sync => sync());
}

window.addEventListener('resize', _syncShelfArrows);

function applyCategoryFilter() {
  const host = document.getElementById('home-shelves');
  if (!host) return;
  host.querySelectorAll('.shelf').forEach(section => {
    const shelfCat = section.dataset.shelfCategory || 'all';
    let visibleCards = 0;
    section.querySelectorAll('.shelf-item').forEach(card => {
      const item = _searchResults[Number(card.dataset.idx)];
      if (!item) return;
      let showCard = true;
      if (_homeCategory === 'movie') {
        showCard = (shelfCat === 'movie') || (item.type === 'movie');
      } else if (_homeCategory === 'tv') {
        showCard = (shelfCat === 'tv') || (item.type === 'tv');
      }
      card.classList.toggle('d-none', !showCard);
      if (showCard) visibleCards++;
    });

    const showSection = (_homeCategory === 'all')
      ? true
      : ((shelfCat === _homeCategory || shelfCat === 'all') && visibleCards > 0);

    section.classList.toggle('d-none', !showSection);
  });
  _syncShelfArrows();
}

function applyClientFilter() {
  applyCategoryFilter();
}

// ── Request status on the result cards ─────────────────────────────────────────
//
// The one thing worth taking from Seerr: the state of a title is readable on the
// card itself, without opening anything.

const STATUS_RIBBONS = {
  pending:         { label: 'Richiesto',    cls: 'ribbon-pending',   icon: 'ti-clock' },
  approved:        { label: 'Approvato',    cls: 'ribbon-approved',  icon: 'ti-check' },
  downloading:     { label: 'In download',  cls: 'ribbon-download',  icon: 'ti-download' },
  // Not "Disponibile": the panel never learns how many episodes a series has
  // without asking the source, and this ribbon is painted from one call that
  // decorates a whole page of cards. "In libreria" is what it can actually
  // vouch for — the count says how much, instead of implying all of it.
  completed:       { label: 'In libreria',  cls: 'ribbon-available', icon: 'ti-circle-check' },
  available:       { label: 'In libreria',  cls: 'ribbon-available', icon: 'ti-circle-check' },
  denied:          { label: 'Rifiutato',    cls: 'ribbon-denied',    icon: 'ti-x' },
  failed:          { label: 'Fallito',      cls: 'ribbon-denied',    icon: 'ti-alert-triangle' },
  needs_attention: { label: 'Attenzione',   cls: 'ribbon-attention', icon: 'ti-alert-circle' },
  cancelled:       { label: 'Annullato',    cls: 'ribbon-denied',    icon: 'ti-ban' },
};

async function loadRequestStatuses(externalIds) {
  if (!externalIds.length || !(can('REQUEST') || can('DOWNLOAD'))) return;
  try {
    const statuses = await api.post('/api/requests/status',
      { source: currentSource, external_ids: externalIds });
    // Merged, not replaced. Called with only the new page's ids, an
    // assignment would wipe every ribbon already painted on the pages
    // before it, because renderRequestRibbons re-reads the whole map.
    // Staleness is bounded: _requestStatus is cleared on every fresh
    // search and on a source switch.
    Object.assign(_requestStatus, statuses);
    renderRequestRibbons();
  } catch (e) { /* the cards simply stay plain */ }
}

const IN_LIBRARY_STATUSES = new Set(['completed', 'available']);

// What the ribbon can add without overstating: one episode names itself, more
// than one is counted. The server sends season and episode_number precisely so
// this does not have to guess, and a film is never counted — it is one file,
// and films carry no ribbon anyway.
function ribbonDetail(info) {
  if (!IN_LIBRARY_STATUSES.has(info.status) || info.media_type === 'film') return '';
  const n = info.library_count || 0;
  if (n === 1 && info.season != null && info.episode_number != null) {
    const pad = v => String(v).padStart(2, '0');
    return `S${pad(info.season)}E${pad(info.episode_number)}`;
  }
  return n ? `${n} ep` : '';
}

function renderRequestRibbons() {
  document.querySelectorAll('[data-ribbon-for]').forEach(el => {
    const info = _requestStatus[el.dataset.ribbonFor];
    const style = info && STATUS_RIBBONS[info.status];
    if (!style) { el.innerHTML = ''; el.className = 'status-ribbon'; return; }
    const detail = ribbonDetail(info);
    el.className = `status-ribbon ${style.cls}`;
    el.innerHTML = `<i class="ti ${style.icon}"></i>${style.label}` +
      (detail ? `<span class="ribbon-count">${escapeHtml(detail)}</span>` : '');
  });
}


// ── Delegated handlers ───────────────────────────────────────────────────────

registerActions({
  'home:category':         d => setHomeCategory(d.cat),
  'home:spotlight-watch':   () => {
    if (!_currentSpotlightItem) return;
    if (typeof openStreamPlayer === 'function') {
      openStreamPlayer({
        type: _currentSpotlightItem.type,
        id: _currentSpotlightItem.id,
        slug: _currentSpotlightItem.slug,
        title: _currentSpotlightItem.name,
      });
    }
  },
  'home:spotlight-details': () => {
    if (!_currentSpotlightItem) return;
    location.hash = titleHash(_currentSpotlightItem);
  },
  'home:spotlight-next':    () => {
    if (!_spotlightCandidates.length) return;
    _spotlightIdx = (_spotlightIdx + 1) % _spotlightCandidates.length;
    _updateSpotlight(_spotlightCandidates[_spotlightIdx]);
  },
  'search:source':          d => setSource(d.source),
  'search:run':             () => doSearch(),
  'search:more':            () => loadMoreResults(),
  'search:kind':            d => setKindFilter(d.kind),
  'search:open':            d => openTitle(Number(d.idx)),
  'cw:open-details':        d => openContinueWatchingDetails(d.cwId),
  'cw:quick-resume':        (d, el, e) => { if (e) e.stopPropagation(); resumeContinueWatching(d.cwId); },
  'cw:modal-goto-title':    () => gotoCwTitle(),
  'cw:modal-resume':        () => { if (_currentCwModalItem) resumeContinueWatching(_currentCwModalItem.id); },
  'cw:modal-restart':       () => { if (_currentCwModalItem) restartContinueWatching(_currentCwModalItem.id); },
  'cw:modal-delete':        () => { if (_currentCwModalItem) deleteContinueWatching(_currentCwModalItem.id); },
});


// ── The address ──────────────────────────────────────────────────────────────
//
// The query is the page here, so it is what the link has to carry. The page
// number is not: restoring "page 4" would mean four requests to the source
// before anything appeared, and the results of pages 1-3 are what the user
// actually wants back first.

registerPageHash('search', {
  read: () => ({
    params: {
      q: document.getElementById('search-input')?.value.trim() || null,
      cat: _homeCategory !== 'all' ? _homeCategory : null,
      type: _kindFilter || null,
    },
  }),
  apply: params => {
    const input = document.getElementById('search-input');
    if (input) input.value = params.q || '';
    currentSource = 'streamingcommunity';
    if (input) input.placeholder = 'Cerca film o serie TV per titolo...';
    _kindFilter = params.type || '';
    if (params.cat) {
      setHomeCategory(params.cat);
    }
    _searchResults = [];
    _searchPage = 1;
    _searchExhausted = false;
    renderSearchFilters();
  },
});
