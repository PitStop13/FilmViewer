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
    <div class="search-grid" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 16px; margin-top: 16px;">
      ${filtered.map(item => {
        const isMovie = item.media_type === 'movie';
        const typeBadge = isMovie
          ? '<span class="badge bg-blue" style="position:absolute; top:8px; left:8px; z-index:2; font-size:11px;">Film</span>'
          : '<span class="badge bg-green" style="position:absolute; top:8px; left:8px; z-index:2; font-size:11px;">Serie TV</span>';
        const pUrl = item.poster ? (typeof posterUrl === 'function' ? posterUrl(item) : item.poster) : '';
        const scoreBadge = item.score ? `<span class="badge bg-dark text-warning border border-secondary" style="font-size:10.5px;"><i class="ti ti-star-filled me-1"></i>${escapeHtml(item.score)}</span>` : '';
        const yearStr = item.year ? `<span class="text-muted" style="font-size:11.5px;">${escapeHtml(item.year)}</span>` : '';

        return `
          <div class="result-card fav-card" style="position:relative; background:rgba(255,255,255,0.04); border-radius:10px; border:1px solid rgba(255,255,255,0.08); overflow:hidden; transition:transform 0.18s, box-shadow 0.18s;">
            ${typeBadge}
            <button class="btn btn-sm btn-danger fav-remove-btn" 
                    data-action="fav:remove" 
                    data-type="${escapeHtml(item.media_type)}" 
                    data-id="${escapeHtml(item.content_id)}" 
                    data-title="${escapeHtml(item.title)}"
                    title="Rimuovi dai Preferiti"
                    style="position:absolute; top:8px; right:8px; z-index:2; width:28px; height:28px; padding:0; display:flex; align-items:center; justify-content:center; border-radius:50%; box-shadow:0 2px 8px rgba(0,0,0,0.5);">
              <i class="ti ti-heart-filled" style="font-size:14px;"></i>
            </button>
            <div class="poster-wrap" 
                 data-action="fav:open" 
                 data-type="${escapeHtml(item.media_type)}" 
                 data-id="${escapeHtml(item.content_id)}" 
                 data-slug="${escapeHtml(item.slug || '')}"
                 style="position:relative; aspect-ratio:2/3; width:100%; cursor:pointer; background:#111; overflow:hidden;">
              ${pUrl
                ? `<img src="${encodeURI(pUrl)}" alt="${escapeHtml(item.title)}" loading="lazy" style="width:100%; height:100%; object-fit:cover; transition:transform 0.25s;">`
                : `<div class="poster-noimg" style="width:100%; height:100%; display:flex; align-items:center; justify-content:center; color:var(--text-sub);"><i class="ti ti-movie" style="font-size:32px;"></i></div>`}
              <div class="poster-overlay" style="position:absolute; inset:0; background:linear-gradient(to top, rgba(0,0,0,0.85) 0%, transparent 50%); display:flex; align-items:flex-end; padding:10px;">
                <button class="btn btn-success btn-sm w-100" 
                        data-action="fav:play" 
                        data-type="${escapeHtml(item.media_type)}" 
                        data-id="${escapeHtml(item.content_id)}" 
                        data-slug="${escapeHtml(item.slug || '')}"
                        data-title="${escapeHtml(item.title)}"
                        data-poster="${escapeHtml(item.poster || '')}"
                        title="Guarda ora">
                  <i class="ti ti-player-play-filled me-1"></i>Guarda
                </button>
              </div>
            </div>
            <div class="card-body" 
                 data-action="fav:open" 
                 data-type="${escapeHtml(item.media_type)}" 
                 data-id="${escapeHtml(item.content_id)}" 
                 data-slug="${escapeHtml(item.slug || '')}"
                 style="padding:10px; cursor:pointer;">
              <div class="title" style="font-weight:600; font-size:13px; line-height:1.3; margin-bottom:4px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${escapeHtml(item.title)}">
                ${escapeHtml(item.title)}
              </div>
              <div class="d-flex align-items:center justify-content:space-between" style="font-size:11px;">
                ${yearStr}
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
