/* FilmViewer — page-favorites.js */
//
// I miei Preferiti (Favorites / Mi piace)
// Permette di salvare film e serie TV con un clic sul cuore ❤️ e ritrovarli facilmente.

let _favorites = [];
let _favFilter = 'all'; // 'all' | 'movie' | 'tv'

async function loadFavorites() {
  const c = document.getElementById('favorites-list');
  if (!c) return;
  try {
    const q = _favFilter && _favFilter !== 'all' ? { type: _favFilter } : {};
    const data = await api.get('/api/favorites', q);
    _favorites = data.items || [];
    renderFavoritesList();
  } catch (e) {
    c.innerHTML = `<p class="text-muted">${escapeHtml(errText(e, 'Impossibile caricare i preferiti.'))}</p>`;
  }
}
window.loadFavorites = loadFavorites;
window.loadWatches = loadFavorites;

function renderFavoritesStats() {
  const el = document.getElementById('favorites-stats');
  if (!el) return;
  const movies = _favorites.filter(f => f.media_type === 'movie').length;
  const series = _favorites.filter(f => f.media_type === 'tv').length;
  const chips = [
    [_favorites.length, 'Totale', 'pg-stat-live'],
    [movies, 'Film', 'pg-stat-ok'],
    [series, 'Serie TV', 'pg-stat-warn'],
  ];
  el.innerHTML = chips.map(([value, label, cls]) =>
    `<span class="pg-stat ${value ? cls : 'pg-stat-zero'}"><b>${value}</b><span>${label}</span></span>`
  ).join('');
}

function renderFavoritesList() {
  const c = document.getElementById('favorites-list');
  if (!c) return;
  renderFavoritesStats();

  const filtered = _favorites.filter(item => {
    if (_favFilter === 'movie') return item.media_type === 'movie';
    if (_favFilter === 'tv') return item.media_type === 'tv';
    return true;
  });

  if (!filtered.length) {
    c.innerHTML = `
      <div class="empty-panel" style="padding: 60px 20px; text-align: center;">
        <i class="ti ti-heart-broken" style="font-size: 48px; color: var(--text-sub); opacity: 0.7; margin-bottom: 12px; display: inline-block;"></i>
        <h3 style="margin-bottom: 8px;">Nessun preferito salvato</h3>
        <p class="text-muted" style="font-size: 13.5px; max-width: 420px; margin: 0 auto;">
          ${_favFilter !== 'all'
            ? `Non hai ancora aggiunto alcun ${_favFilter === 'movie' ? 'film' : 'serie TV'} ai preferiti.`
            : 'Clicca sul cuore ❤️ su qualsiasi film o serie TV per salvarlo qui e ritrovarlo facilmente.'}
        </p>
      </div>`;
    return;
  }

  c.innerHTML = `
    <div class="fav-grid">
      ${filtered.map(item => {
        const isMovie = item.media_type === 'movie';
        const typeBadge = isMovie
          ? '<span class="badge bg-blue fav-type-badge">Film</span>'
          : '<span class="badge bg-green fav-type-badge">Serie TV</span>';
        const pUrl = item.poster ? (typeof posterUrl === 'function' ? posterUrl(item) : item.poster) : '';
        const scoreBadge = item.score
          ? `<span class="fav-card-score"><i class="ti ti-star-filled me-1"></i>${escapeHtml(item.score)}</span>`
          : '';
        const yearStr = item.year ? escapeHtml(item.year) : (isMovie ? 'Film' : 'Serie TV');

        return `
          <div class="fav-card" tabindex="0">
            ${typeBadge}
            <button class="fav-heart-btn" 
                    data-action="fav:remove" 
                    data-type="${escapeHtml(item.media_type)}" 
                    data-id="${escapeHtml(item.content_id)}" 
                    data-title="${escapeHtml(item.title)}"
                    title="Rimuovi dai Preferiti">
              <i class="ti ti-heart-filled"></i>
            </button>
            <div class="fav-poster-wrap" 
                 data-action="fav:open" 
                 data-type="${escapeHtml(item.media_type)}" 
                 data-id="${escapeHtml(item.content_id)}" 
                 data-slug="${escapeHtml(item.slug || '')}"
                 title="${escapeHtml(item.title)}">
              ${pUrl
                ? `<img src="${encodeURI(pUrl)}" alt="${escapeHtml(item.title)}" loading="lazy">`
                : `<div class="poster-noimg" style="width:100%; height:100%; display:flex; align-items:center; justify-content:center; color:var(--text-sub);"><i class="ti ti-movie" style="font-size:32px;"></i></div>`}
              <button class="fav-quick-play" 
                      data-action="fav:play" 
                      data-type="${escapeHtml(item.media_type)}" 
                      data-id="${escapeHtml(item.content_id)}" 
                      data-slug="${escapeHtml(item.slug || '')}"
                      data-title="${escapeHtml(item.title)}"
                      data-poster="${escapeHtml(item.poster || '')}"
                      title="Guarda ora">
                <i class="ti ti-player-play-filled"></i>
              </button>
            </div>
            <div class="fav-card-body" 
                 data-action="fav:open" 
                 data-type="${escapeHtml(item.media_type)}" 
                 data-id="${escapeHtml(item.content_id)}" 
                 data-slug="${escapeHtml(item.slug || '')}"
                 title="${escapeHtml(item.title)}">
              <div class="fav-card-title">${escapeHtml(item.title)}</div>
              <div class="fav-card-meta">
                <span class="fav-card-year">${yearStr}</span>
                ${scoreBadge}
              </div>
            </div>
          </div>`;
      }).join('')}
    </div>`;
}

function setFavoritesFilter(type) {
  _favFilter = type || 'all';
  document.getElementById('fav-filter-all')?.classList.toggle('active', _favFilter === 'all');
  document.getElementById('fav-filter-movie')?.classList.toggle('active', _favFilter === 'movie');
  document.getElementById('fav-filter-tv')?.classList.toggle('active', _favFilter === 'tv');
  renderFavoritesList();
}

async function removeFavoriteItem(mediaType, contentId, title) {
  try {
    await api.del(`/api/favorites/${mediaType}/${contentId}`);
    _favorites = _favorites.filter(f => !(f.media_type === mediaType && String(f.content_id) === String(contentId)));
    renderFavoritesList();
    showToast(`«${title || 'Titolo'}» rimosso dai Preferiti`, 'info');
  } catch (e) {
    showToast(errText(e, 'Errore rimozione dai preferiti'), 'danger');
  }
}

// ── Delegated handlers ───────────────────────────────────────────────────────

registerActions({
  'fav:reload': () => loadFavorites(),
  'fav:filter': d => setFavoritesFilter(d.type),
  'fav:open': d => {
    navigate('detail', [d.type, d.id, d.slug || '']);
  },
  'fav:play': (d, el, e) => {
    if (e) e.stopPropagation();
    if (typeof openStreamPlayer === 'function') {
      openStreamPlayer({
        type: d.type,
        id: d.id,
        slug: d.slug || '',
        title: d.title || '',
        poster: d.poster || null,
      });
    }
  },
  'fav:remove': (d, el, e) => {
    if (e) e.stopPropagation();
    removeFavoriteItem(d.type, d.id, d.title);
  },
});

registerPageHash('favorites', {
  read: () => ({ params: { type: _favFilter !== 'all' ? _favFilter : null } }),
  apply: params => {
    _favFilter = params.type || 'all';
    document.getElementById('fav-filter-all')?.classList.toggle('active', _favFilter === 'all');
    document.getElementById('fav-filter-movie')?.classList.toggle('active', _favFilter === 'movie');
    document.getElementById('fav-filter-tv')?.classList.toggle('active', _favFilter === 'tv');
  },
});
