// Service worker minimal : l'interface reste ouverte hors ligne, l'API n'est jamais mise en cache.
const CACHE = "sc-v22";
const SHELL = ["/", "/style.css", "/stats.css", "/app.js", "/stats.js", "/i18n.js", "/i18n/en.json", "/theme.js", "/manifest.webmanifest", "/icons/icon-192.png", "/fonts/Inter.woff2"];
const API = ["/users", "/bank", "/version", "/healthz"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;
  if (API.some((p) => url.pathname === p || url.pathname.startsWith(p + "/"))) return;
  e.respondWith(
    fetch(e.request)
      .then((res) => {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(e.request, copy));
        return res;
      })
      .catch(() => caches.match(e.request).then((r) => r || caches.match("/")))
  );
});

// Notifications natives (Web Push) : alertes du coach
self.addEventListener("push", (e) => {
  let d = {};
  try { d = e.data.json(); } catch { /* message sans données */ }
  e.waitUntil(self.registration.showNotification(d.title || "Sport Coach", {
    body: d.body || "", icon: "/icons/icon-192.png", badge: "/icons/icon-192.png", data: { url: d.url || "/" } }));
});

self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  e.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((cs) =>
    cs.length ? cs[0].focus() : self.clients.openWindow((e.notification.data && e.notification.data.url) || "/")));
});
