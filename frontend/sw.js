// Service worker AudioBox.
// La page (HTML) passe TOUJOURS d'abord par le réseau : après une mise à jour, l'écran
// affiche tout de suite la nouvelle version. Avant (v1.3), la vieille page en cache
// était resservie à chaque démarrage. Le cache ne sert plus que si le serveur ne
// répond pas (box en train de redémarrer).
const CACHE = 'audiobox-v1.7';
const PRECACHE = ['/', '/index.html', '/manifest.json'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(PRECACHE)).catch(() => {}));
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys =>
    Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
  ));
  self.clients.claim();
});

self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET' || e.request.url.includes('/api/')) return;
  e.respondWith(
    fetch(e.request, {cache: 'no-store'}).then(res => {
      if (res.ok) {
        const copie = res.clone();
        caches.open(CACHE).then(c => c.put(e.request, copie));
      }
      return res;
    }).catch(() => caches.match(e.request))
  );
});
