import os
import sys

# 프로젝트 루트 디렉터리를 sys.path에 추가하여 app.py 및 tools.py 임포트 지원
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from app import app

class VercelPathMiddleware:
    """
    Vercel 서버리스 환경에서 /api/index로 요청이 전달될 때,
    PATH_INFO 및 SCRIPT_NAME을 복원하여 Flask 라우터가 원래 경로('/', '/login' 등)를 인식하도록 보정합니다.
    """
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        environ["SCRIPT_NAME"] = ""

        path = environ.get("PATH_INFO", "")
        # /api/index 또는 /api/index.py 접두사 제거
        if path.startswith("/api/index.py"):
            path = path[len("/api/index.py"):] or "/"
            environ["PATH_INFO"] = path
        elif path.startswith("/api/index"):
            path = path[len("/api/index"):] or "/"
            environ["PATH_INFO"] = path
        elif path == "/api" or path == "/api/":
            environ["PATH_INFO"] = "/"

        # Vercel이 헤더로 원본 경로를 보낸 경우 우선 적용
        matched_path = environ.get("HTTP_X_MATCHED_PATH")
        if matched_path and not matched_path.startswith("/api/index"):
            environ["PATH_INFO"] = matched_path

        return self.wsgi_app(environ, start_response)

app.wsgi_app = VercelPathMiddleware(app.wsgi_app)
