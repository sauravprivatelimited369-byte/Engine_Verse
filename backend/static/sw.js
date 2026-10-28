/* Meridian service worker (codename: engineverse).
 * Cache-first for immutable WebAssembly compiler toolchains and static assets,
 * network-first with cache fallback for app scripts/styles and pages,
 * never caches authenticated or mutating requests.
 */
// Bumped whenever a cached asset changes behaviour. v6: sign-in became
// compulsory and the practice cards changed, so a v5 app.js must not linger.
// v8: pages-live.js learned to resolve the ids the exported account pages
// actually use (the signup/sign-in/recovery OTP steps, the account icon) and
// stopped throwing on the first page it hydrated.
// v10: pages-live.js/codelab.js learned to run every language on the vendored
// WebAssembly toolchains (runtimes/).
// v11: cache-first WebAssembly toolchain caching without stream tee stalls,
// never serve HTML fallbacks to non-navigation script/wasm requests, and
// pre-cache worker entrypoints for instant offline compiler boot.
// v12: the 2026 visual layer, self-hosted Inter/Sora variable fonts, scroll.js
// (topbar auto-hide + study-plan progress) and the new home/dashboard markup.
// v14: the MERIDIAN identity — warm-paper glass, navy ink, signal blue.
// v15: offline device speech and tutor answer controls; drop older cached JS.
// v16: 3D observatory, scroll walkthrough, live workbench & meridian.css shell.
// v17: contrast fix to the subject initials in app.css (a shell asset), so an
// offline visitor must not keep the pre-fix stylesheet.
const VERSION = "meridian-v17";
const SHELL = [
  "/static/css/app.css",
  "/static/css/meridian.css",
  "/static/css/codelab.css",
  "/static/css/voice.css",
  "/static/js/app.js",
  "/static/js/voice.js",
  "/static/js/codelab.js",
  "/static/js/pages-live.js",
  "/static/js/ev-runtime-worker.js",
  "/static/js/csharp-worker.js",
  "/static/js/capabilities.js",
  "/static/js/engine3d.js",
  "/static/js/scroll.js",
  "/static/fonts/inter-latin-wght-normal.woff2",
  "/static/fonts/newsreader-latin-wght-normal.woff2",
  "/static/fonts/newsreader-latin-wght-italic.woff2",
  "/static/fonts/sora-latin-wght-normal.woff2",
  "/static/icons/favicon.svg",
  "/static/offline.html",
  "/manifest.webmanifest",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

function cacheable(request) {
  if (request.method !== "GET") return false;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return false;
  if (/\/api\//.test(url.pathname)) return false;
  if (/\/settings(\/|$)/.test(url.pathname)) return false;
  if (/\/admin(\/|$)/.test(url.pathname)) return false;
  return true;
}

// The path checks above are not sufficient on their own. The server marks
// authenticated HTML private/no-store. Anonymous HTML is private to HTTP
// caches too (it carries a browser-bound CSRF token), but may be stored in this
// browser's own offline cache when explicitly marked X-Offline-Cache: anonymous.
function storable(response) {
  if (!response || !response.ok) return false;
  const cc = (response.headers.get("Cache-Control") || "").toLowerCase();
  if (cc.includes("no-store")) return false;
  if (cc.includes("private") && response.headers.get("X-Offline-Cache") !== "anonymous") return false;
  return true;
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (!cacheable(request)) return;

  const url = new URL(request.url);
  const isRuntimeManifest = /\/runtimes\/manifest\.json$/.test(url.pathname);
  const isToolchainBinary = !isRuntimeManifest && /\/(runtimes|pyodide)\//.test(url.pathname);

  // Pinned WebAssembly compiler toolchains (/runtimes/*, /pyodide/*):
  // Cache-first so each toolchain downloads once and runs offline in milliseconds
  // on subsequent sessions without re-downloading 10-57 MiB over mobile data.
  // Buffered cleanly so Blink's ServiceWorker stream tee never stalls large WASM bodies.
  if (isToolchainBinary) {
    event.respondWith((async () => {
      const hit = await caches.match(request);
      if (hit) return hit;
      const res = await fetch(request);
      if (!storable(res)) return res;
      const buf = await res.arrayBuffer();
      const headers = new Headers(res.headers);
      headers.delete("content-encoding");
      headers.set("content-length", String(buf.byteLength));
      const stored = new Response(buf.slice(0), {
        status: res.status,
        statusText: res.statusText,
        headers,
      });
      event.waitUntil(
        caches.open(VERSION).then((c) => c.put(request, stored)).catch(() => {})
      );
      return new Response(buf, {
        status: res.status,
        statusText: res.statusText,
        headers,
      });
    })());
    return;
  }

  const isCode = isRuntimeManifest || request.destination === "style" || request.destination === "script" ||
                 request.destination === "worker" || /\/static\/(js|css)\//.test(url.pathname);
  const isStatic = isCode || request.destination === "image" || request.url.includes("/static/");

  // Scripts, workers, styles, and runtime manifest: network first, cached copy offline.
  if (isCode) {
    event.respondWith(
      fetch(request).then((res) => {
        if (storable(res)) {
          const copy = res.clone();
          event.waitUntil(caches.open(VERSION).then((c) => c.put(request, copy)).catch(() => {}));
        }
        return res;
      }).catch(() => caches.match(request).then((hit) => hit || Response.error()))
    );
    return;
  }

  if (isStatic) {
    event.respondWith(
      caches.match(request).then((hit) => hit || fetch(request).then((res) => {
        if (storable(res)) {
          const copy = res.clone();
          event.waitUntil(caches.open(VERSION).then((c) => c.put(request, copy)).catch(() => {}));
        }
        return res;
      }).catch(() => (request.mode === "navigate" ? caches.match("/static/offline.html") : Response.error())))
    );
    return;
  }

  // Pages: fresh from the network when possible, cached copy offline. Non-navigation
  // background requests fail cleanly rather than returning HTML where JSON/bytes were expected.
  event.respondWith(
    fetch(request).then((res) => {
      if (storable(res)) {
        const copy = res.clone();
        event.waitUntil(caches.open(VERSION).then((c) => c.put(request, copy)).catch(() => {}));
      }
      return res;
    }).catch(() =>
      caches.match(request).then((hit) => {
        if (hit) return hit;
        return request.mode === "navigate" ? caches.match("/static/offline.html") : Response.error();
      })
    )
  );
});
