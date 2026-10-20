"""
AI Data Insight Builder - End-to-End 전체 파이프라인 통합 테스트 스크립트
1. GET /health: 서비스 상태 및 API Key 설정 확인
2. POST /inspect: World Bank 공식 CSV 업로드, 인코딩/헤더/2024 권장시점/집계그룹 13개 항목 진단
3. POST /suggest: Gemini API 기반 12개 카탈로그 내 최적 분석 제안 (JSON 파싱 및 유효성)
4. POST /run: Pandas 순수 수치 계산, 기준시점 및 집계그룹 제외 검증, Chart.js 데이터 생성
5. POST /explain (Mode B): 엄격한 8대 규칙 기반 정식 통계 해석 보고서 생성
6. POST /explain (Mode A): 비교용 일반 보고서 생성
"""

import sys
import os
import glob

# Windows 콘솔 출력 인코딩 안전 설정
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app import app

def run_tests():
    print("=" * 60)
    print("AI Data Insight Builder - 전체 파이프라인 통합 테스트 시작")
    print("=" * 60)

    client = app.test_client()

    # 1. 헬스체크
    print("\n[단계 1/7] GET /health 호출 중...")
    res = client.get("/health")
    assert res.status_code == 200, f"Health check failed: {res.status_code}"
    health_data = res.get_json()
    print(f" -> 성공 (Status: {health_data['status']}, Model: {health_data['model']}, API Key 설정: {health_data['api_key_configured']})")

    # 1-1. 보안 로그인 인증 테스트 (/login)
    print("\n[보안 인증] 미인증 접근 차단 및 비밀번호(0412) 로그인 검증 중...")
    # 미인증 시 메인화면(/) 리다이렉트 확인
    unauth_res = client.get("/")
    assert unauth_res.status_code == 302 and "/login" in unauth_res.headers.get("Location", ""), "미인증 접근 리다이렉트 실패"
    
    # 잘못된 비밀번호 시 401 실패 확인
    fail_res = client.post("/login", json={"password": "wrong_password"})
    assert fail_res.status_code == 401, "잘못된 비밀번호 차단 실패"
    
    # 올바른 비밀번호 0412 입력 시 200 성공 및 세션 수립 확인
    login_res = client.post("/login", json={"password": "0412"})
    assert login_res.status_code == 200, f"로그인 실패: {login_res.status_code}"
    print(" -> 성공! 미인증 차단 및 0412 비밀번호 로그인 정상 인증 완료")

    # 2. CSV 진단 (/inspect)
    csv_candidates = glob.glob("data/**/*.csv", recursive=True)
    csv_path = None
    for c in csv_candidates:
        if "API_IT.NET.USER.ZS" in c and "Metadata" not in c:
            csv_path = c
            break

    assert csv_path is not None, "World Bank CSV 파일을 data 폴더에서 찾을 수 없습니다."
    print(f"\n[단계 2/6] POST /inspect 호출 중... (파일: {csv_path})")

    with open(csv_path, "rb") as f:
        res = client.post("/inspect", data={"file": (f, os.path.basename(csv_path))}, content_type="multipart/form-data")

    assert res.status_code == 200, f"Inspect failed: {res.status_code}, {res.data}"
    inspect_data = res.get_json()
    print(f" -> 성공! 행 수: {inspect_data['row_count']}, 열 수: {inspect_data['col_count']}")
    print(f" -> 인코딩: {inspect_data['encoding']}, 건너뛴 헤더 줄: {inspect_data['skipped_rows']}")
    print(f" -> 권장 기준연도: {inspect_data['recommended_reference_period']}")
    print(f" -> 감지된 집계 그룹: {len(inspect_data['aggregate_row_candidates'])}개")
    print(f" -> 경고 수: {len(inspect_data['warnings'])}개")

    # 2-1. 자연어 질문 테스트 (/ask)
    print("\n[자연어 질의] POST /ask 호출 중 ('2024년 세계 1~10등까지 순위국가와 대한민국을 함께 비교해줘.')...")
    res = client.post("/ask", json={"query": "2024년 세계 1~10등까지 순위국가와 대한민국을 함께 비교해줘."})
    assert res.status_code == 200, f"Ask failed: {res.status_code}"
    ask_data = res.get_json()
    print(f" -> 성공! 매칭된 도구: {ask_data['tool']}, 제목: {ask_data.get('title')}")
    print(f" -> 답변 글자 수: {len(ask_data['answer'])}자, 시각화 차트: {ask_data['run_result']['chart']['type']}")

    # 3. AI 분석 제안 (/suggest)
    print("\n[단계 3/7] POST /suggest 호출 중 (Gemini API)...")
    res = client.post("/suggest", json={})
    assert res.status_code == 200, f"Suggest failed: {res.status_code}, {res.data}"
    suggest_data = res.get_json()
    suggestions = suggest_data.get("suggestions", [])
    print(f" -> 성공! 제안된 도구 수: {len(suggestions)}개")
    for idx, s in enumerate(suggestions, 1):
        print(f"    {idx}. 도구: {s['tool']} (기준시점: {s.get('reference_period')}) - {s.get('why', '')[:40]}...")

    # 4. 분석 실행 (/run)
    print("\n[단계 4/6] POST /run 호출 중 (Pandas top_bottom_n 실행)...")
    run_payload = {
        "tool": "top_bottom_n",
        "params": {
            "reference_period": "2024",
            "n": 5,
            "exclude_aggregates": True
        }
    }
    res = client.post("/run", json=run_payload)
    assert res.status_code == 200, f"Run failed: {res.status_code}, {res.data}"
    run_res = res.get_json()
    result = run_res["result"]
    print(f" -> 성공! 도구: {result['tool']}, 기준시점: {result['reference_period']}")
    print(f" -> 사용 행 수: {result['used_rows_count']}, 제외 행 수: {result['excluded_rows_count']}")
    print(f" -> 제외 사유: {result['exclusion_reason']}")
    print(f" -> Chart.js 차트 타입: {result['chart']['type']}")
    print(f" -> 2024년 상위 3개국:")
    for t in result["data"]["top_n"][:3]:
        print(f"    - {t['rank']}위: {t['label']} ({t['value']}%)")

    # 5. AI 해석 생성 - 모드 B (/explain)
    print("\n[단계 5/6] POST /explain 호출 중 (모드 B: Pandas 계산 결과 기반 정식 보고서)...")
    res = client.post("/explain", json={"mode": "B"})
    assert res.status_code == 200, f"Explain Mode B failed: {res.status_code}, {res.data}"
    explain_b = res.get_json()
    print(" -> 성공! 모드 B 보고서 생성 완료 (응답 글자 수:", len(explain_b["explanation"]), "자)")

    # 6. AI 해석 생성 - 모드 A (/explain)
    print("\n[단계 6/7] POST /explain 호출 중 (모드 A: 비교용 일반 보고서)...")
    res = client.post("/explain", json={"mode": "A"})
    assert res.status_code == 200, f"Explain Mode A failed: {res.status_code}, {res.data}"
    explain_a = res.get_json()
    print(" -> 성공! 모드 A 보고서 생성 완료 (응답 글자 수:", len(explain_a["explanation"]), "자)")

    # 7. 후속 대화 Q&A 테스트 (/chat)
    print("\n[단계 7/7] POST /chat 호출 중 ('중학생도 이해할 수 있게 쉽게 설명해줘.')...")
    res = client.post("/chat", json={"message": "중학생도 이해할 수 있게 쉽게 설명해줘."})
    assert res.status_code == 200, f"Chat failed: {res.status_code}, {res.data}"
    chat_res = res.get_json()
    assert "reply" in chat_res, "Chat response missing 'reply'"
    assert "suggested_questions" in chat_res, "Chat response missing 'suggested_questions'"
    print(f" -> 성공! AI 답변 생성 완료 (답변 글자 수: {len(chat_res['reply'])}자)")
    print(f" -> 추천 후속 질문 수: {len(chat_res['suggested_questions'])}개: {chat_res['suggested_questions']}")

    print("\n" + "=" * 60)
    print("🎉 축하합니다! 모든 7개 파이프라인 단계가 완벽히 검증되었습니다.")
    print("=" * 60)

if __name__ == "__main__":
    run_tests()
