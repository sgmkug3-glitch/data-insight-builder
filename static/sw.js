/**
 * Service Worker for AI Data Insight Builder (PWA)
 * Enables installation on Chrome Mobile & offline shell caching
 */

const CACHE_NAME = "insight-builder-v1";
const STATIC_ASSETS = [
    "/",
    "/login",
    "/static/style.css",
    "/static/app.js",
    "/static/manifest.json",
    "/static/icons/icon-192.png",
    "/static/icons/icon-512.png",
    "/static/icons/apple-touch-icon.png",
    "/static/icons/favicon.ico"
];

// 1. 설치 (Install) & 셸 에셋 사전 캐싱
self.addEventListener("install", (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            console.log("[SW] 캐시 스토리지 초기화 및 정적 에셋 등록");
            return cache.addAll(STATIC_ASSETS).catch((err) => {
                console.warn("[SW] 일부 에셋 사전 캐싱 실패 (계속 진행):", err);
            });
        }).then(() => self.skipWaiting())
    );
});

// 2. 활성화 (Activate) & 구버전 캐시 정리
self.addEventListener("activate", (event) => {
    event.waitUntil(
        caches.keys().then((keys) => {
            return Promise.all(
                keys.map((key) => {
                    if (key !== CACHE_NAME) {
                        console.log("[SW] 이전 버전 캐시 삭제:", key);
                        return caches.delete(key);
                    }
                })
            );
        }).then(() => self.clients.claim())
    );
});

// 3. 네트워크 요청 가로채기 (Fetch)
self.addEventListener("fetch", (event) => {
    const req = event.request;
    const url = new URL(req.url);

    // API 요청이나 POST/PUT/DELETE 등 변경 작업은 무조건 실시간 네트워크 직행
    if (
        req.method !== "GET" ||
        url.pathname.startsWith("/inspect") ||
        url.pathname.startsWith("/run") ||
        url.pathname.startsWith("/suggest") ||
        url.pathname.startsWith("/explain") ||
        url.pathname.startsWith("/ask") ||
        url.pathname.startsWith("/chat") ||
        url.pathname.startsWith("/health")
    ) {
        event.respondWith(fetch(req));
        return;
    }

    // 정적 리소스(CSS, JS, 이미지, 아이콘)는 Network-First 또는 Stale-While-Revalidate
    event.respondWith(
        fetch(req)
            .then((networkRes) => {
                // 성공적인 응답은 캐시에 백업
                if (networkRes && networkRes.status === 200 && networkRes.type === "basic") {
                    const resClone = networkRes.clone();
                    caches.open(CACHE_NAME).then((cache) => {
                        cache.put(req, resClone);
                    });
                }
                return networkRes;
            })
            .catch(() => {
                // 네트워크 단절 시 캐시에서 제공
                return caches.match(req).then((cachedRes) => {
                    if (cachedRes) {
                        return cachedRes;
                    }
                    if (req.mode === "navigate") {
                        return caches.match("/login") || caches.match("/");
                    }
                });
            })
    );
});
