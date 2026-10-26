import os
import sys
from urllib.parse import parse_qs, urlparse

# 프로젝트 루트 디렉터리를 sys.path에 추가하여 app.py 및 tools.py 임포트 지원
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from app import app

class VercelPathMiddleware:
    """
    Vercel 서버리스 환경에서 SCRIPT_NAME 왜곡 및 PATH_INFO를 원래 요청 경로로 완전 복원합니다.
    GET 및 POST 요청 모두에서 원래 의도된 엔드포인트(/login, /inspect 등)를 정확히 추출합니다.
    """
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        environ["SCRIPT_NAME"] = ""

        found_path = None
        # 1. QUERY_STRING 우선 파싱
        qs = parse_qs(environ.get("QUERY_STRING", ""))
        if "__vercel_path" in qs and qs["__vercel_path"]:
            found_path = qs["__vercel_path"][0]

        # 2. Vercel 헤더들에서 파싱
        if not found_path:
            for header_val in [
                environ.get("HTTP_X_MATCHED_PATH", ""),
                environ.get("HTTP_X_VERCEL_MATCHED_PATH", ""),
                environ.get("HTTP_X_INVOKE_PATH", ""),
                environ.get("HTTP_X_FORWARDED_PATH", ""),
                environ.get("HTTP_X_ORIGINAL_URI", ""),
                environ.get("REQUEST_URI", ""),
                environ.get("RAW_URI", "")
            ]:
                if not header_val:
                    continue
                parsed = urlparse(header_val if "?" in header_val else ("?" + header_val))
                h_qs = parse_qs(parsed.query)
                if "__vercel_path" in h_qs and h_qs["__vercel_path"]:
                    found_path = h_qs["__vercel_path"][0]
                    break
                p = urlparse(header_val).path
                if p and not p.startswith("/api/index") and not p.startswith("/api/"):
                    found_path = p
                    break

        if found_path:
            while found_path.startswith("//"):
                found_path = found_path[1:]
            environ["PATH_INFO"] = found_path or "/"
        else:
            path = environ.get("PATH_INFO", "")
            # 3. /api/index 또는 /api 접두사 제거
            if path.startswith("/api/index.py"):
                path = path[len("/api/index.py"):] or "/"
                environ["PATH_INFO"] = path
            elif path.startswith("/api/index"):
                path = path[len("/api/index"):] or "/"
                environ["PATH_INFO"] = path
            elif path.startswith("/api"):
                path = path[len("/api"):] or "/"
                environ["PATH_INFO"] = path

        return self.wsgi_app(environ, start_response)

app.wsgi_app = VercelPathMiddleware(app.wsgi_app)
