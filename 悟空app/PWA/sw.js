const CACHE = "wukong-pwa-v122";
const ASSETS = [
  "./",
  "./index.html",
  "./install.html",
  "./privacy.html",
  "./styles.css",
  "./app.js",
  "./shell.js",
  "./manifest.webmanifest",
  "./favicon.ico",
  "./wukong_latest_snapshot.json",
  "./exchange_markets.json",
  "./gate_private_status.json",
  "./gate_markets.json",
  "./ema_cross_4h.json",
  "./ema_cross_4h_bootstrap.js",
  "./x_social.json",
  "./binance_alpha.json",
  "./telegram_status.json",
  "./wukong_file_sync.json",
  "./qr/wukong-ios-qr.png",
  "./qr/wukong-android-qr.png",
  "./icons/wukong-180.png",
  "./icons/wukong-192.png",
  "./icons/wukong-512.png"
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(ASSETS)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))))
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (url.hostname === "michill.ai" || url.hostname === "api.binance.com" || url.hostname === "fapi.binance.com" || url.hostname === "www.okx.com" || url.hostname === "api.gateio.ws" || url.hostname === "api.x.com") {
    event.respondWith(fetch(event.request));
    return;
  }
  if (event.request.mode === "navigate" || url.pathname.endsWith("/index.html")) {
    event.respondWith(fetch(event.request).then((response) => {
      const copy = response.clone();
      caches.open(CACHE).then((cache) => cache.put(event.request, copy));
      return response;
    }).catch(() => caches.match(event.request, { ignoreSearch: true }).then((cached) => cached || caches.match("./index.html"))));
    return;
  }
  if (url.pathname.endsWith("/app.js") || url.pathname.endsWith("/shell.js") || url.pathname.endsWith("/styles.css") || url.pathname.endsWith("/sw.js") || url.pathname.endsWith("/manifest.webmanifest")) {
    event.respondWith(fetch(event.request).then((response) => {
      const copy = response.clone();
      caches.open(CACHE).then((cache) => cache.put(event.request, copy));
      return response;
    }).catch(() => caches.match(event.request, { ignoreSearch: true })));
    return;
  }
  if (url.pathname.endsWith("/wukong_latest_snapshot.json") || url.pathname.endsWith("/exchange_markets.json") || url.pathname.endsWith("/gate_private_status.json") || url.pathname.endsWith("/gate_markets.json") || url.pathname.endsWith("/x_social.json") || url.pathname.endsWith("/binance_alpha.json") || url.pathname.endsWith("/telegram_status.json") || url.pathname.endsWith("/wukong_file_sync.json")) {
    event.respondWith(fetch(event.request).catch(() => caches.match(event.request)));
    return;
  }
  event.respondWith(caches.match(event.request, { ignoreSearch: true }).then((cached) => cached || fetch(event.request)));
});
