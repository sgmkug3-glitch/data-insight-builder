import os
import sys

# 프로젝트 루트 디렉터리를 sys.path에 추가하여 app.py 및 tools.py 임포트 지원
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app

# Vercel Serverless Function 진입점
app_entry = app
