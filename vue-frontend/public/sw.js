/* LLHhy Blog Service Worker（v3.21.0）
 * 策略：
 *  - 导航请求（HTML 页面）：network-first，离线回退到缓存壳页 → /offline.html
 *  - 带哈希的静态资源（/assets/*、/icon-*.png 等）：stale-while-revalidate（不可变，长期缓存）
 *  - 文章只读 API（GET /api/post/*、/api/posts）：stale-while-revalidate，离线可读缓存文章
 *  - 后台/管理/写操作 API（/api/* 其余、/admin/*）：不缓存、直接放行
 * 不触碰任何会话态写接口，避免离线误改数据。
 */
const CACHE = "llhhy-pwa-v1";
const OFFLINE = "/offline.html";
const PRECACHE = [
  "/",
  "/index.html",
  "/favicon.svg",
  "/og-default.png",
  "/manifest.webmanifest",
  "/offline.html",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(PRECACHE)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

function isArticleApi(url) {
  return url.pathname.startsWith("/api/post/") || url.pathname.startsWith("/api/posts");
}

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  // 后台/管理/非文章写接口：不缓存，直接放行
  if (url.pathname.startsWith("/admin")) return;
  if (url.pathname.startsWith("/api/") && !isArticleApi(url)) return;

  // 导航：network-first
  if (req.mode === "navigate") {
    event.respondWith(
      fetch(req)
        .then((res) => {
          const cp = res.clone();
          caches.open(CACHE).then((c) => c.put(req, cp));
          return res;
        })
        .catch(() => caches.match(req).then((r) => r || caches.match(OFFLINE)))
    );
    return;
  }

  // 其余：stale-while-revalidate
  event.respondWith(
    caches.match(req).then((cached) => {
      const network = fetch(req)
        .then((res) => {
          const cp = res.clone();
          caches.open(CACHE).then((c) => c.put(req, cp));
          return res;
        })
        .catch(() => cached);
      return cached || network;
    })
  );
});
