/*
 * Service worker „Szczypta Smaku" - aplikacja instalowalna (PWA) i czytanie przepisów offline.
 *
 * Strategie:
 *  - strony HTML: najpierw sieć (zawsze świeża treść), a bez sieci - wersja zapisana
 *    przy ostatniej wizycie albo strona /offline. Zapisujemy tylko strony oznaczone
 *    przez serwer nagłówkiem X-Offline-Cacheable (publiczne, oglądane bez logowania),
 *    więc panel administracyjny i dane zalogowanego użytkownika nigdy nie trafiają do cache.
 *  - CSS/JS/ikony: z cache od razu, a w tle pobieramy nowszą wersję (stale-while-revalidate).
 *  - zdjęcia przepisów (/static/uploads/): z cache, a jeśli ich nie ma - z sieci.
 *  - wszystko poza GET (formularze, oceny, komentarze) idzie zawsze prosto do serwera.
 */
"use strict";

const VERSION = "v2";
const STATIC_CACHE = `static-${VERSION}`;
const PAGES_CACHE = `pages-${VERSION}`;
const IMAGES_CACHE = `images-${VERSION}`;
const MAX_PAGES = 60;
const MAX_IMAGES = 80;

const PRECACHE = [
  "/offline",
  "/lista-zakupow",
  "/ulubione",
  "/static/style.css",
  "/static/js/app.js",
  "/static/js/shopping-store.js",
  "/static/js/recipe.js",
  "/static/js/shopping.js",
  "/static/js/favorites.js",
  "/static/js/offline.js",
  "/static/logo.png",
  "/static/icons/icon-192.png",
];

// Ścieżki, których nigdy nie zapisujemy (panel, logowanie). Offline pokazujemy dla nich /offline.
const NEVER_CACHE = /^\/(admin|redakcja|login|logout|konto|healthz)(\/|$)/;

self.addEventListener("install", (event) => {
  // credentials: "omit" - strony pobieramy jak anonimowy czytelnik, nawet gdy w tej
  // przeglądarce zalogowany jest administrator (nie zapisujemy menu ani danych panelu).
  const requests = PRECACHE.map((url) => new Request(url, { credentials: "omit" }));
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => cache.addAll(requests)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  const keep = [STATIC_CACHE, PAGES_CACHE, IMAGES_CACHE];
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => !keep.includes(k)).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

async function trimCache(name, max) {
  const cache = await caches.open(name);
  const keys = await cache.keys();
  // Klucze są w kolejności dodania - usuwamy najstarsze.
  for (let i = 0; i < keys.length - max; i++) await cache.delete(keys[i]);
}

async function handlePage(request) {
  const url = new URL(request.url);
  try {
    const response = await fetch(request);
    if (response.ok && response.headers.get("X-Offline-Cacheable") === "1") {
      const cache = await caches.open(PAGES_CACHE);
      await cache.delete(request); // przenosi stronę na koniec kolejki (najświeższa)
      await cache.put(request, response.clone());
      trimCache(PAGES_CACHE, MAX_PAGES);
    }
    return response;
  } catch (err) {
    const cached =
      (await caches.match(request)) ||
      (url.pathname === "/" ? await caches.match("/", { ignoreSearch: true }) : undefined);
    return cached || (await caches.match("/offline")) || Response.error();
  }
}

async function handleStatic(request, event) {
  const cache = await caches.open(STATIC_CACHE);
  const cached = await cache.match(request);
  const network = fetch(request)
    .then((response) => {
      if (response.ok) {
        const copy = response.clone();
        event.waitUntil(cache.put(request, copy));
      }
      return response;
    })
    .catch(() => cached);
  if (cached) {
    event.waitUntil(network);
    return cached;
  }
  return network;
}

async function handleImage(request) {
  const cached = await caches.match(request);
  if (cached) return cached;
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(IMAGES_CACHE);
      await cache.put(request, response.clone());
      trimCache(IMAGES_CACHE, MAX_IMAGES);
    }
    return response;
  } catch (err) {
    return Response.error();
  }
}

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (NEVER_CACHE.test(url.pathname)) {
    // Tylko sieć - ale zamiast błędu przeglądarki pokazujemy stronę offline.
    if (request.mode === "navigate") {
      event.respondWith(fetch(request).catch(() => caches.match("/offline").then((r) => r || Response.error())));
    }
    return;
  }

  if (request.mode === "navigate") {
    event.respondWith(handlePage(request));
  } else if (url.pathname.startsWith("/static/uploads/")) {
    event.respondWith(handleImage(request));
  } else if (url.pathname.startsWith("/static/")) {
    event.respondWith(handleStatic(request, event));
  } else if (url.pathname.startsWith("/api/")) {
    // API ulubionych: sieć, a offline - ostatnia odpowiedź.
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response.ok) {
            const copy = response.clone(); // kopia PRZED oddaniem odpowiedzi stronie
            event.waitUntil(caches.open(PAGES_CACHE).then((c) => c.put(request, copy)));
          }
          return response;
        })
        .catch(() => caches.match(request).then((r) => r || Response.error()))
    );
  }
});
