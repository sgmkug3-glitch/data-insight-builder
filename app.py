import csv
import io
import json
import logging
import math
import os
import re
import time
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, session, redirect, url_for
import numpy as np
import pandas as pd
import tools

# .env 환경변수 로드
load_dotenv()

# 로깅 설정 (print 대신 Python logging 모듈 사용)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("DataInsightBuilder")

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "data-insight-builder-auth-0412-key")

# 보안 접속 비밀번호 (기본값: 0412)
APP_PASSWORD = os.getenv("APP_PASSWORD", "0412")

# 업로드 크기 제한 설정 (기본값 10MB)
max_upload_mb = int(os.getenv("MAX_UPLOAD_MB", 10))
app.config["MAX_CONTENT_LENGTH"] = max_upload_mb * 1024 * 1024

# 메모리 전역 데이터셋 저장소 (디스크 영구 저장 대신 1개만 메모리 보관)
current_dataset = {
    "filename": None,
    "df": None,
    "encoding": None,
    "skiprows": 0,
    "filesize": 0,
    "raw_columns": []
}

ENCODING_CANDIDATES = ["utf-8-sig", "utf-8", "cp949", "euc-kr"]

# 집계 행(대륙, 경제권, 소득수준 등) 식별용 키워드
AGG_KEYWORDS = [
    "world", "oecd", "euro area", "european union", "high income", "low income",
    "middle income", "upper middle income", "lower middle income", "income",
    "area", "total", "states", "dividend", "classified", "sub-saharan",
    "latin america", "caribbean", "east asia", "south asia", "north america",
    "middle east", "ida & ibrd", "africa eastern", "africa western"
]


def sanitize_for_json(obj):
    """NaN, Infinity 등 JSON 비호환 수치를 None으로 안전하게 변환합니다."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    elif isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_for_json(x) for x in obj]
    elif pd.isna(obj):
        return None
    return obj


@app.before_request
def check_authentication():
    """요청 로깅 및 세션 기반 비밀번호 보안 인증 검사"""
    logger.info(f"[REQUEST] {request.method} {request.path}")

    # Vercel 서버리스 환경에서 /api/index 또는 /api가 붙는 경우 및 __vercel_path 파라미터 경로 정규화
    vpath = request.args.get("__vercel_path")
    if vpath:
        while vpath.startswith("//"):
            vpath = vpath[1:]
        norm_path = vpath or "/"
    else:
        norm_path = request.path
        if norm_path.startswith("/api/index.py"):
            norm_path = norm_path[len("/api/index.py"):] or "/"
        elif norm_path.startswith("/api/index"):
            norm_path = norm_path[len("/api/index"):] or "/"
        elif norm_path.startswith("/api"):
            norm_path = norm_path[len("/api"):] or "/"

    # 1. 로그인/로그아웃, 정적 파일, 헬스체크, PWA 엔드포인트는 절대 리다이렉트 금지 (무한 루프 방지)
    if (
        "login" in request.path
        or "login" in norm_path
        or request.endpoint == "login"
        or "logout" in request.path
        or "logout" in norm_path
        or request.path.startswith("/static/")
        or request.path.startswith("/public/")
        or norm_path in ["/login", "/logout", "/health", "/sw.js", "/manifest.json", "/favicon.ico"]
    ):
        return None

    # 2. X-App-Password 헤더 검사 (API 또는 자동화 테스트용)
    header_pw = request.headers.get("X-App-Password")
    if header_pw and header_pw == APP_PASSWORD:
        return None

    # 3. 세션 인증 확인
    if session.get("authenticated"):
        return None

    # 4. 미인증 요청 처리
    # API 요청(JSON 또는 주요 API 경로)인 경우 401 JSON 응답
    api_paths = ["/inspect", "/suggest", "/run", "/explain", "/ask", "/chat"]
    if norm_path in api_paths or request.is_json:
        logger.warning(f"[AUTH] 미인증 API 요청 차단: {request.path} (norm: {norm_path})")
        return jsonify({"error": "보안 인증이 필요합니다. 먼저 비밀번호를 입력해 로그인해주세요."}), 401

    # 일반 웹페이지 접속 요청인 경우 로그인 화면으로 리다이렉트
    logger.info(f"[AUTH] 미인증 브라우저 접근 -> /login 리다이렉트 (path: {request.path})")
    return redirect("/login")


@app.errorhandler(413)
def request_entity_too_large(error):
    """파일 크기 초과 에러 처리"""
    msg = f"파일 크기가 허용치({max_upload_mb}MB)를 초과했습니다."
    logger.warning(f"[ERROR] {msg}")
    return jsonify({"error": msg}), 413


@app.route("/login", methods=["GET", "POST"])
@app.route("/api/login", methods=["GET", "POST"])
@app.route("/api/index/login", methods=["GET", "POST"])
def login():
    """보안 로그인(비밀번호 0412) 처리 및 화면 제공"""
    if request.method == "GET":
        # GET 요청 시 절대 리다이렉트하지 않고 무조건 로그인 폼 제공 (루프 원천 차단)
        return render_template("login.html")

    # POST 처리
    password = ""
    if request.is_json:
        data = request.get_json() or {}
        password = str(data.get("password", "")).strip()
    else:
        password = str(request.form.get("password", "")).strip()

    if password == APP_PASSWORD:
        session["authenticated"] = True
        logger.info("[AUTH] 로그인 성공 (비밀번호 일치)")
        if request.is_json:
            return jsonify({"status": "success", "redirect": "/"}), 200
        return redirect("/")
    else:
        logger.warning("[AUTH] 로그인 실패 (비밀번호 불일치)")
        error_msg = "비밀번호가 올바르지 않습니다. 다시 입력해주세요."
        if request.is_json:
            return jsonify({"error": error_msg}), 401
        return render_template("login.html", error=error_msg), 401


@app.route("/logout")
@app.route("/api/index/logout")
def logout():
    """로그아웃 및 세션 해제"""
    session.pop("authenticated", None)
    logger.info("[AUTH] 로그아웃 완료")
    return redirect("/login")


@app.route("/sw.js")
@app.route("/api/index/sw.js")
def service_worker():
    """PWA 서비스 워커 제공 (루트 스코프 적용)"""
    response = app.send_static_file("sw.js")
    response.headers["Content-Type"] = "application/javascript; charset=utf-8"
    response.headers["Service-Worker-Allowed"] = "/"
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


@app.route("/manifest.json")
@app.route("/api/index/manifest.json")
def pwa_manifest():
    """PWA 웹앱 매니페스트 제공"""
    response = app.send_static_file("manifest.json")
    response.headers["Content-Type"] = "application/manifest+json; charset=utf-8"
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response


@app.route("/favicon.ico")
@app.route("/api/index/favicon.ico")
def favicon():
    """파비콘 제공"""
    return app.send_static_file("icons/favicon.ico")


@app.route("/")
@app.route("/api")
@app.route("/api/")
@app.route("/api/index")
@app.route("/api/index/")
def index():
    """메인 페이지를 반환합니다. (템플릿 준비 전에는 기본 안내 메시지 표시)"""
    logger.info("[RESPONSE] status=200 path=/")
    try:
        return render_template("index.html")
    except Exception:
        return "<h1>AI Data Insight Builder</h1><p>서버가 정상 동작 중입니다. (Step 13)</p><p><a href='/health'>/health 확인하기</a></p>"


@app.route("/health", methods=["GET"])
def health():
    """서버 상태와 API Key 설정 여부만 반환 (키 값 자체는 절대 노출 금지)"""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    has_api_key = bool(api_key and api_key != "your_gemini_api_key_here")
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    response_data = {
        "status": "ok",
        "service": "AI Data Insight Builder",
        "api_key_configured": has_api_key,
        "model": model_name,
        "dataset_loaded": current_dataset["df"] is not None
    }
    logger.info(f"[RESPONSE] status=200 path=/health api_key_configured={has_api_key}")
    return jsonify(response_data), 200


def detect_and_parse_csv(file_bytes, filename):
    """인코딩 순차 시도, 헤더 자동 감지, CSV 파싱 및 상세 진단을 수행합니다."""
    # 1. 인코딩 순차 시도
    decoded_text = None
    used_encoding = None

    for enc in ENCODING_CANDIDATES:
        try:
            decoded_text = file_bytes.decode(enc)
            used_encoding = enc
            logger.info(f"[ENCODING] {enc} 시도 성공 (filename={filename})")
            break
        except (UnicodeDecodeError, LookupError):
            logger.info(f"[ENCODING] {enc} 시도 실패 (디코딩 에러)")
            continue

    if decoded_text is None:
        raise ValueError("지원하는 인코딩(utf-8-sig, utf-8, cp949, euc-kr)으로 파일을 읽을 수 없습니다.")

    lines = decoded_text.splitlines()
    if not lines:
        raise ValueError("업로드된 파일의 내용이 비어 있습니다.")

    # 2. 앞쪽 여러 줄을 검사하여 헤더 행 자동 감지
    sample_lines = lines[:25]
    parsed_sample = list(csv.reader(sample_lines))
    non_empty_rows = [r for r in parsed_sample if any(c.strip() for c in r)]
    if not non_empty_rows:
        raise ValueError("내용이 비어 있어 유효한 행을 찾을 수 없습니다.")

    max_cols = max(len([c for c in r if c.strip()]) for r in non_empty_rows)
    skiprows = 0
    for idx, row in enumerate(parsed_sample):
        clean = [c.strip() for c in row if c.strip()]
        if len(clean) >= max_cols * 0.7 and len(clean) >= 2:
            skiprows = idx
            break

    logger.info(f"[HEADER] 헤더 줄 감지 결과 (건너뛴 줄 수={skiprows}, 헤더 행 인덱스={skiprows})")

    # 3. Pandas로 CSV 파싱
    try:
        df = pd.read_csv(io.StringIO(decoded_text), skiprows=skiprows)
    except Exception as e:
        logger.error(f"[ERROR] Pandas 파싱 실패: {e}")
        raise ValueError(f"CSV 파싱 중 오류가 발생했습니다: {str(e)}")

    logger.info(f"[CSV] parsing 완료 rows={len(df)} columns={len(df.columns)}")

    # 4. 열별 데이터 타입 및 분류
    dtypes = {str(c): str(df[c].dtype) for c in df.columns}
    numeric_columns = [str(c) for c in df.select_dtypes(include=[np.number]).columns]
    string_columns = [str(c) for c in df.select_dtypes(include=["object", "string"]).columns]

    # 연도 열 후보 (4자리 연도 형태인 열 탐색, 예: 1960 ~ 2025)
    year_columns = [str(c) for c in df.columns if re.match(r"^(19|20)\d{2}$", str(c))]

    # 5. 결측치 개수와 비율 (열별)
    missing_values = {}
    for c in df.columns:
        m_count = int(df[c].isna().sum())
        m_pct = round(float(df[c].isna().mean() * 100), 2)
        missing_values[str(c)] = {"count": m_count, "percentage": m_pct}

    # 6. 중복 행 수
    duplicate_rows_count = int(df.duplicated().sum())

    # 7. Unnamed 열 / 빈 열 목록
    unnamed_columns = [str(c) for c in df.columns if str(c).startswith("Unnamed:") or str(c).strip() == ""]
    empty_columns = [str(c) for c in df.columns if df[c].isna().all()]
    duplicate_cols = list(df.columns[df.columns.duplicated()].unique())

    # 8. 연도별 데이터 충실도 및 권장 기준연도 탐색
    year_coverage = {}
    recommended_reference_period = None
    if year_columns:
        for y in year_columns:
            year_coverage[str(y)] = int(df[y].notna().sum())

        max_cov = max(year_coverage.values()) if year_coverage else 0
        sorted_years = sorted(year_columns, reverse=True)
        # 최신 연도부터 탐색하여 최대 충실도의 70% 이상 채워진 최근 연도를 권장
        for y in sorted_years:
            if year_coverage[y] >= max_cov * 0.7:
                recommended_reference_period = y
                break

    # 9. 집계 행 후보 탐지 (첫 번째 문자열 열 또는 첫 번째 열 기준)
    aggregate_row_candidates = []
    first_col = df.columns[0]
    for idx, val in df[first_col].items():
        s = str(val).lower()
        for kw in AGG_KEYWORDS:
            if kw in s:
                aggregate_row_candidates.append({
                    "index": int(idx),
                    "label": str(val),
                    "matched_keyword": kw
                })
                break

    # 10. 경고 목록 생성
    warnings = []
    if unnamed_columns:
        warnings.append(f"이름이 없는 열({len(unnamed_columns)}개)이 발견되었습니다: {', '.join(unnamed_columns[:5])}")

    if empty_columns:
        warnings.append(f"데이터가 전혀 없는 빈 열({len(empty_columns)}개)이 포함되어 있습니다: {', '.join(empty_columns[:5])}")

    if duplicate_cols:
        warnings.append(f"중복된 열 이름이 존재합니다: {', '.join([str(c) for c in duplicate_cols])}")

    if duplicate_rows_count > 0:
        warnings.append(f"내용이 완전히 중복된 행이 {duplicate_rows_count}개 발견되었습니다.")

    if aggregate_row_candidates:
        samples = [c["label"] for c in aggregate_row_candidates[:3]]
        warnings.append(f"개별 단위가 아닌 대륙/경제권 등 집계 행 후보가 {len(aggregate_row_candidates)}개 감지되었습니다. (예: {', '.join(samples)} 등)")

    if year_columns and recommended_reference_period:
        latest_year = sorted(year_columns, reverse=True)[0]
        if latest_year != recommended_reference_period:
            cov_latest = year_coverage.get(latest_year, 0)
            cov_rec = year_coverage.get(recommended_reference_period, 0)
            warnings.append(f"최신 연도인 {latest_year}년은 데이터 충실도가 {cov_latest}개로 매우 낮습니다. 안정적인 분석을 위해 {recommended_reference_period}년(충실도 {cov_rec}개)을 기준 시점으로 권장합니다.")

    logger.info(f"[DIAGNOSE] 진단 완료 warnings={len(warnings)}, aggregates={len(aggregate_row_candidates)}, rec_year={recommended_reference_period}")

    # 11. 미리보기 10행 안전 변환
    preview_df = df.head(10).replace({np.nan: None})
    preview_rows = sanitize_for_json(preview_df.to_dict(orient="records"))

    diagnostics = {
        "df": df,
        "used_encoding": used_encoding,
        "skiprows": skiprows,
        "dtypes": dtypes,
        "numeric_columns": numeric_columns,
        "string_columns": string_columns,
        "year_columns": year_columns,
        "missing_values": missing_values,
        "duplicate_rows_count": duplicate_rows_count,
        "unnamed_columns": unnamed_columns,
        "empty_columns": empty_columns,
        "year_coverage": year_coverage,
        "recommended_reference_period": recommended_reference_period,
        "aggregate_row_candidates": aggregate_row_candidates,
        "preview_rows": preview_rows,
        "warnings": warnings
    }

    return diagnostics


@app.route("/inspect", methods=["POST"])
def inspect_file():
    """CSV 업로드, 인코딩·헤더 감지, 13개 항목 종합 진단 결과 JSON 반환"""
    if "file" not in request.files:
        msg = "업로드할 파일이 선택되지 않았습니다."
        logger.warning(f"[ERROR] {msg}")
        return jsonify({"error": msg}), 400

    uploaded_file = request.files["file"]
    filename = uploaded_file.filename

    if not filename:
        msg = "파일 이름이 비어 있습니다."
        logger.warning(f"[ERROR] {msg}")
        return jsonify({"error": msg}), 400

    if not filename.lower().endswith(".csv"):
        msg = "CSV 형식(.csv)의 파일만 지원됩니다."
        logger.warning(f"[ERROR] {msg}")
        return jsonify({"error": msg}), 400

    file_bytes = uploaded_file.read()
    filesize = len(file_bytes)
    logger.info(f"[FILE] name={filename} size={filesize} bytes")

    if filesize == 0:
        msg = "업로드된 파일이 빈 파일(0 바이트)입니다."
        logger.warning(f"[ERROR] {msg}")
        return jsonify({"error": msg}), 400

    try:
        diag = detect_and_parse_csv(file_bytes, filename)
    except ValueError as ve:
        logger.warning(f"[ERROR] {str(ve)}")
        return jsonify({"error": str(ve)}), 400
    except Exception as ex:
        logger.exception(f"[ERROR] 예상치 못한 오류: {ex}")
        return jsonify({"error": f"파일 처리 중 오류가 발생했습니다: {str(ex)}"}), 500

    df = diag["df"]

    # 메모리에 데이터셋 보관 (서버 재시작 시 초기화됨)
    current_dataset["filename"] = filename
    current_dataset["df"] = df
    current_dataset["encoding"] = diag["used_encoding"]
    current_dataset["skiprows"] = diag["skiprows"]
    current_dataset["filesize"] = filesize
    current_dataset["raw_columns"] = [str(c) for c in df.columns]
    current_dataset["recommended_reference_period"] = diag["recommended_reference_period"]
    current_dataset["aggregate_row_candidates"] = diag["aggregate_row_candidates"]

    # 진단에 포함할 13개 항목 종합 페이로드 구성
    response_payload = {
        "status": "success",
        # 1. 파일명, 파일 크기
        "filename": filename,
        "filesize_bytes": filesize,
        "filesize_kb": round(filesize / 1024, 2),
        # 2. 성공한 인코딩, 건너뛴 헤더 줄 수
        "encoding": diag["used_encoding"],
        "skipped_rows": diag["skiprows"],
        # 3. 행 수, 열 수, 열 이름
        "row_count": int(df.shape[0]),
        "col_count": int(df.shape[1]),
        "column_names": [str(c) for c in df.columns],
        # 4. 열별 데이터 타입
        "dtypes": diag["dtypes"],
        # 5. 숫자형 열, 문자형 열, 연도·날짜 후보 열
        "numeric_columns": diag["numeric_columns"],
        "string_columns": diag["string_columns"],
        "year_columns": diag["year_columns"],
        # 6. 결측치 개수와 비율 (열별)
        "missing_values": diag["missing_values"],
        # 7. 중복 행 수
        "duplicate_rows_count": diag["duplicate_rows_count"],
        # 8. Unnamed 열 / 빈 열 목록
        "unnamed_columns": diag["unnamed_columns"],
        "empty_columns": diag["empty_columns"],
        # 9. 연도별 데이터 충실도
        "year_coverage": diag["year_coverage"],
        # 10. 권장 기준연도
        "recommended_reference_period": diag["recommended_reference_period"],
        # 11. 집계 행 후보
        "aggregate_row_candidates": diag["aggregate_row_candidates"],
        # 12. 데이터 미리보기 10행
        "preview_rows": diag["preview_rows"],
        # 13. 경고 목록
        "warnings": diag["warnings"],
        "notice": "데이터는 서버 메모리에만 1개 세트로 임시 보관되며, 서버를 재시작하면 사라집니다."
    }

    logger.info(f"[RESPONSE] status=200 path=/inspect filename={filename} rows={df.shape[0]} cols={df.shape[1]}")
    return jsonify(response_payload), 200


# ==============================================================================
# 도구 카탈로그 정의 (Gemini가 제안할 수 있는 12개 도구 목록)
# ==============================================================================
TOOL_CATALOG = [
    {
        "name": "reshape_wide_to_long",
        "title": "연도 열을 행으로 접기",
        "description": "가로로 펼쳐진 연도 열들을 행으로 접어 시계열 분석에 최적화된 표준 롱 포맷(Tidy Data)으로 변환합니다.",
        "requires_reference_period": False
    },
    {
        "name": "quality_report",
        "title": "데이터 품질 진단 리포트",
        "description": "결측치 순위, 중복 행, 이상한 열 이름 등 데이터셋 전반의 신뢰도를 종합 점검합니다.",
        "requires_reference_period": False
    },
    {
        "name": "year_coverage",
        "title": "연도별 충실도 및 권장 기준연도",
        "description": "연도별 유효값 수집 현황을 분석하여 결측치 위험이 적은 최적의 기준 시점을 제시합니다.",
        "requires_reference_period": False
    },
    {
        "name": "detect_aggregates",
        "title": "집계 그룹(대륙·소득군) 탐지",
        "description": "World, OECD members 등 개별 국가가 아닌 묶음 행들을 찾아내 왜곡을 사전에 방지합니다.",
        "requires_reference_period": False
    },
    {
        "name": "describe_numeric",
        "title": "핵심 기술통계량 산출",
        "description": "평균, 중앙값, 최소, 최대, 표준편차, 사분위수(Q1, Q3)를 도출하여 수치 특성을 요약합니다.",
        "requires_reference_period": True
    },
    {
        "name": "trend_line",
        "title": "주요 항목 연도별 시계열 추이",
        "description": "한국 및 주요국들의 연도별 변화 궤적을 꺾은선 차트로 비교합니다.",
        "requires_reference_period": False
    },
    {
        "name": "top_bottom_n",
        "title": "기준연도 상위·하위 순위 비교",
        "description": "동일 시점 기준 상위 및 하위 N개 항목을 추출하여 공정하게 서열을 비교합니다.",
        "requires_reference_period": True
    },
    {
        "name": "group_summary",
        "title": "대륙·그룹별 평균 비교",
        "description": "대륙(Region) 또는 소득군(IncomeGroup)별 평균 보급률을 산출하여 지역 격차를 비교합니다.",
        "requires_reference_period": True
    },
    {
        "name": "change_rate",
        "title": "두 시점 사이 성장량·성장률",
        "description": "과거 대비 기준 시점까지의 절대 포인트 변화량(%p)과 성장률을 계산합니다.",
        "requires_reference_period": True
    },
    {
        "name": "distribution",
        "title": "구간별 빈도 분포 (히스토그램)",
        "description": "수치 구간을 10개 계급으로 나누어 데이터가 어디에 쏠려 있는지 분포 형태를 파악합니다.",
        "requires_reference_period": True
    },
    {
        "name": "correlation_scatter",
        "title": "두 숫자 열 상관분석 및 산점도",
        "description": "피어슨 상관계수를 계산하고 산점도 좌표를 도출합니다. (주의: 상관관계 != 인과관계)",
        "requires_reference_period": True
    },
    {
        "name": "compare_one_vs_all",
        "title": "대한민국 vs 전체 평균·중앙값",
        "description": "한국의 위치를 전 세계 평균 및 중앙값과 1:1로 직접 벤치마킹하는 3색 막대 차트를 생성합니다.",
        "requires_reference_period": True
    }
]
ALLOWED_TOOL_NAMES = {t["name"] for t in TOOL_CATALOG}


@app.route("/ask", methods=["POST"])
def ask_natural_language():
    """
    자연어로 질문하면 의도를 파악하여 적합한 도구를 선정,
    Pandas로 실제 수치를 계산한 뒤, 데이터 기반의 자연어 답변과 맞춤 차트 데이터를 반환합니다.
    """
    if current_dataset["df"] is None:
        msg = "분석할 데이터셋이 없습니다. 먼저 CSV 파일을 업로드해 주세요."
        logger.warning(f"[ERROR] {msg}")
        return jsonify({"error": msg}), 400

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key or api_key == "your_gemini_api_key_here":
        msg = "GEMINI_API_KEY가 설정되지 않았습니다. .env 파일에 유효한 API Key를 입력해 주세요."
        logger.warning(f"[ERROR] {msg}")
        return jsonify({"error": msg}), 400

    data = request.get_json(silent=True) or {}
    query = data.get("query", "").strip()
    if not query:
        return jsonify({"error": "질문 내용을 입력해주세요."}), 400

    df = current_dataset["df"]
    rec_year = current_dataset.get("recommended_reference_period") or "2024"
    year_cols = tools.detect_year_columns(df)
    min_year = min(year_cols) if year_cols else "1960"
    max_year = max(year_cols) if year_cols else "2024"
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    catalog_summary = json.dumps([
        {"name": t["name"], "title": t["title"], "description": t["description"], "requires_reference_period": t["requires_reference_period"]}
        for t in TOOL_CATALOG
    ], ensure_ascii=False, indent=2)

    logger.info(f"[REQUEST] POST /ask query={query}")

    # 1. 자연어 질문을 12개 도구 카탈로그 및 파라미터로 매핑
    parse_prompt = f"""당신은 데이터 분석 질문 분류기입니다.
사용자가 데이터에 대해 다음과 같이 자연어로 질문했습니다:
"{query}"

이 질문을 가장 잘 분석하고 시각화할 수 있는 도구 1개와 적절한 파라미터를 아래 12개 도구 카탈로그 중에서 엄격히 선택하여 JSON으로 응답하세요:
{catalog_summary}

[데이터셋 정보]
- 권장 기준연도: {rec_year}
- 연도 범위: {min_year} ~ {max_year}
- 라벨 열: Country Name

[작성 규칙]
1. 도구(tool)는 반드시 카탈로그의 12개 영문 도구명 중 하나여야 합니다:
   - 상위/하위 순위, 순위권 국가, 특정 국가와 순위 비교 -> "top_bottom_n"
   - 대한민국(한국) vs 전 세계 평균/중앙값 1:1 벤치마킹 비교 -> "compare_one_vs_all"
   - 연도별 시계열 변화, 장기 추이, 특정 국가들의 연도별 흐름 -> "trend_line"
   - 전체 수치 기술통계 요약(평균, 중앙값, 최솟값, 최댓값, 표준편차) -> "describe_numeric"
   - 대륙별, 지역별, 소득군별 평균 비교 -> "group_summary"
   - 두 시점 사이 성장량(%p), 증가율(%), 가장 많이 성장한 나라 -> "change_rate"
   - 데이터 구간별 빈도 분포, 히스토그램, 데이터 쏠림 현상 -> "distribution"
   - 두 숫자 열 간 상관관계, 산점도 -> "correlation_scatter"
   - 결측치 순위, 데이터 누락, 데이터 품질 진단 리포트 -> "quality_report"
   - 연도별 데이터 수집 충실도, 추천 기준시점 -> "year_coverage"
   - 대륙·경제권 등 묶음 행(World, OECD 등) 집계 그룹 탐지 -> "detect_aggregates"
   - 연도 열을 행으로 변환 (언피벗, 롱 포맷 변환) -> "reshape_wide_to_long"
2. 기준 시점(reference_period)이 필요한 도구의 경우 질문에 특정 연도가 명시되어 있으면 그 연도를 사용하고, 없으면 권장 기준연도인 "{rec_year}"를 사용하세요.
3. n 파라미터가 필요한 경우(top_bottom_n, change_rate 등) 사용자가 언급한 개수(예: 1~10등이면 n=10)를 반영하고, 없으면 기본값 10을 사용하세요.
4. change_rate(성장률/변화량)의 경우 최근 기준 시점(reference_period)과 과거 비교 시점(compare_period)을 함께 추출하세요. (예: 2010년 대비 2024년이면 reference_period="2024", compare_period="2010")
5. 오직 아래 JSON 형식만 반환하세요:
{{
  "tool": "도구명",
  "params": {{
    "reference_period": "{rec_year}",
    "n": 10,
    "exclude_aggregates": true
  }},
  "analysis_title": "분석 요약 제목"
}}
"""

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        resp_intent = client.models.generate_content(
            model=model_name,
            contents=parse_prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1
            )
        )
        raw_text = resp_intent.text.strip()
        if raw_text.startswith("```"):
            raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
            raw_text = re.sub(r"\s*```$", "", raw_text)
        intent_data = json.loads(raw_text)
    except Exception as ex:
        logger.warning(f"[WARN] 자연어 의도 파악 기본값 폴백: {ex}")
        intent_data = {
            "tool": "top_bottom_n",
            "params": {"reference_period": rec_year, "n": 10, "exclude_aggregates": True},
            "analysis_title": f"{rec_year}년 상위 순위 분석"
        }

    tool_name = intent_data.get("tool")
    if tool_name not in ALLOWED_TOOL_NAMES:
        tool_name = "top_bottom_n"
    params = intent_data.get("params", {})
    if not isinstance(params, dict):
        params = {}
    if "reference_period" not in params:
        params["reference_period"] = rec_year

    # 2. Pandas로 실제 수치 계산 실행
    tool_func = getattr(tools, tool_name, None)
    if not tool_func:
        tool_func = tools.top_bottom_n
        tool_name = "top_bottom_n"

    try:
        import inspect
        sig = inspect.signature(tool_func)
        has_var_kw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
        call_params = params if has_var_kw else {k: v for k, v in params.items() if k in sig.parameters}
        run_res = tool_func(df, **call_params)
        run_res = sanitize_for_json(run_res)
    except Exception as run_err:
        logger.warning(f"[WARN] 도구 실행 오류 시 기본 top_bottom_n 대체: {run_err}")
        run_res = sanitize_for_json(tools.top_bottom_n(df, reference_period=rec_year, n=10, exclude_aggregates=True))
        tool_name = "top_bottom_n"
        params = {"reference_period": rec_year, "n": 10, "exclude_aggregates": True}

    # 한국(대한민국) 관련 수치 부가 컨텍스트 산출
    extra_context = {}
    label_col = tools.get_first_label_column(df)
    target_period = str(params.get("reference_period") or rec_year)
    if target_period in df.columns:
        filtered_clean, _, _ = tools.filter_aggregates(df, label_col=label_col, exclude_aggregates=True)
        valid_rank_df = filtered_clean.dropna(subset=[target_period]).copy()
        valid_rank_df["_val"] = pd.to_numeric(valid_rank_df[target_period], errors="coerce")
        valid_rank_df = valid_rank_df.dropna(subset=["_val"]).sort_values(by="_val", ascending=False)
        korea_match = valid_rank_df[valid_rank_df[label_col].astype(str).str.contains("Korea", case=False, na=False)]
        if len(korea_match) > 0:
            k_val = round(float(korea_match.iloc[0]["_val"]), 4)
            k_rank = int((valid_rank_df["_val"] > k_val).sum() + 1)
            extra_context["korea"] = {
                "name": str(korea_match.iloc[0][label_col]),
                "value": k_val,
                "rank": k_rank,
                "total_countries": len(valid_rank_df)
            }

    # 3. 계산된 실제 숫자를 바탕으로 자연어 답변 생성
    answer_prompt = f"""당신은 정확하고 신뢰할 수 있는 데이터 분석 교육 전문 AI입니다.
사용자가 다음 질문을 했습니다:
"{query}"

이 질문에 대해 Python Pandas가 실제 데이터셋에서 계산한 결과는 다음과 같습니다:
- 선택된 분석 도구: {tool_name}
- 기준 시점: {target_period}
- 계산 수치 결과: {json.dumps(run_res.get('data', {}), ensure_ascii=False, default=str)[:1500]}
- 대한민국 관련 계산 정보: {json.dumps(extra_context, ensure_ascii=False, default=str)}

[작성 가이드라인]
1. 사용자의 질문에 대해, 위에서 계산된 실제 사실과 수치만을 근거로 명확하고 친절하게 답변하세요.
2. 만약 질문에 대한민국이나 특정 국가와의 비교가 포함되어 있다면, 위의 대한민국 실제 수치(순위, 보급률 %)를 구체적으로 인용하여 비교 설명하세요.
3. 데이터에 없는 임의의 숫자를 절대로 지어내지 마세요.
4. 마크다운 형식(소제목, 볼드체, 글머리 기호)을 활용하여 2~3개의 읽기 쉬운 문단으로 구성하세요.
5. 답변 마지막에는 아래에 제공될 차트 시각화 버튼을 클릭하여 시각화와 추가 심층 보고서를 확인할 수 있음을 친절하게 안내하세요.
"""

    try:
        resp_answer = client.models.generate_content(
            model=model_name,
            contents=answer_prompt
        )
        answer_text = resp_answer.text.strip()
    except Exception as ex:
        logger.exception(f"[ERROR] 자연어 답변 생성 실패: {ex}")
        answer_text = f"계산이 완료되었습니다. ({tool_name} 실행 완료). 아래 버튼을 눌러 시각화 차트와 상세 보고서를 확인해 보세요."

    # 최근 실행 결과 및 질의 메모리에 보관 (Step 4, Step 5와 완벽 동기화)
    if isinstance(run_res, dict):
        run_res["user_query"] = query
    current_dataset["last_run_result"] = run_res
    current_dataset["last_query"] = query

    logger.info(f"[RESPONSE] status=200 path=/ask tool={tool_name}")
    return jsonify({
        "status": "success",
        "query": query,
        "tool": tool_name,
        "params": params,
        "title": intent_data.get("analysis_title", f"{target_period}년 맞춤 분석"),
        "answer": answer_text,
        "run_result": run_res
    }), 200


@app.route("/suggest", methods=["POST"])
def suggest_analyses():
    """
    진단 결과 요약과 도구 카탈로그를 Gemini에 전달하여 실행 가능한 분석 3~5개를 JSON으로 제안받습니다.
    (규칙: Gemini에게 CSV 원본 전체 전송 금지, 카탈로그 외 도구 제안 불가, 오직 JSON만 반환)
    """
    if current_dataset["df"] is None:
        msg = "진단된 데이터셋이 없습니다. 먼저 CSV 파일을 업로드해 주세요."
        logger.warning(f"[ERROR] {msg}")
        return jsonify({"error": msg}), 400

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key or api_key == "your_gemini_api_key_here":
        msg = "GEMINI_API_KEY가 설정되지 않았습니다. .env 파일에 유효한 API Key를 입력해 주세요."
        logger.warning(f"[ERROR] {msg}")
        return jsonify({"error": msg}), 400

    model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    df = current_dataset["df"]

    # Gemini에 보낼 요약 메타데이터 구성 (CSV 원본 전체는 절대 전송하지 않음)
    rec_year = current_dataset.get("recommended_reference_period") or "2024"
    str_cols = df.select_dtypes(include=["object", "string"]).columns.tolist()
    num_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    sample_cols = [str(c) for c in df.columns[:15]]

    diag_summary = {
        "filename": current_dataset.get("filename"),
        "total_rows": int(len(df)),
        "total_columns": int(len(df.columns)),
        "recommended_reference_period": str(rec_year),
        "label_column": str(str_cols[0]) if str_cols else str(df.columns[0]),
        "aggregate_candidates_count": len(current_dataset.get("aggregate_row_candidates", [])),
        "sample_columns": sample_cols,
        "numeric_columns_sample": [str(c) for c in num_cols[-10:]]
    }

    prompt = f"""당신은 교육용 데이터 분석 웹앱의 수석 데이터 분석가입니다.
사용자가 업로드한 데이터셋 진단 요약과 도구 카탈로그를 검토하고, 지금 데이터로 실행하기에 가장 유의미한 분석 3~5개를 골라 제안해주세요.

[엄격한 제약 규칙]
1. 도구(tool)는 반드시 아래 제공된 [도구 카탈로그]에 있는 12개 이름 중 하나여야 합니다. 카탈로그에 없는 도구는 절대 제안하지 마세요.
2. 데이터셋에 없는 열 이름을 제안하지 마세요.
3. 7~12번 도구는 reference_period(기준 시점)가 필수입니다. 권장 기준연도인 '{rec_year}'를 우선 활용하세요.
4. Gemini는 절대 수치를 직접 계산하지 마세요. (계산은 나중에 Pandas가 실행합니다.)
5. 반드시 아래 [출력 JSON 스키마] 형식의 순수 JSON만 응답하세요. 마크다운 따옴표(```json)나 부가 설명 문장은 일절 포함하지 마세요.
6. 3개 이상 5개 이하의 제안을 담으세요.

[데이터셋 진단 요약]
{json.dumps(diag_summary, ensure_ascii=False, indent=2)}

[도구 카탈로그]
{json.dumps(TOOL_CATALOG, ensure_ascii=False, indent=2)}

[출력 JSON 스키마]
{{
  "suggestions": [
    {{
      "tool": "카탈로그도구이름",
      "params": {{
        "reference_period": "{rec_year}",
        "exclude_aggregates": true
      }},
      "reference_period": "{rec_year}",
      "why": "이 분석이 이 데이터에서 의미 있는 구체적인 이유",
      "caution": "초보자가 이 결과를 해석할 때 주의할 점"
    }}
  ]
}}
"""

    logger.info(f"[AI] suggest 요청 시작 (model={model_name})")
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        response = None
        for attempt in range(2):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.2
                    )
                )
                break
            except Exception as e:
                if attempt == 0 and ("503" in str(e) or "UNAVAILABLE" in str(e)):
                    logger.warning("[AI] Gemini 503 일시적 지연 감지, 1.5초 후 재시도...")
                    time.sleep(1.5)
                    continue
                raise e
        logger.info("[AI] suggest 응답 수신 완료")
    except Exception as ex:
        logger.exception(f"[ERROR] Gemini API 호출 실패: {ex}")
        rec_period = current_dataset.get("diagnostics", {}).get("recommended_reference_period") or "2024"
        fallback_suggestions = [
            {
                "tool": "quality_report",
                "recommended_reference_period": None,
                "reason": "대규모 국가별 시계열 데이터셋이므로 결측치와 중복 현황을 먼저 점검하는 것을 권장합니다."
            },
            {
                "tool": "detect_aggregates",
                "recommended_reference_period": None,
                "reason": "데이터셋 내 대륙 및 경제권 집계 그룹 후보를 사전에 식별하여 통계 왜곡을 방지합니다."
            },
            {
                "tool": "top_bottom_n",
                "recommended_reference_period": rec_period,
                "reason": f"권장 기준연도인 {rec_period}년을 기준으로 글로벌 상하위 순위 분포를 명확히 파악합니다."
            },
            {
                "tool": "compare_one_vs_all",
                "recommended_reference_period": rec_period,
                "reason": f"대한민국의 {rec_period}년 수치를 글로벌 평균 및 중앙값과 직관적으로 비교 벤치마킹합니다."
            }
        ]
        return jsonify({
            "status": "success",
            "suggestions": fallback_suggestions,
            "count": len(fallback_suggestions)
        }), 200

    # 응답 JSON 파싱 및 유효성 검증
    try:
        raw_text = response.text.strip()
        # 마크다운 코드블록 제거 보정
        if raw_text.startswith("```"):
            raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
            raw_text = re.sub(r"\s*```$", "", raw_text)
        parsed = json.loads(raw_text)
        if isinstance(parsed, list):
            raw_suggestions = parsed
        elif isinstance(parsed, dict):
            raw_suggestions = parsed.get("suggestions", [])
        else:
            raw_suggestions = []
    except Exception as parse_err:
        logger.error(f"[ERROR] JSON 파싱 실패: {parse_err}, 원본 응답: {response.text[:200]}")
        return jsonify({"error": "AI가 반환한 제안을 JSON으로 파싱하지 못했습니다."}), 500

    # 카탈로그 엄격 검증 필터링
    valid_suggestions = []
    for item in raw_suggestions:
        tool_name = item.get("tool")
        if tool_name in ALLOWED_TOOL_NAMES:
            params = item.get("params", {})
            # 7~12번 도구 기준시점 누락 시 보정
            if tool_name in {"describe_numeric", "top_bottom_n", "group_summary", "change_rate", "distribution", "correlation_scatter", "compare_one_vs_all"}:
                if not params.get("reference_period"):
                    params["reference_period"] = rec_year
                item["reference_period"] = params["reference_period"]
            item["params"] = params
            valid_suggestions.append(item)

    # 최소 3개 미만인 경우 기본 필수 분석 보충
    if len(valid_suggestions) < 3:
        defaults = [
            {
                "tool": "top_bottom_n",
                "params": {"reference_period": rec_year, "n": 10, "exclude_aggregates": True},
                "reference_period": rec_year,
                "why": f"{rec_year}년 기준 인터넷 보급률 최상위 및 최하위 국가들의 서열과 격차를 공정하게 비교합니다.",
                "caution": "동일 시점의 수치만 사용하여 시점 차이에 따른 왜곡을 방지했습니다."
            },
            {
                "tool": "compare_one_vs_all",
                "params": {"reference_period": rec_year, "exclude_aggregates": True},
                "reference_period": rec_year,
                "why": f"대한민국의 보급률 위치를 전 세계 평균 및 중앙값과 1:1로 벤치마킹합니다.",
                "caution": "평균값 외에 중앙값과의 격차를 함께 살펴 상대적 위상을 정확히 파악해야 합니다."
            },
            {
                "tool": "trend_line",
                "params": {"label_column": "Country Name"},
                "reference_period": f"1960 - {rec_year}",
                "why": "대한민국 및 주요국들의 장기 시계열 변화 궤적을 비교합니다.",
                "caution": "과거 특정 연도의 조사 방식 변화 여부를 고려해야 합니다."
            }
        ]
        existing_tools = {s["tool"] for s in valid_suggestions}
        for d in defaults:
            if d["tool"] not in existing_tools and len(valid_suggestions) < 5:
                valid_suggestions.append(d)

    # 최대 5개로 제한
    valid_suggestions = valid_suggestions[:5]
    logger.info(f"[AI] suggest JSON 파싱 완료 (유효 제안 수: {len(valid_suggestions)})")
    logger.info(f"[RESPONSE] status=200 path=/suggest suggestions={len(valid_suggestions)}")

    return jsonify({
        "status": "success",
        "suggestions": valid_suggestions
    }), 200


@app.route("/run", methods=["POST"])
def run_analysis():
    """
    선택된 분석 도구를 Pandas로 실제 실행하고, 계산 결과와 Chart.js 호환 데이터를 반환합니다.
    (규칙: 계산은 반드시 Pandas가 수행, 기준시점 필수 검증, 제외 행 수/이유 반환)
    """
    if current_dataset["df"] is None:
        msg = "분석할 데이터셋이 없습니다. 먼저 CSV 파일을 업로드해 주세요."
        logger.warning(f"[ERROR] {msg}")
        return jsonify({"error": msg}), 400

    data = request.get_json(silent=True) or {}
    tool_name = data.get("tool")
    params = data.get("params", {})

    if not tool_name:
        msg = "실행할 도구(tool)를 지정해야 합니다."
        logger.warning(f"[ERROR] {msg}")
        return jsonify({"error": msg}), 400

    if tool_name not in ALLOWED_TOOL_NAMES:
        msg = f"도구 카탈로그에 존재하지 않는 도구입니다: '{tool_name}'"
        logger.warning(f"[ERROR] {msg}")
        return jsonify({"error": msg}), 400

    # 7~12번 도구 기준시점(reference_period) 필수 검증
    requires_reference_period = {
        "describe_numeric", "top_bottom_n", "group_summary",
        "change_rate", "distribution", "correlation_scatter", "compare_one_vs_all"
    }
    if tool_name in requires_reference_period:
        ref_period = params.get("reference_period") or data.get("reference_period")
        if not ref_period or str(ref_period).strip() == "":
            msg = f"선택한 도구 '{tool_name}'은(는) 기준 시점(reference_period) 입력이 필수입니다."
            logger.warning(f"[ERROR] {msg}")
            return jsonify({"error": msg}), 400
        params["reference_period"] = str(ref_period).strip()

    df = current_dataset["df"]

    # 도구 함수 조회 및 실행
    tool_func = getattr(tools, tool_name, None)
    if not tool_func:
        msg = f"도구 실행 함수를 찾을 수 없습니다: tools.{tool_name}"
        logger.error(f"[ERROR] {msg}")
        return jsonify({"error": msg}), 500

    try:
        import inspect
        sig = inspect.signature(tool_func)
        has_var_kw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
        call_params = params if has_var_kw else {k: v for k, v in params.items() if k in sig.parameters}
        raw_result = tool_func(df, **call_params)
        result = sanitize_for_json(raw_result)
    except ValueError as ve:
        logger.warning(f"[ERROR] 도구 실행 실패 ({tool_name}): {ve}")
        return jsonify({"error": str(ve)}), 400
    except Exception as ex:
        logger.exception(f"[ERROR] 도구 실행 중 예상치 못한 오류 ({tool_name}): {ex}")
        return jsonify({"error": f"분석 실행 중 오류가 발생했습니다: {str(ex)}"}), 500

    # 최근 실행 결과 메모리에 보관 (/explain 에서 사용 가능)
    user_query = data.get("user_query")
    if user_query:
        result["user_query"] = user_query
        current_dataset["last_query"] = user_query
    elif current_dataset.get("last_query") and result.get("tool") == (current_dataset.get("last_run_result") or {}).get("tool"):
        result["user_query"] = current_dataset.get("last_query")
    current_dataset["last_run_result"] = result

    used_rows = result.get("used_rows_count", 0)
    excluded_rows = result.get("excluded_rows_count", 0)
    logger.info(f"[TOOL] name={tool_name}, params={params}, used_rows={used_rows}, excluded_rows={excluded_rows}")
    logger.info(f"[RESPONSE] status=200 path=/run tool={tool_name}")

    return jsonify({
        "status": "success",
        "result": result
    }), 200


@app.route("/explain", methods=["POST"])
def explain_analysis():
    """
    Pandas 분석 결과를 Gemini에 전달하여 해석 보고서를 생성합니다. (Prompt A/B 모드 지원)
    - 사용자가 앞선 자연어 질의(/ask)를 통해 질문한 경우, 해당 질문 의도에 직접적으로 답하는 맞춤형 보고서 작성
    - 모드 A (비교용, 의도적으로 허술하게): 진단 요약만 주고 일반 보고서 요청 (Pandas 계산 결과 미제공)
    - 모드 B (정식): Pandas 계산 결과만을 엄격한 8대 규칙에 따라 해석 (7개 필수 마크다운 섹션 출력)
    """
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key or api_key == "your_gemini_api_key_here":
        msg = "GEMINI_API_KEY가 설정되지 않았습니다. .env 파일에 유효한 API Key를 입력해 주세요."
        logger.warning(f"[ERROR] {msg}")
        return jsonify({"error": msg}), 400

    data = request.get_json(silent=True) or {}
    mode = str(data.get("mode", "B")).strip().upper()
    if mode not in {"A", "B"}:
        mode = "B"

    run_result = data.get("run_result") or current_dataset.get("last_run_result")
    user_query = data.get("user_query") or (run_result.get("user_query") if isinstance(run_result, dict) else None) or current_dataset.get("last_query")
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    # 메타데이터 출처 및 정의 로드 시도
    indicator_info = {
        "name": "Individuals using the Internet (% of population)",
        "definition": "지난 3개월 동안 어느 기기(스마트폰, 컴퓨터 등)로든 인터넷을 사용한 사람의 비율",
        "source": "세계은행(World Bank) / 국제전기통신연합(ITU) 세계 전기통신/ICT 지표 데이터베이스 (https://datahub.itu.int/)"
    }
    try:
        import glob
        meta_ind_files = glob.glob(os.path.join("data", "**", "Metadata_Indicator*.csv"), recursive=True)
        if meta_ind_files:
            m_df = pd.read_csv(meta_ind_files[0], encoding="utf-8-sig")
            if "INDICATOR_NAME" in m_df.columns:
                indicator_info["name"] = str(m_df["INDICATOR_NAME"].iloc[0])
            if "SOURCE_NOTE" in m_df.columns:
                indicator_info["definition"] = str(m_df["SOURCE_NOTE"].iloc[0])
            if "SOURCE_ORGANIZATION" in m_df.columns:
                indicator_info["source"] = str(m_df["SOURCE_ORGANIZATION"].iloc[0])
    except Exception:
        pass

    logger.info(f"[REQUEST] POST /explain (mode={mode}, user_query={user_query})")

    if mode == "A":
        # 모드 A (비교용, 의도적으로 허술하게): 진단 요약만 제공, 계산 결과 미제공
        diag_summary = {
            "filename": current_dataset.get("filename", "업로드 데이터"),
            "row_count": len(current_dataset["df"]) if current_dataset["df"] is not None else 0,
            "col_count": len(current_dataset["df"].columns) if current_dataset["df"] is not None else 0,
            "recommended_reference_period": current_dataset.get("recommended_reference_period", "2024")
        }
        query_context_a = ""
        if user_query:
            query_context_a = f"""
[사용자 핵심 질문]: "{user_query}"
위 사용자 질문에 답하는 형식으로 보고서를 작성해주세요.
"""
        prompt = f"""당신은 AI 어시스턴트입니다.
다음 데이터셋 요약 정보{('와 사용자 질문' if user_query else '')}를 바탕으로 데이터 분석 보고서를 작성해주세요:
{json.dumps(diag_summary, ensure_ascii=False, indent=2)}
{query_context_a}
[가독성 및 서식 규칙]
- 문단과 문단 사이에 빈 줄(줄바꿈 2번)을 넉넉히 넣어 띄어쓰기를 시원하게 해주세요.
- 긴 줄글을 피하고, 2~3줄 단위로 문단을 나누거나 글머리 기호(- )를 활용해 일목요연하게 작성하세요.
- 주요 키워드는 **굵은 글씨**로 강조하세요.

이 데이터로 알 수 있는 것과 보고서를 자유롭게 작성해주세요.
"""
    else:
        # 모드 B (정식): Pandas 계산 결과만을 바탕으로 엄격한 8대 규칙 적용
        if not run_result:
            msg = "분석 실행 결과가 없습니다. 먼저 분석 도구를 실행(/run)해 주세요."
            logger.warning(f"[ERROR] {msg}")
            return jsonify({"error": msg}), 400

        # 계산 결과에서 Chart.js 데이터 등 무거운 필드는 제외하고 통계 표/수치만 정리
        calc_summary = {
            "tool": run_result.get("tool"),
            "reference_period": run_result.get("reference_period"),
            "used_rows_count": run_result.get("used_rows_count"),
            "excluded_rows_count": run_result.get("excluded_rows_count"),
            "exclusion_reason": run_result.get("exclusion_reason"),
            "used_columns": run_result.get("used_columns"),
            "unit": run_result.get("unit"),
            "caution": run_result.get("caution"),
            "data": run_result.get("data")
        }

        query_context_b = ""
        if user_query:
            query_context_b = f"""
[사용자의 질문 및 핵심 분석 목적 (최우선 반영)]
사용자가 다음 구체적인 질문에 답을 얻기 위해 이 분석 보고서 작성을 요청했습니다:
👉 "{user_query}"

[질문 맞춤형 작성 필수 가이드라인]
1. 보고서 전체의 초점은 사용자의 위 질문("{user_query}")에 대한 직접적이고 명쾌한 해답을 제시하는 것입니다.
2. '## 무엇을 봤는가' 섹션의 첫머리에서 사용자가 질문한 내용("{user_query}")을 명확히 언급하며, 이에 답하기 위해 어떤 지표와 분석 도구를 적용했는지 설명하세요.
3. '## 계산 결과' 및 '## 읽어낼 수 있는 것' 섹션에서는 단순히 수치를 나열하지 말고, 사용자의 질문에 대한 구체적인 결론과 통계적 사실(예: 질문에서 언급된 국가들의 순위, 한국과의 차이 등)을 가장 먼저 집중적으로 서술하세요.
"""

        prompt = f"""당신은 교육용 데이터 분석 웹앱의 수석 데이터 분석가입니다.
아래에 제공된 [Pandas 계산 결과]와 [메타데이터]만을 철저히 바탕으로 정식 데이터 해석 보고서를 작성해주세요.
{query_context_b}
[엄격한 8대 해석 준수 규칙]
1. 제공된 계산 결과에 있는 숫자만 사용하세요.
2. 직접 계산하거나 추측/추정하지 마세요.
3. 계산 결과 데이터에 없는 국가, 연도, 열을 임의로 언급하지 마세요.
4. 기준 시점과 제외된 행 수, 제외 사유를 본문에 반드시 명시하세요.
5. 상관관계를 인과관계로 표현하지 마세요 (A가 B의 원인이라고 단정 금지).
6. 지표의 정의와 출처를 보고서 앞부분(출처와 정의 섹션)에 명확히 표기하세요.
7. 확인할 수 없거나 데이터에 없는 것은 반드시 "이 데이터로는 확인할 수 없다"라고 쓰세요.
8. 중학생도 쉽게 이해할 수 있는 평이하고 친절한 문장으로 쓰되, 데이터의 엄밀함과 정확성을 절대 희생하지 마세요.

[가독성 및 띄어쓰기 서식 규칙 (필수 준수)]
- **문단 간 넉넉한 띄어쓰기**: 문단과 문단 사이, 소항목 사이에는 반드시 **빈 줄(두 번 엔터)**을 넣어 글이 빽빽하게 뭉치지 않게 하세요.
- **짧고 편안한 호흡**: 긴 장문 대신 2~3문장 단위로 문단을 분리하여 호흡을 편안하게 만드세요.
- **글머리 기호(- ) 적극 활용**: 계산 결과 수치나 나열할 항목은 줄글로 붙여 쓰지 말고 글머리 기호(- ) 목록으로 보기 쉽게 정리하세요.
- **핵심 수치 굵게 강조**: 주요 국가명, 순위, 수치(예: **1위 United Arab Emirates (100.0%)**, **대한민국 13위 (97.90%)**)는 **굵은 글씨**로 강조하세요.
- **쉬운 설명 덧붙이기**: 어려운 통계 용어는 중학생 눈높이에 맞추어 쉬운 비유와 친절한 설명을 덧붙이세요.

[지표 메타데이터 및 출처]
- 지표명: {indicator_info['name']}
- 공식 정의: {indicator_info['definition']}
- 출처 기관: {indicator_info['source']}

[Pandas 실제 계산 결과]
{json.dumps(calc_summary, ensure_ascii=False, indent=2)}

[필수 마크다운 출력 형식]
아래 7개 섹션 헤더를 한 자도 틀리지 말고 그대로 사용하여 작성하세요:

## 무엇을 봤는가
## 데이터 출처와 정의
## 기준 시점과 제외된 항목
## 계산 결과
## 읽어낼 수 있는 것
## 이 데이터로는 알 수 없는 것
## 다음에 확인해볼 것
"""

    logger.info(f"[AI] explain 요청 시작 (모드={mode}, model={model_name})")
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model_name,
            contents=prompt
        )
        explanation_text = response.text.strip()
        current_dataset["last_explanation"] = explanation_text
        logger.info("[AI] explain 응답 수신 완료")
    except Exception as ex:
        logger.exception(f"[ERROR] Gemini explain 호출 실패: {ex}")
        return jsonify({"error": f"Gemini 해석 호출 중 오류가 발생했습니다: {str(ex)}"}), 502

    logger.info(f"[RESPONSE] status=200 path=/explain mode={mode}")
    return jsonify({
        "status": "success",
        "mode": mode,
        "explanation": explanation_text,
        "user_query": user_query
    }), 200


@app.route("/chat", methods=["POST"])
def chat_followup():
    """
    분석 보고서에 대한 후속 질의응답 (Q&A 대화형 어시스턴트)
    - 중학생도 이해할 수 있는 쉬운 설명 지원
    - 계산 결과 맥락 유지
    - 다음 후속 질문 추천 목록(말풍선 칩) 함께 반환
    """
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key or api_key == "your_gemini_api_key_here":
        msg = "GEMINI_API_KEY가 설정되지 않았습니다."
        logger.warning(f"[ERROR] {msg}")
        return jsonify({"error": msg}), 400

    data = request.get_json(silent=True) or {}
    user_message = data.get("message", "").strip()
    if not user_message:
        return jsonify({"error": "질문 내용을 입력해주세요."}), 400

    history = data.get("history", [])
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    last_run = current_dataset.get("last_run_result") or {}
    tool_name = last_run.get("tool", "알 수 없음")
    ref_period = last_run.get("reference_period", "전체")
    calc_data = last_run.get("data", {})
    last_explanation = current_dataset.get("last_explanation", "")

    # 대화 이력 텍스트 변환
    history_text = ""
    for item in history[-6:]:
        role_label = "사용자" if item.get("role") == "user" else "AI 어시스턴트"
        history_text += f"{role_label}: {item.get('content', '')}\n"

    prompt = f"""당신은 친절하고 뛰어난 데이터 분석 교육 전문 AI 튜터입니다.
사용자가 방금 수행한 데이터 분석 결과 및 보고서에 대해 대화형으로 후속 질문을 하고 있습니다.

[분석 맥락 정보]
- 파일명: {current_dataset.get('filename', '업로드 데이터')}
- 실행된 분석 도구: {tool_name}
- 기준 시점: {ref_period}
- Pandas 실제 계산 요약: {json.dumps(calc_data, ensure_ascii=False, default=str)[:1500]}
- 기존 AI 보고서 내용:
{last_explanation[:1500]}

[이전 대화 이력]
{history_text}

[사용자의 이번 질문]
{user_message}

[답변 가이드라인]
1. 사용자의 질문에 직접적이고 명쾌하게 답변하세요.
2. 만약 질문이 "쉽게 설명해줘"나 "중학생도 이해할 수 있게 설명해줘" 또는 초보자 눈높이를 요구하는 경우:
   - 복잡한 통계 용어 대신 친숙한 일상 비유(예: 학교 학급 30명 중 스마트폰 가진 학생 수, 용돈 차이, 키 순서 서기 등)를 적극 사용하세요.
   - 핵심 메시지가 한눈에 들어오도록 2~3개의 짧은 핵심 문장과 친근한 어조로 설명하세요.
3. 데이터에 없는 허구의 수치를 사실인 양 지어내지 마세요.
4. 답변 본문 작성이 끝난 후, 맨 마지막 줄에 사용자가 클릭해서 물어볼 만한 다음 후속 질문 3개를 아래 JSON 코드블록 형식으로 반드시 출력하세요:
```json
{{
  "suggested_questions": [
    "질문 1",
    "질문 2",
    "질문 3"
  ]
}}
```
"""

    logger.info(f"[REQUEST] POST /chat (question={user_message[:30]}...)")
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model_name,
            contents=prompt
        )
        reply_full = response.text.strip()
        logger.info("[AI] chat 응답 수신 완료")
    except Exception as ex:
        logger.exception(f"[ERROR] Gemini chat 호출 실패: {ex}")
        return jsonify({"error": f"AI 답변 생성 중 오류가 발생했습니다: {str(ex)}"}), 502

    # 본문과 추천 질문 분리
    suggested_questions = []
    reply_text = reply_full

    json_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", reply_full)
    if json_match:
        try:
            parsed = json.loads(json_match.group(1))
            suggested_questions = parsed.get("suggested_questions", [])
            reply_text = reply_full[:json_match.start()].strip()
        except Exception:
            pass

    if not suggested_questions:
        suggested_questions = [
            "중학생도 이해할 수 있게 쉽게 설명해줘.",
            "이 수치에서 초보자가 주의해야 할 점은 뭐야?",
            "대한민국의 순위와 수치는 다른 나라와 비교해 어떤 의미야?"
        ]

    logger.info(f"[RESPONSE] status=200 path=/chat suggestions={len(suggested_questions)}")
    return jsonify({
        "status": "success",
        "reply": reply_text,
        "suggested_questions": suggested_questions
    }), 200


if __name__ == "__main__":
    debug_mode = os.getenv("FLASK_DEBUG", "true").lower() == "true"
    port = int(os.getenv("PORT", 5000))
    host = os.getenv("HOST", "0.0.0.0")
    logger.info(f"[START] Flask 서버 시작 (Host: {host}, Port: {port}, Debug: {debug_mode})")
    app.run(host=host, port=port, debug=debug_mode)



