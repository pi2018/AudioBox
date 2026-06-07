
// ══════════════════════════════════════════════════════
// État global
// ══════════════════════════════════════════════════════
let token    = localStorage.getItem('ab_token') || '';
let isPlaying = false;
window._absItems = [];  // Items ABS globaux
let pState   = {playing:false,paused:false,position:0,duration:0,volume:80};
let currentItem = null;
let ws;

const SCREENS = {
  home:      '',
  abs:       'Livre audio',
  player:    'Lecture livre',
  nas:       'Musique NAS',
  youtube:   'YouTube',
  radios:    'Web Radio',
  podcasts:  'Podcasts',
  settings:  'Paramètres',
};

// ══════════════════════════════════════════════════════
// Utilitaires
// ══════════════════════════════════════════════════════
function toast(msg) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = 'show';
  clearTimeout(el._t);
  el._t = setTimeout(() => el.className = '', 2800);
}

function fmtTime(s) {
  s = Math.floor(s || 0);
  const h = Math.floor(s/3600), m = Math.floor((s%3600)/60), ss = s%60;
  return h > 0
    ? `${h}:${m.toString().padStart(2,'0')}:${ss.toString().padStart(2,'0')}`
    : `${m}:${ss.toString().padStart(2,'0')}`;
}

async function api(method, path, body) {
  const opts = {method, headers:{'Content-Type':'application/json'}};
  if (token) opts.headers['Authorization'] = `Bearer ${token}`;
  if (body)  opts.body = JSON.stringify(body);
  const r = await fetch('/api' + path, opts);
  if (!r.ok) {
    const e = await r.json().catch(() => ({}));
    throw new Error(e.detail || `HTTP ${r.status}`);
  }
  return r.json();
}

// ══════════════════════════════════════════════════════
// Navigation
// ══════════════════════════════════════════════════════
function showScreen(name) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  const el = document.getElementById('screen-' + name);
  if (el) el.classList.add('active');

  document.getElementById('page-title').textContent = SCREENS[name] || '';
  document.getElementById('btn-home').classList.toggle('active', name === 'home');
  document.getElementById('btn-settings').classList.toggle('active', name === 'settings');

  if (name === 'home')      loadRecent();
  if (name === 'abs')       loadABS();
  if (name === 'radios')    loadRadios();
  if (name === 'podcasts')  loadPodcasts();
  if (name === 'settings')  initSettings();
  if (name === 'nas')       browseNAS('/opt/jv/nas');
}

async function loadRecent() {
  // Ces éléments n'existent plus — fonction désactivée
  return;
  const recentList = document.getElementById('home-recent-list');
  const libGrid    = document.getElementById('home-lib-grid');

  try {
    const data = await api('GET', '/abs/libraries');
    const libs = data.libraries || [];

    if (!libs.length) {
      recentList.innerHTML = '<div style="color:var(--txt3);font-size:13px;padding:8px 0">Configurez Audiobookshelf dans Paramètres</div>';
      libGrid.innerHTML    = '';
      return;
    }

    let inProgress = [];
    let allBooks   = [];

    for (const lib of libs) {
      try {
        const items   = await api('GET', `/abs/libraries/${lib.id}/items?limit=100`);
        const results = items.results || items.items || [];
        results.forEach(item => {
          allBooks.push(item);
          const prog = item.userMediaProgress;
          if (prog && prog.progress > 0.01 && !prog.isFinished) {
            inProgress.push(item);
          }
        });
      } catch(e) {}
    }

    // Trier en cours par dernière mise à jour
    inProgress.sort((a, b) => (b.userMediaProgress?.lastUpdate||0) - (a.userMediaProgress?.lastUpdate||0));
    inProgress = inProgress.slice(0, 10);

    // ── Livres en cours ──────────────────────────────────────
    if (!inProgress.length) {
      recentList.innerHTML = '<div style="color:var(--txt3);font-size:13px;padding:8px 0">Aucun livre en cours</div>';
    } else {
      recentList.innerHTML = '';
      inProgress.forEach(item => {
        const title  = item.media?.metadata?.title || '—';
        const prog   = item.userMediaProgress?.progress || 0;
        const pct    = Math.round(prog * 100);
        const pos    = item.userMediaProgress?.currentTime || 0;
        const dur    = item.media?.duration || 0;
        const remain = dur > 0 ? Math.max(0, dur - pos) : 0;

        const card = document.createElement('div');
        card.className = 'recent-card';
        card.dataset.idx = window._absItems ? window._absItems.indexOf(item) : 0;
        card.addEventListener("click", function(){ var idx=this.dataset.idx; openBook(window._absItems ? window._absItems[idx] : item); });
        card.innerHTML = `
          <div class="rc-cover">
            <img src="/api/abs/cover/${item.id}" onerror="this.parentElement.textContent='📚'" loading="lazy">
          </div>
          <div class="rc-info">
            <div class="rc-title" title="${title}">${title}</div>
            <div class="rc-progress"><div class="rc-progress-fill" style="width:${pct}%"></div></div>
            <div class="rc-time">${pct}% · ${fmtTime(remain)} restant</div>
          </div>`;
        recentList.appendChild(card);
      });
    }

    // ── Bibliothèque complète ────────────────────────────────
    if (!allBooks.length) {
      libGrid.innerHTML = '<div style="color:var(--txt3);font-size:13px;grid-column:1/-1">Aucun livre</div>';
    } else {
      libGrid.innerHTML = '';
      allBooks.forEach(item => {
        const title  = item.media?.metadata?.title || '—';
        const author = item.media?.metadata?.authorName || '';
        const prog   = item.userMediaProgress?.progress || 0;
        const pct    = Math.round(prog * 100);

        const card = document.createElement('div');
        card.className = 'home-book-card';
        card.dataset.idx = window._absItems ? window._absItems.indexOf(item) : 0;
        card.addEventListener("click", function(){ var idx=this.dataset.idx; openBook(window._absItems ? window._absItems[idx] : item); });
        card.innerHTML = `
          <div class="home-book-cover">
            <img src="/api/abs/cover/${item.id}" onerror="this.parentElement.textContent='📚'" loading="lazy">
          </div>
          <div class="home-book-info">
            <div class="home-book-title" title="${title}">${title}</div>
            <div class="home-book-author">${author}</div>
            <div class="home-book-bar"><div class="home-book-bar-fill" style="width:${pct}%"></div></div>
          </div>`;
        libGrid.appendChild(card);
      });
    }

  } catch(e) {
    recentList.innerHTML = '<div style="color:var(--txt3);font-size:13px;padding:8px 0">Erreur: ' + e.message + '</div>';
    libGrid.innerHTML    = '';
  }
}

function goHome() {
  showScreen('home');
}

// ══════════════════════════════════════════════════════
// LIVRE AUDIO
// ══════════════════════════════════════════════════════
async function loadABS() {
  const el       = document.getElementById('abs-content');
  const progRow  = document.getElementById('abs-progress-row');
  const libLabel = document.getElementById('abs-lib-label');

  el.innerHTML      = '<div class="empty"><div class="spinner"></div><span>Chargement…</span></div>';
  progRow.innerHTML = '<div class="empty"><div class="spinner"></div></div>';

  try {
    const data = await api('GET', '/abs/libraries');
    const libs = data.libraries || [];

    if (!libs.length) {
      el.innerHTML      = '<div class="empty">📚<span>Configurez Audiobookshelf dans Paramètres</span></div>';
      progRow.innerHTML = '';
      return;
    }

    window._absItems = [];  // Stockage global pour les callbacks
    let allBooks   = [];
    let inProgress = [];

    // Récupérer la progression depuis /api/me
    let progressMap = {};
    try {
      const me = await api('GET', '/abs/me');
      (me.mediaProgress || []).forEach(p => {
        progressMap[p.libraryItemId] = p;
      });
    } catch(e) {}

    for (const lib of libs) {
      const items = await api('GET', `/abs/libraries/${lib.id}/items?limit=200`);
      const books = items.results || items.items || [];
      books.forEach(item => {
        // Injecter la progression dans l'item
        if (progressMap[item.id]) {
          item.userMediaProgress = progressMap[item.id];
        }
        allBooks.push(item);
        window._absItems.push(item);
        const prog = item.userMediaProgress;
        if (prog && prog.progress > 0.01 && !prog.isFinished) {
          inProgress.push(item);
        }
      });
    }

    // Trier en cours par dernière mise à jour
    inProgress.sort((a,b) => (b.userMediaProgress?.lastUpdate||0) - (a.userMediaProgress?.lastUpdate||0));

    // ── Livres en cours ──────────────────────────────────────
    progRow.innerHTML = '';
    if (!inProgress.length) {
      progRow.innerHTML = '<div style="color:var(--txt3);font-size:13px;padding:4px 0">Aucun livre en cours</div>';
    } else {
      inProgress.forEach(item => {
        const title  = item.media?.metadata?.title || '—';
        const author = item.media?.metadata?.authorName || '';
        const prog   = item.userMediaProgress?.progress || 0;
        const pct    = Math.round(prog * 100);
        const idx    = window._absItems.indexOf(item);
        const card   = document.createElement('div');
        card.className = 'abs-prog-card';
        card.dataset.idx = idx;
        card.addEventListener('click', function() { openBook(window._absItems[this.dataset.idx]); });
        card.innerHTML = `
          <div class="abs-prog-cover">
            <img src="/api/abs/cover/${item.id}" onerror="this.parentElement.textContent='📚'" loading="lazy">
            <div class="abs-prog-pct">${pct}%</div>
          </div>
          <div class="abs-prog-info">
            <div class="abs-prog-title" title="${title.replace(/"/g,"&quot;")}">${title}</div>
            <div class="abs-prog-author">${author}</div>
            <div class="abs-prog-bar"><div class="abs-prog-bar-fill" style="width:${pct}%"></div></div>
          </div>`;
        progRow.appendChild(card);
      });
    }

    // ── Bibliothèque ──────────────────────────────────────────
    if (libs.length === 1) {
      libLabel.textContent = '📚 ' + libs[0].name;
    } else {
      libLabel.textContent = '📚 Bibliothèque';
    }

    el.innerHTML = '';
    if (!allBooks.length) {
      el.innerHTML = '<div class="empty">📚<span>Aucun livre</span></div>';
      return;
    }

    const grid = document.createElement('div');
    grid.className = 'books-grid';
    allBooks.forEach(item => {
      const title  = item.media?.metadata?.title || '—';
      const author = item.media?.metadata?.authorName || '';
      const prog   = item.userMediaProgress?.progress || 0;
      const pct    = Math.round(prog * 100);
      const card   = document.createElement('div');
      card.className = 'book-card';
      card.dataset.idx = window._absItems ? window._absItems.indexOf(item) : 0;
      card.addEventListener("click", function(){ var idx=this.dataset.idx; openBook(window._absItems ? window._absItems[idx] : item); });
      card.innerHTML = `
        <div class="book-cover">
          <img src="/api/abs/cover/${item.id}" onerror="this.parentElement.textContent='📚'" loading="lazy">
        </div>
        <div class="book-info">
          <div class="book-title" title="${title}">${title}</div>
          <div class="book-author">${author}</div>
          <div class="book-progress"><div class="book-progress-fill" style="width:${pct}%"></div></div>
        </div>`;
      grid.appendChild(card);
    });
    el.appendChild(grid);

  } catch(e) {
    el.innerHTML      = `<div class="empty">⚠️<span>${e.message}</span></div>`;
    progRow.innerHTML = '';
  }
}

async function stopBook() {
  try {
    _bookLoading = false;  // Réinitialiser le verrou
    await api('POST', '/player/stop');
    isPlaying = false;
    document.getElementById('btn-playpause').textContent = '▶';
    const btnRead = document.getElementById('btn-read');
    if (btnRead) { btnRead.disabled = false; btnRead.textContent = '▶ Lire'; }
    document.getElementById('pb-title').textContent = 'Aucune lecture';
    document.getElementById('pb-author').textContent = '';
    toast('⏹ Arrêté');
  } catch(e) { 
    _bookLoading = false;
    toast('Erreur: ' + e.message); 
  }
}

let _bookLoading = false;

async function startBook() {
  if (!currentItem) return;
  if (_bookLoading) return;  // Verrou anti double-clic
  _bookLoading = true;

  // Désactiver le bouton pour éviter les doubles clics
  const btn = document.getElementById('btn-read');
  if (btn) { btn.disabled = true; btn.textContent = '⏳ Chargement…'; }
  toast('Chargement…');
  try {
    // 1. Arrêter la sync ET la lecture en cours
    await api('POST', '/player/stop').catch(() => {});

    // 2. Attendre 2s que la sync soit bien arrêtée et qu'ABS soit à jour
    await new Promise(r => setTimeout(r, 2000));

    // 3. Lire la position depuis ABS — maintenant sans interférence
    let startTime = 0;
    try {
      const pos = await api('GET', `/abs/position/${currentItem.id}`);
      startTime = pos.position || 0;
      console.log('Position ABS après arrêt sync:', startTime);
    } catch(e) {
      console.warn('Erreur position ABS:', e.message);
      startTime = currentItem.userMediaProgress?.currentTime || 0;
    }

    // 4. Récupérer l'URL de stream
    const stream = await api('GET', `/abs/stream/${currentItem.id}`);

    // item_id vient du stream (retourné par le backend) OU de currentItem
    const itemId = String(stream.item_id || currentItem.id || currentItem.ino || '');
    console.log('startBook item_id:', itemId, 'currentItem.id:', currentItem.id, 'stream.item_id:', stream.item_id);
    await api('POST', '/player/play', {
      source:     'abs',
      uri:        stream.url,
      http_token: stream.token,
      item_id:    itemId,
      duration:   Number(stream.duration || currentItem.media?.duration || 0),
      title:      String(stream.title || currentItem.media?.metadata?.title || ''),
      author:     String(currentItem.media?.metadata?.authorName || ''),
      start_time: Number(startTime),
      output:     getOutput()
    });
    if (btn) { btn.disabled = false; btn.textContent = '⏸ Pause'; }
    isPlaying = true;
    _bookLoading = false;
    toast('▶ Lecture lancée');
  } catch(e) {
    if (btn) { btn.disabled = false; btn.textContent = '▶ Lire'; }
    _bookLoading = false;
    toast('Erreur: ' + e.message);
  }
}

async function openBook(item) {
  currentItem = item;
  showScreen('player');

  const title  = item.media?.metadata?.title || '—';
  const author = item.media?.metadata?.authorName || '';
  const series = item.media?.metadata?.series || '';
  const desc   = item.media?.metadata?.description || '';
  const dur    = item.media?.duration || 0;
  const prog   = item.userMediaProgress?.currentTime || 0;
  const pct    = dur > 0 ? Math.round(prog/dur*100) : 0;

  document.getElementById('pd-title').textContent  = title;
  document.getElementById('pd-author').textContent = author;
  // pd-series supprimé
  document.getElementById('pd-desc').textContent   = desc;
  document.getElementById('pd-time-dur').textContent = fmtTime(dur);
  document.getElementById('pd-time-cur').textContent = fmtTime(prog);
  document.getElementById('pd-pct').textContent = pct + '%';
  if(document.getElementById('pd-prog')) document.getElementById('pd-prog').style.width = pct + '%';

  // Pochette
  const covEl = document.getElementById('pd-cover');
  covEl.innerHTML = `<img src="/api/abs/cover/${item.id}" onerror="this.parentElement.textContent='📚'" style="width:100%;height:100%;object-fit:cover">`;

// badges supprimés

  // Mettre à jour la player bar
  updatePB(title, author, `/api/abs/cover/${item.id}`);
}

// Proxy cover ABS
// Le router ABS doit exposer /api/abs/cover/{id}

// ══════════════════════════════════════════════════════
// NAS
// ══════════════════════════════════════════════════════
let nasCrumbs = [];

async function browseNAS(path) {
  const content = document.getElementById('nas-content');
  content.innerHTML = '<div class="empty"><div class="spinner"></div></div>';

  try {
    const data = await api('GET', `/nas/browse?path=${encodeURIComponent(path)}`);

    // Breadcrumb
    if (path === '/opt/jv/nas') {
      nasCrumbs = [{label:'NAS', path}];
    } else if (!nasCrumbs.find(c => c.path === path)) {
      const parts = path.split('/');
      nasCrumbs.push({label: parts[parts.length-1], path});
    }
    renderBreadcrumb();

    if (!data.items?.length) {
      content.innerHTML = '<div class="empty">📂<span>Dossier vide</span></div>';
      return;
    }

    content.innerHTML = '';
    content.className = 'nas-grid';
    const AUDIO_EXT = ['.mp3','.flac','.ogg','.m4a','.aac','.wav','.opus','.m4b'];

    data.items.forEach(item => {
      const isAudio = !item.is_dir && AUDIO_EXT.includes(item.ext);
      const div = document.createElement('div');
      div.className = 'nas-item';
      div.innerHTML = `
        <span class="nas-icon">${item.is_dir ? '📁' : isAudio ? '🎵' : '📄'}</span>
        <span class="nas-name" title="${item.name}">${item.name}</span>`;

      if (item.is_dir) {
        div.onclick = () => browseNAS(item.path);
      } else if (isAudio) {
        div.onclick = () => playNAS(item.path, item.name);
      }
      content.appendChild(div);
    });
  } catch(e) {
    content.innerHTML = `<div class="empty">⚠️<span>${e.message}</span></div>`;
  }
}

function renderBreadcrumb() {
  const bc = document.getElementById('nas-breadcrumb');
  bc.innerHTML = nasCrumbs.map((c,i) =>
    i < nasCrumbs.length-1
      ? `<span onclick="nasCrumbs=nasCrumbs.slice(0,${i+1});browseNAS('${c.path}')">${c.label}</span><span class="sep">›</span>`
      : `<span>${c.label}</span>`
  ).join('');
}

async function playNAS(path, name) {
  try {
    await api('POST', '/player/play', {source:'nas', uri:path, title:name, output:getOutput()});
    updatePB(name, 'NAS', '🎵');
    toast(`▶ ${name}`);
  } catch(e) { toast('Erreur: ' + e.message); }
}

// ══════════════════════════════════════════════════════
// YOUTUBE
// ══════════════════════════════════════════════════════
async function searchYT() {
  const q = document.getElementById('yt-input').value.trim();
  if (!q) return;
  const el = document.getElementById('yt-results');
  el.innerHTML = '<div class="empty"><div class="spinner"></div><span>Recherche…</span></div>';
  try {
    const results = await api('GET', `/youtube/search?q=${encodeURIComponent(q)}&max_results=10`);
    if (!results.length) {
      el.innerHTML = '<div class="empty">🔍<span>Aucun résultat</span></div>';
      return;
    }
    el.innerHTML = '';
    results.forEach(r => {
      const d = document.createElement('div');
      d.className = 'yt-card';
      d.onclick = () => playYT(r.url, r.title);
      d.innerHTML = `
        <div class="yt-thumb">
          ${r.thumbnail ? `<img src="${r.thumbnail}" onerror="this.parentElement.textContent='▶'">` : '▶'}
        </div>
        <div class="yt-info">
          <div class="yt-title">${r.title}</div>
          <div class="yt-dur">${r.duration ? fmtTime(r.duration) : ''}</div>
        </div>`;
      el.appendChild(d);
    });
  } catch(e) {
    el.innerHTML = `<div class="empty">⚠️<span>${e.message}</span></div>`;
  }
}

async function playYT(url, title) {
  toast('Résolution du stream…');
  try {
    const stream = await api('POST', '/youtube/resolve', {url, audio_only:true});
    await api('POST', '/player/play', {source:'youtube', uri:stream.url, title, output:getOutput()});
    updatePB(title, 'YouTube', '▶️');
    toast(`▶ ${title}`);
  } catch(e) { toast('Erreur: ' + e.message); }
}

// ══════════════════════════════════════════════════════
// WEB RADIO
// ══════════════════════════════════════════════════════
let currentRadio = '';

function parseOPML(xml) {
  const parser = new DOMParser();
  const doc    = parser.parseFromString(xml, 'text/xml');
  const outlines = doc.querySelectorAll('outline[url], outline[xmlUrl]');
  const stations = [];
  outlines.forEach(o => {
    const url  = o.getAttribute('url') || o.getAttribute('xmlUrl');
    const name = o.getAttribute('text') || o.getAttribute('title') || url;
    if (url && (url.startsWith('http://') || url.startsWith('https://'))) {
      stations.push({name, url});
    }
  });
  return stations;
}

async function importOPML() {
  const input = document.getElementById('opml-url').value.trim();
  if (!input) { toast('Entrez une URL OPML'); return; }
  try {
    let xml = input;
    if (input.startsWith('http')) {
      const r = await fetch(input);
      xml = await r.text();
    }
    const stations = parseOPML(xml);
    if (!stations.length) { toast('Aucune station trouvée dans le fichier'); return; }
    const curr = await api('GET', '/settings/radios').catch(() => []);
    const merged = [...curr];
    stations.forEach(s => {
      if (!merged.find(m => m.url === s.url)) merged.push(s);
    });
    await api('POST', '/settings/radios', merged);
    document.getElementById('opml-url').value = '';
    loadRadios();
    toast(`✓ ${stations.length} stations importées`);
  } catch(e) { toast('Erreur: ' + e.message); }
}

async function importOPMLFile(input) {
  const file = input.files[0];
  if (!file) return;
  const xml = await file.text();
  const stations = parseOPML(xml);
  if (!stations.length) { toast('Aucune station trouvée'); return; }
  const curr = await api('GET', '/settings/radios').catch(() => []);
  const merged = [...curr];
  stations.forEach(s => {
    if (!merged.find(m => m.url === s.url)) merged.push(s);
  });
  await api('POST', '/settings/radios', merged);
  loadRadios();
  toast(`✓ ${stations.length} stations importées`);
}

// ══════════════════════════════════════════════════════
// MODULE HORLOGE / MÉTÉO
// ══════════════════════════════════════════════════════
const WMO_ICONS = {
  0:'☀️', 1:'🌤️', 2:'⛅', 3:'☁️',
  45:'🌫️', 48:'🌫️',
  51:'🌦️', 53:'🌦️', 55:'🌧️',
  61:'🌧️', 63:'🌧️', 65:'🌧️',
  71:'❄️', 73:'❄️', 75:'❄️',
  77:'🌨️', 80:'🌦️', 81:'🌧️', 82:'⛈️',
  85:'❄️', 86:'❄️',
  95:'⛈️', 96:'⛈️', 99:'⛈️'
};

const WMO_DESC = {
  0:'Ciel dégagé', 1:'Peu nuageux', 2:'Partiellement nuageux', 3:'Couvert',
  45:'Brouillard', 48:'Brouillard givrant',
  51:'Bruine légère', 53:'Bruine', 55:'Bruine dense',
  61:'Pluie légère', 63:'Pluie', 65:'Pluie forte',
  71:'Neige légère', 73:'Neige', 75:'Neige forte',
  77:'Grésil', 80:'Averses légères', 81:'Averses', 82:'Averses fortes',
  85:'Averses de neige', 86:'Averses de neige fortes',
  95:'Orage', 96:'Orage avec grêle', 99:'Orage violent'
};

function initClockWeather() {
  updateClock();
  setInterval(updateClock, 1000);
  loadWeather();
  setInterval(loadWeather, 15 * 60 * 1000); // Toutes les 15min
}

function updateClock() {
  const now  = new Date();
  const h    = now.getHours().toString().padStart(2,'0');
  const m    = now.getMinutes().toString().padStart(2,'0');
  const days = ['Dimanche','Lundi','Mardi','Mercredi','Jeudi','Vendredi','Samedi'];
  const months = ['janvier','février','mars','avril','mai','juin',
                  'juillet','août','septembre','octobre','novembre','décembre'];
  document.getElementById('cw-time').textContent = `${h}:${m}`;
  document.getElementById('cw-date').textContent =
    `${days[now.getDay()]} ${now.getDate()} ${months[now.getMonth()]} ${now.getFullYear()}`;
}

async function loadWeather() {
  // Récupérer position depuis les paramètres ou utiliser Luxembourg par défaut
  const lat = localStorage.getItem('weather_lat') || '49.6116';
  const lon = localStorage.getItem('weather_lon') || '6.1319';

  try {
    const r = await fetch(
      `https://api.open-meteo.com/v1/forecast?latitude=${lat}&longitude=${lon}` +
      `&current=temperature_2m,relative_humidity_2m,apparent_temperature,` +
      `weather_code,wind_speed_10m&wind_speed_unit=kmh&timezone=auto`
    );
    const d = await r.json();
    const c = d.current;
    const code = c.weather_code;

    document.getElementById('cw-icon').textContent    = WMO_ICONS[code] || '🌤️';
    document.getElementById('cw-temp').textContent    = `${Math.round(c.temperature_2m)}°`;
    document.getElementById('cw-desc').textContent    = WMO_DESC[code] || '—';
    document.getElementById('cw-humidity').textContent = `${c.relative_humidity_2m}%`;
    document.getElementById('cw-wind').textContent    = `${Math.round(c.wind_speed_10m)} km/h`;
    document.getElementById('cw-feels').textContent   = `Ressenti ${Math.round(c.apparent_temperature)}°`;
  } catch(e) {
    document.getElementById('cw-desc').textContent = 'Météo indisponible';
  }
}

// ══════════════════════════════════════════════════════
// TUNER RADIO BROWSER
// ══════════════════════════════════════════════════════
const RB_API = 'https://de1.api.radio-browser.info/json';

function showRadioTab(tab) {
  ['mes-radios','tuner','ajouter'].forEach(t => {
    document.getElementById('radio-tab-' + t).style.display = t === tab ? 'block' : 'none';
    const btn = document.getElementById('tab-' + t);
    if (btn) {
      btn.className = t === tab ? 'btn btn-primary btn-sm' : 'btn btn-ghost btn-sm';
    }
  });
  if (tab === 'mes-radios') loadRadios();
  if (tab === 'tuner' && !document.getElementById('tuner-results').children.length) {
    tunerSearch();
  }
}

async function tunerSearch() {
  const q       = document.getElementById('tuner-search').value.trim();
  const country = document.getElementById('tuner-country').value;
  const genre   = document.getElementById('tuner-genre').value;
  const results = document.getElementById('tuner-results');
  results.innerHTML = '<div class="empty"><div class="spinner"></div><span>Recherche…</span></div>';

  try {
    let url = '';
    if (q) {
      url = `${RB_API}/stations/search?name=${encodeURIComponent(q)}&limit=30&order=clickcount&reverse=true&hidebroken=true`;
    } else {
      url = `${RB_API}/stations/search?limit=40&order=clickcount&reverse=true&hidebroken=true`;
    }
    if (country) url += `&countrycode=${country}`;
    if (genre)   url += `&tag=${encodeURIComponent(genre)}`;

    const r = await fetch(url);
    const stations = await r.json();

    if (!stations.length) {
      results.innerHTML = '<div class="empty">📻<span>Aucune station trouvée</span></div>';
      return;
    }

    results.innerHTML = '';
    stations.forEach(s => {
      if (!s.url_resolved && !s.url) return;
      const streamUrl = s.url_resolved || s.url;
      const div = document.createElement('div');
      div.className = 'tuner-card';
      div.innerHTML = `
        <div class="tuner-favicon">
          ${s.favicon ? `<img src="${s.favicon}" onerror="this.parentElement.textContent='📻'">` : '📻'}
        </div>
        <div class="tuner-info">
          <div class="tuner-name">${s.name}</div>
          <div class="tuner-meta">
            ${s.country || ''} ${s.tags ? '· ' + s.tags.split(',').slice(0,3).join(', ') : ''}
            ${s.bitrate ? '· ' + s.bitrate + 'kbps' : ''}
          </div>
        </div>
        <div class="tuner-actions">
          <button class="btn btn-ghost btn-sm" onclick="tunerPlay('${streamUrl}','${s.name.replace(/'/g,"\'")}')">▶</button>
          <button class="btn btn-primary btn-sm" onclick="tunerSave('${streamUrl}','${s.name.replace(/'/g,"\'")}','${(s.favicon||'').replace(/'/g,"\'")}')">⭐</button>
        </div>`;
      results.appendChild(div);
    });
  } catch(e) {
    results.innerHTML = `<div class="empty">⚠️<span>Erreur: ${e.message}</span></div>`;
  }
}

async function tunerPlay(url, name) {
  await api('POST', '/player/play', {source:'radio', uri:url, title:name, output:getOutput()});
  updatePB(name, 'Radio', '📻');
  toast(`▶ ${name}`);
}

async function tunerSave(url, name, favicon) {
  const curr = await api('GET', '/settings/radios').catch(() => []);
  if (curr.find(s => s.url === url)) { toast('Déjà dans vos stations'); return; }
  await api('POST', '/settings/radios', [...curr, {name, url, favicon: favicon || ''}]);
  toast(`⭐ ${name} sauvegardé`);
}

// ══════════════════════════════════════════════════════
// PODCASTS
// ══════════════════════════════════════════════════════
async function loadPodcasts() {
  const grid = document.getElementById('podcasts-grid');
  const podcasts = JSON.parse(localStorage.getItem('audiobox_podcasts') || '[]');
  if (!podcasts.length) {
    grid.innerHTML = '<div class="empty" style="grid-column:1/-1">🎙️<span>Aucun podcast — ajoutez un flux RSS</span></div>';
    return;
  }
  grid.innerHTML = '';
  podcasts.forEach((p, i) => {
    const card = document.createElement('div');
    card.className = 'radio-card';
    card.onclick = () => showPodcastEpisodes(p, i);
    card.innerHTML = `
      <div class="radio-icon">🎙️</div>
      <div class="radio-name">${p.title || p.url}</div>
      <button class="radio-del" onclick="event.stopPropagation();removePodcast(${i})">✕</button>`;
    grid.appendChild(card);
  });
}

async function addPodcast() {
  const url = document.getElementById('podcast-rss').value.trim();
  if (!url) { toast('Entrez une URL RSS'); return; }
  toast('Chargement du flux…');
  try {
    const feed = await fetchRSS(url);
    const podcasts = JSON.parse(localStorage.getItem('audiobox_podcasts') || '[]');
    podcasts.push({url, title: feed.title, episodes: feed.episodes});
    localStorage.setItem('audiobox_podcasts', JSON.stringify(podcasts));
    document.getElementById('podcast-rss').value = '';
    loadPodcasts();
    toast(`✓ ${feed.title} ajouté`);
  } catch(e) { toast('Erreur: ' + e.message); }
}

async function fetchRSS(url) {
  // Utiliser un proxy CORS pour les flux RSS externes
  const proxyUrl = `https://api.allorigins.win/get?url=${encodeURIComponent(url)}`;
  const r = await fetch(proxyUrl);
  const data = await r.json();
  const xml = data.contents;
  const parser = new DOMParser();
  const doc = parser.parseFromString(xml, 'text/xml');
  const title = doc.querySelector('channel > title')?.textContent || url;
  const items = doc.querySelectorAll('item');
  const episodes = [];
  items.forEach(item => {
    const enclosure = item.querySelector('enclosure');
    const audioUrl  = enclosure?.getAttribute('url') || '';
    const epTitle   = item.querySelector('title')?.textContent || '—';
    const duration  = item.querySelector('duration')?.textContent || '';
    const pubDate   = item.querySelector('pubDate')?.textContent || '';
    if (audioUrl) {
      episodes.push({title: epTitle, url: audioUrl, duration, pubDate});
    }
  });
  return {title, episodes};
}

function showPodcastEpisodes(podcast, idx) {
  document.getElementById('podcast-list-view').style.display = 'none';
  document.getElementById('podcast-episodes-view').style.display = 'block';
  document.getElementById('podcast-ep-title').textContent = podcast.title || podcast.url;
  const list = document.getElementById('episodes-list');
  list.innerHTML = '';
  (podcast.episodes || []).forEach(ep => {
    const div = document.createElement('div');
    div.className = 'yt-card';
    div.onclick = () => playPodcastEpisode(ep);
    div.innerHTML = `
      <div class="yt-thumb">🎙️</div>
      <div class="yt-info">
        <div class="yt-title">${ep.title}</div>
        <div class="yt-dur">${ep.pubDate ? new Date(ep.pubDate).toLocaleDateString('fr-FR') : ''} ${ep.duration || ''}</div>
      </div>`;
    list.appendChild(div);
  });
}

function showPodcastList() {
  document.getElementById('podcast-list-view').style.display = 'block';
  document.getElementById('podcast-episodes-view').style.display = 'none';
}

async function playPodcastEpisode(ep) {
  try {
    await api('POST', '/player/play', {
      source: 'radio', uri: ep.url, title: ep.title, output: getOutput()
    });
    updatePB(ep.title, 'Podcast', '🎙️');
    toast(`▶ ${ep.title}`);
  } catch(e) { toast('Erreur: ' + e.message); }
}

function removePodcast(idx) {
  const podcasts = JSON.parse(localStorage.getItem('audiobox_podcasts') || '[]');
  podcasts.splice(idx, 1);
  localStorage.setItem('audiobox_podcasts', JSON.stringify(podcasts));
  loadPodcasts();
  toast('Podcast supprimé');
}

async function fetchRadioFavicon(name, url) {
  // 1. Chercher sur Radio Browser par nom exact
  try {
    const r = await fetch(`https://de1.api.radio-browser.info/json/stations/search?name=${encodeURIComponent(name)}&limit=3&hidebroken=true&order=clickcount&reverse=true`);
    const results = await r.json();
    for (const station of results) {
      if (station.favicon && station.favicon.startsWith('http')) {
        const img = new Image();
        const valid = await new Promise(res => {
          img.onload  = () => res(true);
          img.onerror = () => res(false);
          setTimeout(() => res(false), 3000);
          img.src = station.favicon;
        });
        if (valid) return station.favicon;
      }
    }
  } catch(e) {}

  // 2. Fallback : Google favicon depuis le nom de la radio
  try {
    // Chercher le site web de la radio via Radio Browser
    const r2 = await fetch(`https://de1.api.radio-browser.info/json/stations/search?name=${encodeURIComponent(name)}&limit=1`);
    const res2 = await r2.json();
    if (res2.length && res2[0].homepage) {
      const domain = new URL(res2[0].homepage).hostname;
      return `https://www.google.com/s2/favicons?domain=${domain}&sz=64`;
    }
  } catch(e) {}

  return '';
}

async function loadRadios() {
  const grid = document.getElementById('radios-grid');
  try {
    const stations = await api('GET', '/settings/radios');
    if (!stations.length) {
      grid.innerHTML = '<div class="empty" style="grid-column:1/-1">📻<span>Aucune station — ajoutez-en ci-dessous</span></div>';
      return;
    }
    // Trier : favoris en premier
    const favorites = JSON.parse(localStorage.getItem('radio_favorites') || '[]');
    stations.sort((a, b) => {
      const af = favorites.includes(a.url) ? 0 : 1;
      const bf = favorites.includes(b.url) ? 0 : 1;
      return af - bf;
    });

    // Cache local des logos
    const logoCache = JSON.parse(localStorage.getItem('radio_logos') || '{}');

    grid.innerHTML = '';
    stations.forEach((s, i) => {
      const isFav = favorites.includes(s.url);
      const card = document.createElement('div');
      card.className = 'radio-card' + (currentRadio === s.url ? ' playing' : '') + (isFav ? ' favorite' : '');
      card.onclick = () => playRadio(s.url, s.name);
      card.id = `radio-card-${i}`;

      // Logo : depuis la station, depuis le cache, ou emoji
      const favicon = s.favicon || logoCache[s.name] || '';
      const logoHtml = favicon
        ? `<img src="${favicon}" onerror="this.outerHTML='📻'" style="width:52px;height:52px;border-radius:8px;object-fit:cover">`
        : `<span id="radio-logo-${i}">📻</span>`;

      card.innerHTML = `
        <button class="radio-fav" onclick="event.stopPropagation();toggleFavoriteRadio('${s.url}')" title="${isFav ? 'Retirer des favoris' : 'Ajouter aux favoris'}">${isFav ? '⭐' : '☆'}</button>
        <div class="radio-icon">${logoHtml}</div>
        <div class="radio-name">${s.name}</div>
        <button class="radio-del" onclick="event.stopPropagation();removeRadio(${i})">✕</button>`;
      grid.appendChild(card);

      // Charger le logo en arrière-plan si manquant
      if (!favicon) {
        fetchRadioFavicon(s.name, s.url).then(url => {
          if (url) {
            logoCache[s.name] = url;
            localStorage.setItem('radio_logos', JSON.stringify(logoCache));
            const span = document.getElementById(`radio-logo-${i}`);
            if (span) span.outerHTML = `<img src="${url}" onerror="this.outerHTML='📻'" style="width:52px;height:52px;border-radius:8px;object-fit:cover">`;
          }
        });
      }
    });
  } catch(e) {
    grid.innerHTML = `<div class="empty" style="grid-column:1/-1">⚠️<span>${e.message}</span></div>`;
  }
}

async function playRadio(url, name) {
  try {
    await api('POST', '/player/play', {source:'radio', uri:url, title:name, output:getOutput()});
    currentRadio = url;
    updatePB(name, 'Radio en direct', '📻');
    toast(`▶ ${name}`);
    loadRadios();
  } catch(e) { toast('Erreur: ' + e.message); }
}

async function addRadio() {
  const name = document.getElementById('r-name').value.trim();
  const url  = document.getElementById('r-url').value.trim();
  if (!name || !url) { toast('Remplissez le nom et l\'URL'); return; }
  try {
    const curr = await api('GET', '/settings/radios').catch(() => []);
    await api('POST', '/settings/radios', [...curr, {name, url}]);
    document.getElementById('r-name').value = '';
    document.getElementById('r-url').value  = '';
    loadRadios();
    toast('✓ Station ajoutée');
  } catch(e) { toast('Erreur: ' + e.message); }
}

function toggleFavoriteRadio(url) {
  const favorites = JSON.parse(localStorage.getItem('radio_favorites') || '[]');
  const idx = favorites.indexOf(url);
  if (idx >= 0) {
    favorites.splice(idx, 1);
    toast('Retiré des favoris');
  } else {
    favorites.push(url);
    toast('⭐ Ajouté aux favoris');
  }
  localStorage.setItem('radio_favorites', JSON.stringify(favorites));
  loadRadios();
}

async function removeRadio(idx) {
  const curr = await api('GET', '/settings/radios').catch(() => []);
  curr.splice(idx, 1);
  await api('POST', '/settings/radios', curr);
  loadRadios();
}

// ══════════════════════════════════════════════════════
// PLAYER
// ══════════════════════════════════════════════════════
function updatePB(title, author, coverSrc) {
  document.getElementById('pb-title').textContent  = title;
  document.getElementById('pb-author').textContent = author;
  document.getElementById('btn-playpause').textContent = '⏸';
  isPlaying = true;

  const cov = document.getElementById('pb-cover');
  if (typeof coverSrc === 'string' && coverSrc.startsWith('/')) {
    cov.innerHTML = `<img src="${coverSrc}" onerror="this.parentElement.textContent='🎵'" style="width:100%;height:100%;object-fit:cover;border-radius:8px">`;
  } else {
    cov.textContent = coverSrc || '🎵';
  }
}

async function togglePlay() {
  try {
    if (isPlaying) {
      // En lecture → pause
      await api('POST', '/player/pause');
      isPlaying = false;
      document.getElementById('btn-playpause').textContent = '▶';
      const btn = document.getElementById('btn-read');
      if (btn) btn.textContent = '▶ Lire';
    } else if (currentItem) {
      // En pause ou arrêté → toujours relancer depuis ABS
      await startBook();
    } else {
      toast('Sélectionnez un livre ou une radio');
    }
  } catch(e) { toast('Erreur: ' + e.message); }
}

async function seekRel(delta) {
  const pos = Math.max(0, pState.position + delta);
  await api('POST', '/player/seek', {position: pos}).catch(() => {});
}

function seekToClick(e) {
  const rect = e.currentTarget.getBoundingClientRect();
  const pos  = (e.clientX - rect.left) / rect.width * (pState.duration || 0);
  api('POST', '/player/seek', {position: Math.max(0,pos)}).catch(() => {});
}

function seekToClickBar(e) { seekToClick(e); }

async function setVolume(v) {
  await api('POST', `/player/volume/${v}`).catch(() => {});
}

function getOutput() {
  return document.getElementById('cfg-output')?.value
      || localStorage.getItem('ab_output')
      || 'jack';
}

// WebSocket état player
function connectWS() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(`${proto}://${location.host}/api/player/ws`);
  ws.onmessage = e => {
    pState = JSON.parse(e.data);
    document.getElementById('time-cur').textContent = fmtTime(pState.position);
    document.getElementById('time-dur').textContent = fmtTime(pState.duration);
    const pct = pState.duration > 0 ? (pState.position / pState.duration * 100).toFixed(1) : 0;
    document.getElementById('pb-prog').style.width = pct + '%';

    // Sync écran lecture
    if (document.getElementById('screen-player').classList.contains('active')) {
      document.getElementById('pd-time-cur').textContent = fmtTime(pState.position);
      if(document.getElementById('pd-prog')) document.getElementById('pd-prog').style.width = pct + '%';
      document.getElementById('pd-pct').textContent = Math.round(pct) + '%';
    }

    if (!pState.playing && !pState.paused && isPlaying) {
      isPlaying = false;
      document.getElementById('btn-playpause').textContent = '▶';
    }
  };
  ws.onclose = () => setTimeout(connectWS, 3000);
}

// ══════════════════════════════════════════════════════
// PARAMÈTRES
// ══════════════════════════════════════════════════════
// ══════════════════════════════════════════════════════
// HOME ASSISTANT + WEBHOOKS
// ══════════════════════════════════════════════════════
function generateHAConfig() {
  const ip = location.hostname;
  const port = location.port || 8000;
  const base = `http://${ip}:${port}/api/public`;
  return `# AudioBox — Home Assistant integration
# Ajoutez dans configuration.yaml

rest_command:
  audiobox_play:
    url: "${base}/play"
    method: POST
  audiobox_pause:
    url: "${base}/pause"
    method: POST
  audiobox_stop:
    url: "${base}/stop"
    method: POST
  audiobox_volume:
    url: "${base}/volume/{{ level }}"
    method: POST
  audiobox_radio:
    url: "${base}/radio/{{ name }}"
    method: POST

sensor:
  - platform: rest
    name: audiobox_state
    resource: "${base}/state"
    value_template: "{{ value_json.playing }}"
    json_attributes:
      - position
      - duration
      - volume
      - paused

# Automatisation exemple — lance France Inter quand tu rentres :
# automation:
#   - alias: "Accueil → Lance la radio"
#     trigger:
#       platform: state
#       entity_id: person.toi
#       to: home
#     action:
#       service: rest_command.audiobox_radio
#       data:
#         name: "France Inter"`;
}

function loadHAConfig() {
  const el = document.getElementById('ha-config');
  if (el) el.textContent = generateHAConfig();
}

function copyHAConfig() {
  navigator.clipboard.writeText(generateHAConfig())
    .then(() => toast('✓ Config HA copiée'))
    .catch(() => toast('Erreur copie'));
}

async function loadWebhooks() {
  try {
    const whs = await api('GET', '/settings/webhooks');
    const el  = document.getElementById('webhooks-list');
    if (!whs.length) { el.innerHTML = '<div style="color:var(--txt3);font-size:13px">Aucun webhook configuré</div>'; return; }
    el.innerHTML = whs.map((w, i) => `
      <div style="display:flex;align-items:center;gap:8px;padding:8px;background:var(--bg2);border-radius:var(--rsm);margin-bottom:6px">
        <div style="flex:1;min-width:0">
          <div style="font-size:13px;font-weight:600">${w.name || 'Webhook'}</div>
          <div style="font-size:11px;color:var(--txt3);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${w.url}</div>
          <div style="font-size:11px;color:var(--txt2)">${(w.events||[]).join(', ')}</div>
        </div>
        <button class="btn btn-danger btn-sm" onclick="removeWebhook(${i})">✕</button>
      </div>`).join('');
  } catch(e) {}
}

async function addWebhook() {
  const url  = document.getElementById('wh-url').value.trim();
  const name = document.getElementById('wh-name').value.trim();
  if (!url) { toast('Entrez une URL'); return; }
  const events = [];
  if (document.getElementById('wh-ev-play').checked)     events.push('play');
  if (document.getElementById('wh-ev-pause').checked)    events.push('pause');
  if (document.getElementById('wh-ev-stop').checked)     events.push('stop');
  if (document.getElementById('wh-ev-finished').checked) events.push('finished');
  try {
    const curr = await api('GET', '/settings/webhooks').catch(() => []);
    curr.push({url, name, events});
    await api('POST', '/settings/webhooks', curr.map(w => ({url:w.url, name:w.name||'', events:w.events||[]})));
    document.getElementById('wh-url').value  = '';
    document.getElementById('wh-name').value = '';
    loadWebhooks();
    toast('✓ Webhook ajouté');
  } catch(e) { toast('Erreur: ' + e.message); }
}

async function removeWebhook(idx) {
  const curr = await api('GET', '/settings/webhooks').catch(() => []);
  curr.splice(idx, 1);
  await api('POST', '/settings/webhooks', curr.map(w => ({url:w.url, name:w.name||'', events:w.events||[]})));
  loadWebhooks();
}

async function spotifyStatus() {
  try {
    const r = await fetch('/api/spotify/status');
    const d = await r.json();
    document.getElementById('spotify-status').textContent = d.running ? '✅ En cours' : '⭕ Arrêté';
  } catch(e) { document.getElementById('spotify-status').textContent = 'Non installé — lancez setup-spotify.sh'; }
}
async function spotifyStart() {
  await fetch('/api/spotify/start', {method:'POST'}).catch(()=>{});
  setTimeout(spotifyStatus, 2000);
  toast('Spotify Connect démarré');
}
async function spotifyStop() {
  await fetch('/api/spotify/stop', {method:'POST'}).catch(()=>{});
  setTimeout(spotifyStatus, 1000);
  toast('Spotify Connect arrêté');
}

// ══════════════════════════════════════════════════════
// SYSTÈME
// ══════════════════════════════════════════════════════
async function loadSysStatus() {
  const el = document.getElementById('sys-status');
  try {
    const s = await fetch('/api/system/status').then(r => r.json());
    el.innerHTML = `
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px">
        <div>🌡️ <strong>${s.temperature}</strong></div>
        <div>⏱️ ${s.uptime}</div>
        <div>💾 ${s.disk}</div>
        <div>🧠 ${s.memory}</div>
        <div>🎬 yt-dlp ${s.ytdlp}</div>
        <div>⚙️ Backend: <span style="color:${s.services.backend==='active'?'var(--green)':'var(--red)'}">
          ${s.services.backend}</span></div>
      </div>`;
    // Mettre à jour la version yt-dlp
    document.getElementById('ytdlp-info').textContent = `Version actuelle: ${s.ytdlp}`;
  } catch(e) {
    el.textContent = 'Erreur: ' + e.message;
  }
}

async function sysReboot() {
  try {
    await api('POST', '/system/reboot');
    toast('🔄 Redémarrage dans 2s…');
  } catch(e) { toast('Erreur: ' + e.message); }
}

async function sysShutdown() {
  try {
    await api('POST', '/system/shutdown');
    toast('⏹ Arrêt dans 2s…');
  } catch(e) { toast('Erreur: ' + e.message); }
}

async function sysRestartBackend() {
  try {
    await api('POST', '/system/restart-backend');
    toast('↻ Backend redémarre…');
  } catch(e) { toast('Erreur: ' + e.message); }
}

async function updateYtdlp() {
  const btn = event.target;
  btn.disabled = true;
  btn.textContent = '⏳ Mise à jour…';
  try {
    const r = await api('POST', '/system/update-ytdlp');
    toast(`✓ yt-dlp mis à jour: ${r.version}`);
    document.getElementById('ytdlp-info').textContent = `Version: ${r.version}`;
  } catch(e) {
    toast('Erreur: ' + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = '⬆️ Mettre à jour yt-dlp';
  }
}

async function backupConfig() {
  try {
    const r = await fetch('/api/system/backup', {
      headers: token ? {'Authorization': `Bearer ${token}`} : {}
    });
    const blob = await r.blob();
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `audiobox-backup-${new Date().toISOString().slice(0,10)}.json`;
    a.click();
    toast('✓ Backup téléchargé');
  } catch(e) { toast('Erreur: ' + e.message); }
}

async function restoreConfig(input) {
  const file = input.files[0];
  if (!file) return;
  if (!confirm(`Restaurer depuis ${file.name} ? La config actuelle sera remplacée.`)) return;
  try {
    const data = JSON.parse(await file.text());
    await api('POST', '/system/restore', data);
    toast('✓ Configuration restaurée');
  } catch(e) { toast('Erreur: ' + e.message); }
}

async function loadLogs(lines) {
  const el = document.getElementById('sys-logs');
  el.textContent = 'Chargement…';
  try {
    const r = await fetch(`/api/system/logs?lines=${lines}`);
    const d = await r.json();
    el.textContent = d.logs || 'Aucun log';
    el.scrollTop = el.scrollHeight;
  } catch(e) { el.textContent = 'Erreur: ' + e.message; }
}

// ══════════════════════════════════════════════════════
// MODULE ÉGALISEUR
// ══════════════════════════════════════════════════════
const EQ_BANDS = [
  {freq:'60Hz',  key:'b60'},
  {freq:'150Hz', key:'b150'},
  {freq:'400Hz', key:'b400'},
  {freq:'1kHz',  key:'b1k'},
  {freq:'2.5kHz',key:'b2k'},
  {freq:'6kHz',  key:'b6k'},
  {freq:'15kHz', key:'b15k'},
];

const EQ_PRESETS = {
  flat:      [0,  0,  0,  0,  0,  0,  0],
  bass:      [8,  6,  2,  0,  0,  0,  0],
  treble:    [0,  0,  0,  0,  2,  6,  8],
  vocal:     [-2,-1,  3,  5,  4,  2, -1],
  jazz:      [4,  3,  1,  2,  4,  3,  2],
  classical: [5,  3,  0,  0,  0,  3,  4],
  rock:      [5,  3,  0, -1,  0,  3,  5],
};

let _eqValues = JSON.parse(localStorage.getItem('eq_values') || 'null') || EQ_PRESETS.flat.slice();

function initEQ() {
  const container = document.getElementById('eq-bands');
  if (!container) return;
  container.innerHTML = '';
  EQ_BANDS.forEach((band, i) => {
    const div = document.createElement('div');
    div.className = 'eq-band';
    div.innerHTML = `
      <div class="eq-val" id="eq-val-${i}">${_eqValues[i] > 0 ? '+' : ''}${_eqValues[i]}dB</div>
      <input type="range" class="eq-slider" min="-12" max="12" value="${_eqValues[i]}"
             oninput="updateEQBand(${i}, this.value)">
      <label>${band.freq}</label>`;
    container.appendChild(div);
  });
  highlightActivePreset();
}

function updateEQBand(idx, value) {
  _eqValues[idx] = parseInt(value);
  const sign = _eqValues[idx] > 0 ? '+' : '';
  document.getElementById(`eq-val-${idx}`).textContent = `${sign}${_eqValues[idx]}dB`;
  localStorage.setItem('eq_values', JSON.stringify(_eqValues));
  applyEQToMpv();
  highlightActivePreset();
}

function applyEQPreset(name) {
  _eqValues = EQ_PRESETS[name].slice();
  localStorage.setItem('eq_values', JSON.stringify(_eqValues));
  localStorage.setItem('eq_preset', name);
  // Mettre à jour les sliders
  EQ_BANDS.forEach((band, i) => {
    const slider = document.querySelector(`#eq-bands .eq-band:nth-child(${i+1}) input`);
    const val    = document.getElementById(`eq-val-${i}`);
    if (slider) slider.value = _eqValues[i];
    if (val) {
      const sign = _eqValues[i] > 0 ? '+' : '';
      val.textContent = `${sign}${_eqValues[i]}dB`;
    }
  });
  applyEQToMpv();
  highlightActivePreset();
  toast(`🎚️ Préset ${name}`);
}

function highlightActivePreset() {
  const preset = localStorage.getItem('eq_preset') || 'flat';
  document.querySelectorAll('.eq-preset-btn').forEach((btn, i) => {
    const presets = ['flat','bass','treble','vocal','jazz','classical','rock'];
    btn.classList.toggle('active', presets[i] === preset);
  });
}

async function applyEQToMpv() {
  try {
    await api('POST', '/player/equalizer', {bands: _eqValues});
  } catch(e) {}
}

function saveWeatherLocation() {
  const lat = document.getElementById('cfg-weather-lat').value.trim();
  const lon = document.getElementById('cfg-weather-lon').value.trim();
  if (lat) localStorage.setItem('weather_lat', lat);
  if (lon) localStorage.setItem('weather_lon', lon);
  loadWeather();
}

function setCity(name, lat, lon) {
  document.getElementById('cfg-weather-lat').value = lat;
  document.getElementById('cfg-weather-lon').value = lon;
  localStorage.setItem('weather_lat', lat);
  localStorage.setItem('weather_lon', lon);
  loadWeather();
  toast(`📍 ${name} sélectionné`);
}

function saveToken(v) {
  token = v.trim();
  localStorage.setItem('ab_token', token);
}

function initSettings() {
  document.getElementById('cfg-token').value = token;
  document.getElementById('cfg-weather-lat').value = localStorage.getItem('weather_lat') || '49.6116';
  document.getElementById('cfg-weather-lon').value = localStorage.getItem('weather_lon') || '6.1319';
  loadBT();
  loadBTOutputs();
  loadSysStatus();
  initEQ();
  loadHAConfig();
  loadWebhooks();
}

async function saveABS() {
  if (!token) { toast('Entrez d\'abord votre token'); return; }
  try {
    await api('POST', '/settings/abs', {
      url: document.getElementById('cfg-abs-url').value,
      api_key: document.getElementById('cfg-abs-key').value
    });
    toast('✓ Audiobookshelf configuré');
  } catch(e) { toast('Erreur: ' + e.message); }
}

async function mountNAS() {
  if (!token) { toast('Entrez d\'abord votre token'); return; }
  try {
    await api('POST', '/settings/nas/mount', {
      host:        document.getElementById('cfg-nas-host').value,
      share:       document.getElementById('cfg-nas-share').value,
      mount_point: document.getElementById('cfg-nas-mp').value,
      username:    document.getElementById('cfg-nas-user').value,
      password:    document.getElementById('cfg-nas-pass').value,
    });
    toast('✓ NAS monté');
  } catch(e) { toast('Erreur: ' + e.message); }
}

async function loadBT() {
  const el = document.getElementById('bt-list');
  el.innerHTML = '<div class="empty" style="padding:12px 0"><div class="spinner"></div></div>';
  try {
    const devs = await api('GET', '/bluetooth/devices');
    if (!devs.length) { el.innerHTML = '<div class="empty" style="padding:12px 0"><span>Aucun périphérique</span></div>'; return; }
    el.innerHTML = devs.map(d => `
      <div class="bt-device">
        <div class="bt-dot ${d.connected ? 'on' : ''}"></div>
        <div style="flex:1">
          <div style="font-size:13px;font-weight:500">${d.name}</div>
          <div style="font-size:11px;color:var(--txt3)">${d.mac}</div>
        </div>
        ${d.connected
          ? `<button class="btn btn-ghost btn-sm" onclick="btDis('${d.mac}')">Déconnecter</button>`
          : `<button class="btn btn-primary btn-sm" onclick="btCon('${d.mac}')">Connecter</button>`}
      </div>`).join('');
  } catch(e) { el.innerHTML = `<div class="empty" style="padding:12px 0"><span>${e.message}</span></div>`; }
}

async function btScan() {
  document.getElementById('btn-bt-scan').style.display = 'none';
  document.getElementById('btn-bt-stop').style.display = 'inline-flex';
  toast('Scan en cours (20s)…');
  await api('POST', '/bluetooth/scan').catch(() => {});
  document.getElementById('btn-bt-scan').style.display = 'inline-flex';
  document.getElementById('btn-bt-stop').style.display = 'none';
  loadBT();
}

async function btStopScan() {
  await api('POST', '/bluetooth/scan-stop').catch(() => {});
  document.getElementById('btn-bt-scan').style.display = 'inline-flex';
  document.getElementById('btn-bt-stop').style.display = 'none';
  toast('Scan arrêté');
  loadBT();
}

async function btDisableAll() {
  try {
    await api('POST', '/bluetooth/disable');
    toast('Bluetooth désactivé');
    loadBT();
  } catch(e) { toast('Erreur: ' + e.message); }
}

async function btEnableAll() {
  try {
    await api('POST', '/bluetooth/enable');
    toast('Bluetooth activé');
    loadBT();
  } catch(e) { toast('Erreur: ' + e.message); }
}
async function btCon(mac) { toast('Connexion…'); await api('POST',`/bluetooth/connect/${mac}`).catch(e=>toast(e.message)); loadBT(); }
async function btDis(mac) { await api('POST',`/bluetooth/disconnect/${mac}`).catch(()=>{}); loadBT(); }

async function loadBTOutputs() {
  try {
    const devs = await api('GET', '/bluetooth/devices');
    const sel = document.getElementById('cfg-output');
    // Supprimer les options BT existantes
    [...sel.options].filter(o => o.value.startsWith('bluetooth:')).forEach(o => o.remove());
    devs.filter(d => d.connected).forEach(d => {
      const opt = document.createElement('option');
      opt.value = `bluetooth:${d.mac}`;
      opt.textContent = `🔵 ${d.name}`;
      sel.appendChild(opt);
    });
    // Sélectionner auto le BT si connecté
    if (devs.some(d => d.connected)) {
      const btOpt = [...sel.options].find(o => o.value.startsWith('bluetooth:'));
      if (btOpt) sel.value = btOpt.value;
    }
  } catch(e) {}
}

// ══════════════════════════════════════════════════════
// Init
// ══════════════════════════════════════════════════════
connectWS();
loadBTOutputs();
loadRecent();
initScreensaver();
initClockWeather();

// ══════════════════════════════════════════════════════
// ÉCRAN DE VEILLE
// ══════════════════════════════════════════════════════
var _ssTimer  = null;
var _dimTimer = null;
var _ssActive = false;

function initScreensaver() {
  // Réinitialiser les timers à chaque interaction — passive:true pour ne pas bloquer
  const events = ['mousemove','mousedown','touchstart','keydown','click'];
  events.forEach(e => document.addEventListener(e, resetScreensaver, {passive: true}));
  resetScreensaver();
}

function resetScreensaver() {
  if (_ssActive) return;
  clearTimeout(_ssTimer);
  clearTimeout(_dimTimer);
  _ssTimer = setTimeout(showScreensaver, 20000);   // 20s
}

function showScreensaver() {
  if (!isPlaying) {
    resetScreensaver();
    return;
  }
  _ssActive = true;
  const ss = document.getElementById('screensaver');
  ss.classList.add('active');
  ss.classList.remove('dim');

  // Mettre à jour le contenu
  updateScreensaverContent();

  // Assombrir progressivement après 10s
  _dimTimer = setTimeout(() => {
    ss.classList.add('dim');
  }, 10000);
}

function hideScreensaver() {
  _ssActive = false;
  const ss = document.getElementById('screensaver');
  ss.classList.remove('active', 'dim');
  clearTimeout(_dimTimer);
  resetScreensaver();
}

function updateScreensaverContent() {
  const title  = document.getElementById('pb-title').textContent;
  const author = document.getElementById('pb-author').textContent;

  document.getElementById('ss-title').textContent  = title;
  document.getElementById('ss-author').textContent = author;

  // Pochette en fond
  if (currentItem) {
    document.getElementById('ss-cover').style.backgroundImage =
      `url('/api/abs/cover/${currentItem.id}')`;
  }

  // Progression
  if (pState.duration > 0) {
    const pct = (pState.position / pState.duration * 100).toFixed(1);
    document.getElementById('ss-progress-fill').style.width = pct + '%';
    document.getElementById('ss-time').textContent =
      fmtTime(pState.position) + ' / ' + fmtTime(pState.duration);
  }
}

// Mettre à jour l'écran de veille si actif
setInterval(() => {
  if (_ssActive) updateScreensaverContent();
}, 2000);

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').catch(() => {});
}

