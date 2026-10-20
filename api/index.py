import os
import sys
from urllib.parse import urlparse

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

        # 1. Vercel이 전달한 원본 경로 헤더 확인 (HTTP_X_MATCHED_PATH, REQUEST_URI 등)
        raw_uri = environ.get("HTTP_X_MATCHED_PATH") or environ.get("REQUEST_URI") or environ.get("RAW_URI")
        if raw_uri:
            parsed = urlparse(raw_uri).path
            if parsed and not parsed.startswith("/api/index"):
                environ["PATH_INFO"] = parsed

        path = environ.get("PATH_INFO", "")
        # 2. /api/index 접두사 제거
        if path.startswith("/api/index.py"):
            path = path[len("/api/index.py"):] or "/"
            environ["PATH_INFO"] = path
        elif path.startswith("/api/index"):
            path = path[len("/api/index"):] or "/"
            environ["PATH_INFO"] = path

        return self.wsgi_app(environ, start_response)

app.wsgi_app = VercelPathMiddleware(app.wsgi_app)
