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
    """
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        environ["SCRIPT_NAME"] = ""

        # 1. vercel.json rewrite에서 전달된 __vercel_path 파라미터 확인
        query_string = environ.get("QUERY_STRING", "")
        qs = parse_qs(query_string)
        if "__vercel_path" in qs and qs["__vercel_path"]:
            raw_path = qs["__vercel_path"][0]
            while raw_path.startswith("//"):
                raw_path = raw_path[1:]
            environ["PATH_INFO"] = raw_path or "/"
        else:
            # 2. Vercel이 전달한 원본 경로 헤더 확인
            orig = (
                environ.get("HTTP_X_INVOKE_PATH")
                or environ.get("HTTP_X_FORWARDED_PATH")
                or environ.get("HTTP_X_ORIGINAL_URI")
                or environ.get("HTTP_X_MATCHED_PATH")
                or environ.get("REQUEST_URI")
            )
            if orig:
                parsed = urlparse(orig).path
                if parsed and not parsed.startswith("/api/index"):
                    environ["PATH_INFO"] = parsed

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
