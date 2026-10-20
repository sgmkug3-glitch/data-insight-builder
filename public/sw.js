/**
 * Service Worker for AI Data Insight Builder (PWA)
 * Strictly conforms to Google Chrome PWA Installability Specifications
 */

const CACHE_NAME = "insight-builder-v2";

// 정적 에셋 목록 (리다이렉트 302가 발생할 수 있는 "/"나 "/login"은 설치 시점에 포함하지 않음)
const STATIC_PRECACHE = [
    "/static/style.css",
    "/static/app.js",
    "/static/manifest.json",
    "/static/icons/icon-192.png",
    "/static/icons/icon-512.png",
    "/static/icons/icon-maskable.png",
    "/static/icons/apple-touch-icon.png",
    "/static/icons/favicon.ico"
];

// 1. Install Event: 정적 에셋 안전 캐싱 및 즉시 활성화 준비
self.addEventListener("install", (event) => {
    self.skipWaiting();
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            // Promise.allSettled를 사용하여 개별 에셋 실패가 전체 설치를 중단시키지 않도록 방어
            return Promise.allSettled(
                STATIC_PRECACHE.map((url) => {
                    return fetch(url, { cache: "no-cache" }).then((res) => {
                        if (res.ok) {
                            return cache.put(url, res);
                        }
                    }).catch((err) => {
                        console.warn("[SW] 개별 에셋 캐싱 건너뜀:", url, err);
                    });
                })
            );
        })
    );
});

// 2. Activate Event: 구버전 캐시 정리 및 제어권 즉시 획득
self.addEventListener("activate", (event) => {
    event.waitUntil(
        caches.keys().then((keys) => {
            return Promise.all(
                keys.map((key) => {
                    if (key !== CACHE_NAME) {
                        return caches.delete(key);
                    }
                })
            );
        }).then(() => self.clients.claim())
    );
});

// 3. Fetch Event: Chrome PWA 오프라인/탐색 요구조건 충족
self.addEventListener("fetch", (event) => {
    const req = event.request;
    const url = new URL(req.url);

    // 내부 분석 API 엔드포인트는 항상 네트워크 직행
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
        return;
    }

    // 네비게이션 요청 (HTML 페이지 이동)
    if (req.mode === "navigate") {
        event.respondWith(
            fetch(req)
                .then((networkRes) => {
                    return networkRes;
                })
                .catch(() => {
                    // 네트워크 단절 시 캐시된 페이지 반환 시도
                    return caches.match(req).then((cached) => {
                        if (cached) return cached;
                        return caches.match("/login") || caches.match("/");
                    });
                })
        );
        return;
    }

    // 정적 에셋 (JS, CSS, 아이콘)
    event.respondWith(
        caches.match(req).then((cachedRes) => {
            const fetchPromise = fetch(req)
                .then((networkRes) => {
                    if (networkRes && networkRes.status === 200) {
                        const resClone = networkRes.clone();
                        caches.open(CACHE_NAME).then((cache) => {
                            cache.put(req, resClone);
                        });
                    }
                    return networkRes;
                })
                .catch(() => cachedRes);

            return cachedRes || fetchPromise;
        })
    );
});
