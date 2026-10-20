"""
tools.py - AI Data Insight Builder 분석 도구 카탈로그

규칙:
1. 숫자 계산은 반드시 Pandas가 수행합니다. (Gemini에게 계산 위임 금지)
2. 모든 도구는 계산 결과와 함께 기준시점, 사용한 행 수, 제외한 행 수와 이유, 사용한 열, 단위, 주의사항을 반환합니다.
3. NaN과 Infinity는 JSON 직렬화가 가능하도록 안전하게 처리(None/null)합니다.
4. Step 14: 도구 1~4 구현 (reshape_wide_to_long, quality_report, year_coverage, detect_aggregates)
"""

import math
import re
import numpy as np
import pandas as pd

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
        return round(obj, 4)
    elif isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_for_json(x) for x in obj]
    elif pd.isna(obj):
        return None
    return obj


def detect_year_columns(df):
    """4자리 연도(1900~2099) 형태의 열 이름을 탐색합니다."""
    return [str(c) for c in df.columns if re.match(r"^(19|20)\d{2}$", str(c))]


def is_aggregate_label(label):
    """주어진 문자열 라벨이 대륙/경제권 등 집계 그룹 명칭인지 판별합니다."""
    s = str(label).lower()
    return any(kw in s for kw in AGG_KEYWORDS)


def get_first_label_column(df):
    """국가명/항목명으로 쓰일 만한 첫 번째 문자열 열을 탐색합니다."""
    str_cols = df.select_dtypes(include=["object", "string"]).columns
    if len(str_cols) > 0:
        return str_cols[0]
    return df.columns[0]


def filter_aggregates(df, label_col=None, exclude_aggregates=True):
    """
    집계 행 제외 여부에 따라 DataFrame을 필터링하고 제외된 행 수와 이유를 반환합니다.
    """
    if label_col is None:
        label_col = get_first_label_column(df)

    if not exclude_aggregates or label_col not in df.columns:
        return df, 0, None

    agg_mask = df[label_col].apply(is_aggregate_label)
    excluded_count = int(agg_mask.sum())
    filtered_df = df[~agg_mask].copy()

    reason = f"대륙/경제권 등 집계 그룹 행 {excluded_count}개 제외" if excluded_count > 0 else None
    return filtered_df, excluded_count, reason


# ==============================================================================
# 도구 1. reshape_wide_to_long (연도 열을 행으로 접기)
# ==============================================================================
def reshape_wide_to_long(df, id_columns=None, value_name="value", var_name="year", exclude_aggregates=True, **kwargs):
    """
    가로로 펼쳐진 연도 열들을 행으로 접어 분석과 시각화에 적합한 표준 Long Format(Tidy Data)으로 변환합니다.
    """
    year_cols = detect_year_columns(df)
    if not year_cols:
        raise ValueError("변환할 연도 형식(YYYY)의 열을 찾을 수 없습니다.")

    label_col = get_first_label_column(df)
    filtered_df, excluded_count, exclusion_reason = filter_aggregates(df, label_col, exclude_aggregates)

    if id_columns is None:
        id_columns = [c for c in filtered_df.columns if c not in year_cols and not str(c).startswith("Unnamed:")]

    melted_df = pd.melt(
        filtered_df,
        id_vars=id_columns,
        value_vars=year_cols,
        var_name=var_name,
        value_name=value_name
    )

    # 결측치는 제외하거나 유지 (여기서는 정보 보존 후 정렬)
    melted_df = melted_df.sort_values(by=[label_col, var_name])

    # 상위 50행 미리보기 제공
    preview = sanitize_for_json(melted_df.head(50).to_dict(orient="records"))

    return {
        "tool": "reshape_wide_to_long",
        "reference_period": f"{min(year_cols)} - {max(year_cols)}",
        "used_rows_count": int(len(melted_df)),
        "original_rows_count": int(len(filtered_df)),
        "excluded_rows_count": excluded_count,
        "exclusion_reason": exclusion_reason,
        "used_columns": id_columns + [var_name, value_name],
        "unit": "행 (Tidy Data)",
        "caution": "연도가 열에서 행으로 전환되어 총 행 수가 증가하며, 시계열 분석 및 그룹 집계에 최적화된 형태입니다.",
        "data": {
            "total_melted_rows": int(len(melted_df)),
            "year_range": f"{min(year_cols)} ~ {max(year_cols)}",
            "id_columns": id_columns,
            "preview_50_rows": preview
        },
        "chart": None
    }


# ==============================================================================
# 도구 2. quality_report (결측·중복·타입·이상한 열 이름 진단)
# ==============================================================================
def quality_report(df, **kwargs):
    """
    데이터셋의 전반적인 데이터 품질(결측치, 중복 행, 열 데이터 타입, Unnamed/빈 열)을 종합 진단합니다.
    """
    total_rows = len(df)
    total_cols = len(df.columns)

    missing_by_col = []
    for col in df.columns:
        m_cnt = int(df[col].isna().sum())
        m_pct = round(float(df[col].isna().mean() * 100), 2)
        missing_by_col.append({
            "column": str(col),
            "missing_count": m_cnt,
            "missing_percentage": m_pct,
            "dtype": str(df[col].dtype)
        })

    # 결측률 높은 순으로 정렬
    missing_by_col.sort(key=lambda x: x["missing_percentage"], reverse=True)

    unnamed_cols = [str(c) for c in df.columns if str(c).startswith("Unnamed:") or str(c).strip() == ""]
    empty_cols = [str(c) for c in df.columns if df[c].isna().all()]
    duplicate_rows = int(df.duplicated().sum())

    # Chart.js용 상위 10개 결측 열 막대 차트 데이터
    top_missing = [x for x in missing_by_col[:10] if x["missing_percentage"] > 0]
    chart_data = None
    if top_missing:
        chart_data = {
            "type": "bar",
            "title": "상위 결측치 발생 열 (결측률 %)",
            "labels": [x["column"] for x in top_missing],
            "datasets": [{
                "label": "결측률 (%)",
                "data": [x["missing_percentage"] for x in top_missing],
                "backgroundColor": "rgba(239, 68, 68, 0.7)"
            }]
        }

    return {
        "tool": "quality_report",
        "reference_period": "데이터 전체",
        "used_rows_count": total_rows,
        "excluded_rows_count": 0,
        "exclusion_reason": None,
        "used_columns": [str(c) for c in df.columns],
        "unit": "건 / %",
        "caution": "결측률이 50%를 초과하는 열은 직접적인 단일 통계 비교에서 왜곡을 유발할 수 있으므로 주의가 필요합니다.",
        "data": {
            "total_rows": total_rows,
            "total_cols": total_cols,
            "duplicate_rows_count": duplicate_rows,
            "unnamed_columns": unnamed_cols,
            "empty_columns": empty_cols,
            "columns_quality": missing_by_col
        },
        "chart": chart_data
    }


# ==============================================================================
# 도구 3. year_coverage (연도별 값 개수와 권장 기준연도)
# ==============================================================================
def year_coverage(df, threshold_ratio=0.7, **kwargs):
    """
    모든 연도 열의 유효값 개수(데이터 충실도)를 산출하고, 결측률이 낮으면서 가장 최근인 권장 기준연도를 찾습니다.
    """
    year_cols = detect_year_columns(df)
    if not year_cols:
        raise ValueError("연도 형식(YYYY)의 열을 찾을 수 없습니다.")

    coverage_list = []
    total_rows = len(df)

    for y in year_cols:
        valid_cnt = int(df[y].notna().sum())
        valid_pct = round(float(valid_cnt / total_rows * 100), 2)
        coverage_list.append({
            "year": str(y),
            "valid_count": valid_cnt,
            "valid_percentage": valid_pct
        })

    max_cov = max(x["valid_count"] for x in coverage_list) if coverage_list else 0
    rec_year = None
    sorted_years = sorted(coverage_list, key=lambda x: int(x["year"]), reverse=True)
    for item in sorted_years:
        if item["valid_count"] >= max_cov * threshold_ratio:
            rec_year = item["year"]
            break

    # Chart.js용 연도별 데이터 수집 건수 시계열 차트
    chart_data = {
        "type": "line",
        "title": "연도별 유효 데이터 수집 건수 (충실도)",
        "labels": [x["year"] for x in coverage_list],
        "datasets": [{
            "label": "수집된 데이터 건수",
            "data": [x["valid_count"] for x in coverage_list],
            "borderColor": "rgba(59, 130, 246, 1)",
            "backgroundColor": "rgba(59, 130, 246, 0.1)",
            "fill": True
        }]
    }

    return {
        "tool": "year_coverage",
        "reference_period": rec_year if rec_year else "미정",
        "used_rows_count": total_rows,
        "excluded_rows_count": 0,
        "exclusion_reason": None,
        "used_columns": year_cols,
        "unit": "건 / 개국",
        "caution": f"최신 연도라 하더라도 수집률이 급감하는 연도는 표본 대표성이 훼손되므로, 충실도가 검증된 {rec_year}년 사용을 강력히 권장합니다.",
        "data": {
            "recommended_year": rec_year,
            "max_coverage": max_cov,
            "coverage_by_year": coverage_list
        },
        "chart": chart_data
    }


# ==============================================================================
# 도구 4. detect_aggregates (집계 행 후보 탐지)
# ==============================================================================
def detect_aggregates(df, label_column=None, **kwargs):
    """
    World, OECD members, Income group 등 국가가 아닌 지역·경제권 집계 행 후보를 식별하여 분류합니다.
    """
    if label_column is None:
        label_column = get_first_label_column(df)

    candidates = []
    pure_count = 0

    for idx, val in df[label_column].items():
        s = str(val).lower()
        matched_kw = None
        for kw in AGG_KEYWORDS:
            if kw in s:
                matched_kw = kw
                break

        if matched_kw:
            candidates.append({
                "row_index": int(idx),
                "label": str(val),
                "matched_keyword": matched_kw
            })
        else:
            pure_count += 1

    return {
        "tool": "detect_aggregates",
        "reference_period": "데이터 전체",
        "used_rows_count": int(len(df)),
        "excluded_rows_count": 0,
        "exclusion_reason": None,
        "used_columns": [str(label_column)],
        "unit": "개 (행)",
        "caution": "순위 집계 시 이들 집계 행을 포함하면 국가와 대륙/소득군이 섞여 왜곡된 결과가 나타나므로 반드시 분리·제외해야 합니다.",
        "data": {
            "total_rows": int(len(df)),
            "aggregate_candidates_count": len(candidates),
            "pure_entities_count": pure_count,
            "aggregate_candidates": candidates
        },
        "chart": {
            "type": "doughnut",
            "title": "개별 항목 vs 집계 그룹 비율",
            "labels": ["개별 항목 (국가 등)", "집계 그룹 후보"],
            "datasets": [{
                "data": [pure_count, len(candidates)],
                "backgroundColor": ["rgba(34, 197, 94, 0.7)", "rgba(249, 115, 22, 0.7)"]
            }]
        }
    }


# ==============================================================================
# 도구 5. describe_numeric (개수·평균·중앙값·최소·최대·표준편차)
# ==============================================================================
def describe_numeric(df, column=None, reference_period=None, exclude_aggregates=True, **kwargs):
    """
    지정된 열 또는 기준 시점 열의 핵심 기술통계량(개수, 평균, 중앙값, 최소, 최대, 표준편차, 사분위수)을 계산합니다.
    """
    target_col = column or reference_period
    if not target_col:
        num_cols = df.select_dtypes(include=[np.number]).columns
        if len(num_cols) > 0:
            target_col = num_cols[-1]
        else:
            raise ValueError("분석할 숫자형 열 또는 기준 시점을 지정해야 합니다.")

    target_col = str(target_col)
    if target_col not in df.columns:
        raise ValueError(f"데이터셋에 '{target_col}' 열이 존재하지 않습니다.")

    label_col = get_first_label_column(df)
    filtered_df, agg_excluded, _ = filter_aggregates(df, label_col, exclude_aggregates)

    series = pd.to_numeric(filtered_df[target_col], errors="coerce")
    valid_series = series.dropna()

    nan_excluded = int(len(series) - len(valid_series))
    total_excluded = agg_excluded + nan_excluded

    reasons = []
    if agg_excluded > 0:
        reasons.append(f"집계 그룹 행 {agg_excluded}개 제외")
    if nan_excluded > 0:
        reasons.append(f"결측값 {nan_excluded}개 제외")
    exclusion_reason = ", ".join(reasons) if reasons else None

    if len(valid_series) == 0:
        raise ValueError(f"선택한 열 '{target_col}'에 유효한 수치 데이터가 없습니다.")

    stats = {
        "count": int(valid_series.count()),
        "mean": round(float(valid_series.mean()), 4),
        "median": round(float(valid_series.median()), 4),
        "min": round(float(valid_series.min()), 4),
        "max": round(float(valid_series.max()), 4),
        "std": round(float(valid_series.std()), 4) if len(valid_series) > 1 else 0.0,
        "q25": round(float(valid_series.quantile(0.25)), 4),
        "q75": round(float(valid_series.quantile(0.75)), 4)
    }

    chart_data = {
        "type": "bar",
        "title": f"{target_col} 핵심 기술통계치",
        "labels": ["최소값", "25% (Q1)", "중앙값", "평균값", "75% (Q3)", "최대값"],
        "datasets": [{
            "label": f"수치 ({target_col})",
            "data": [stats["min"], stats["q25"], stats["median"], stats["mean"], stats["q75"], stats["max"]],
            "backgroundColor": "rgba(99, 102, 241, 0.7)"
        }]
    }

    return {
        "tool": "describe_numeric",
        "reference_period": target_col,
        "used_rows_count": int(len(valid_series)),
        "excluded_rows_count": total_excluded,
        "exclusion_reason": exclusion_reason,
        "used_columns": [target_col],
        "unit": "수치 단위 (예: %)",
        "caution": "평균값은 소수의 극단적인 이상치에 의해 왜곡될 수 있으므로, 반드시 중앙값과 사분위수(Q1, Q3)를 함께 검토해야 합니다.",
        "data": stats,
        "chart": chart_data
    }


# ==============================================================================
# 도구 6. trend_line (선택 항목들의 연도별 추이 선 차트)
# ==============================================================================
def trend_line(df, items=None, label_column=None, year_range=None, **kwargs):
    """
    선택한 항목들(예: 한국, 미국 등)의 연도별 시계열 변화 추이를 꺾은선 차트로 도출합니다.
    """
    if label_column is None:
        label_column = get_first_label_column(df)

    year_cols = detect_year_columns(df)
    if not year_cols:
        raise ValueError("시계열 추이를 분석할 연도 형식의 열이 없습니다.")

    if year_range and len(year_range) == 2:
        start_y, end_y = str(year_range[0]), str(year_range[1])
        year_cols = [y for y in year_cols if start_y <= y <= end_y]

    if not items:
        # 기본값: 'Korea' 포함 항목 및 상위 4개 주요 항목 자동 선택
        korea_rows = df[df[label_column].astype(str).str.contains("Korea", case=False, na=False)][label_column].tolist()
        other_rows = df[label_column].head(4).tolist()
        items = list(dict.fromkeys(korea_rows + other_rows))[:5]

    matched_df = df[df[label_column].isin(items)].copy()
    if len(matched_df) == 0:
        raise ValueError("지정된 항목 이름과 일치하는 행을 데이터에서 찾을 수 없습니다.")

    excluded_rows = int(len(df) - len(matched_df))

    color_palette = [
        "rgba(59, 130, 246, 1)", "rgba(239, 68, 68, 1)", "rgba(16, 185, 129, 1)",
        "rgba(245, 158, 11, 1)", "rgba(139, 92, 246, 1)", "rgba(236, 72, 153, 1)"
    ]

    datasets = []
    items_data = {}
    for idx, (_, row) in enumerate(matched_df.iterrows()):
        item_name = str(row[label_column])
        values = [sanitize_for_json(float(row[y])) if pd.notna(row[y]) else None for y in year_cols]
        items_data[item_name] = dict(zip(year_cols, values))

        color = color_palette[idx % len(color_palette)]
        datasets.append({
            "label": item_name,
            "data": values,
            "borderColor": color,
            "backgroundColor": color.replace("1)", "0.1)"),
            "tension": 0.2,
            "fill": False
        })

    chart_data = {
        "type": "line",
        "title": f"항목별 시계열 변화 추이 ({min(year_cols)} ~ {max(year_cols)})",
        "labels": year_cols,
        "datasets": datasets
    }

    return {
        "tool": "trend_line",
        "reference_period": f"{min(year_cols)} - {max(year_cols)}",
        "used_rows_count": int(len(matched_df)),
        "excluded_rows_count": excluded_rows,
        "exclusion_reason": f"비교 대상 외 {excluded_rows}개 항목 제외",
        "used_columns": [label_column] + year_cols,
        "unit": "수치 (예: %)",
        "caution": "시계열 비교 시 과거 특정 연도에 통계 집계 기준이나 조사 대상 연령이 변경되었을 가능성을 염두에 두어야 합니다.",
        "data": {
            "selected_items": items,
            "year_range": f"{min(year_cols)} ~ {max(year_cols)}",
            "series": items_data
        },
        "chart": chart_data
    }


# ==============================================================================
# 도구 7. top_bottom_n (기준연도 기준 상위·하위 N 수평 막대)
# ==============================================================================
def top_bottom_n(df, reference_period, n=10, value_column=None, label_column=None, exclude_aggregates=True, **kwargs):
    """
    기준연도(reference_period) 시점의 수치를 기준으로 상위 N개 및 하위 N개 항목을 추출합니다.
    (규칙: 기준 시점 필수, 기준 시점 결측치 행 제외 및 제외 이유 반환)
    """
    if not reference_period or str(reference_period).strip() == "":
        raise ValueError("기준 시점(reference_period)은 필수 파라미터입니다.")

    ref_col = str(value_column or reference_period)
    if ref_col not in df.columns:
        raise ValueError(f"데이터셋에 기준 시점 열 '{ref_col}'이 존재하지 않습니다.")

    if label_column is None:
        label_column = get_first_label_column(df)

    filtered_df, agg_excluded, _ = filter_aggregates(df, label_col=label_column, exclude_aggregates=exclude_aggregates)

    # 기준 시점에 값이 있는 행만 선별
    valid_mask = pd.to_numeric(filtered_df[ref_col], errors="coerce").notna()
    valid_df = filtered_df[valid_mask].copy()
    valid_df["_numeric_val"] = pd.to_numeric(valid_df[ref_col])

    nan_excluded = int(len(filtered_df) - len(valid_df))
    total_excluded = agg_excluded + nan_excluded

    reasons = []
    if agg_excluded > 0:
        reasons.append(f"집계 그룹 행 {agg_excluded}개 제외")
    if nan_excluded > 0:
        reasons.append(f"{reference_period}년 결측치 행 {nan_excluded}개 제외")
    exclusion_reason = ", ".join(reasons) if reasons else None

    # 내림차순 정렬 및 순위 부여
    sorted_df = valid_df.sort_values(by="_numeric_val", ascending=False).reset_index(drop=True)

    top_df = sorted_df.head(n)
    bottom_df = sorted_df.tail(n).iloc[::-1]

    # 대한민국(한국) 탐지
    korea_mask = (
        sorted_df[label_column].astype(str).str.contains(r"Korea,\s*Rep\.", case=False, na=False) |
        sorted_df[label_column].astype(str).str.contains(r"South\s*Korea", case=False, na=False) |
        sorted_df[label_column].astype(str).str.contains(r"대한민국|한국", case=False, na=False)
    )
    if not korea_mask.any():
        korea_mask = (
            sorted_df[label_column].astype(str).str.contains("Korea", case=False, na=False) &
            ~sorted_df[label_column].astype(str).str.contains("Dem", case=False, na=False)
        )

    korea_item = None
    if korea_mask.any():
        k_idx = int(sorted_df[korea_mask].index[0])
        k_row = sorted_df.iloc[k_idx]
        korea_item = {
            "rank": k_idx + 1,
            "label": str(k_row[label_column]),
            "value": round(float(k_row["_numeric_val"]), 4),
            "is_korea": True
        }

    top_list = []
    for i, (_, r) in enumerate(top_df.iterrows()):
        is_kor = bool(korea_item and (i + 1) == korea_item["rank"])
        top_list.append({
            "rank": i + 1,
            "label": str(r[label_column]),
            "value": round(float(r["_numeric_val"]), 4),
            "is_korea": is_kor
        })

    bottom_list = [
        {"rank": len(sorted_df) - i, "label": str(r[label_column]), "value": round(float(r["_numeric_val"]), 4)}
        for i, (_, r) in enumerate(bottom_df.iterrows())
    ]

    # 차트 및 테이블 비교 목록 구성 (상위 N개국 + 대한민국이 상위 N개국 밖에 있으면 함께 포함)
    korea_in_top_n = any(item.get("is_korea") for item in top_list)
    chart_items = list(top_list)
    if korea_item and not korea_in_top_n:
        chart_items.append(korea_item)
        chart_title = f"{reference_period}년 상위 {n}개 항목 및 대한민국({korea_item['rank']}위) 순위 비교"
        caution_text = f"동일한 시점({reference_period}년)의 단일 기준 데이터로 비교 왜곡을 방지하였으며, 대한민국({korea_item['rank']}위, {korea_item['value']}%)의 위치를 함께 비교할 수 있도록 붉은색 막대로 강조 표시했습니다."
    else:
        chart_title = f"{reference_period}년 상위 {n}개 항목 순위 비교"
        caution_text = f"동일한 시점({reference_period}년)의 단일 기준 데이터만 사용하여 과거/미래 연도가 뒤섞이는 비교 왜곡을 원천 방지했습니다."

    chart_labels = []
    chart_values = []
    chart_bg_colors = []
    chart_border_colors = []

    for item in chart_items:
        val = item["value"]
        rank = item["rank"]
        label = item["label"]
        is_kor = item.get("is_korea", False)

        if is_kor:
            chart_labels.append(f"{label} (대한민국 - {rank}위)")
            chart_values.append(val)
            chart_bg_colors.append("rgba(239, 68, 68, 0.85)")  # 대한민국 차별화 강조 (붉은색)
            chart_border_colors.append("rgba(220, 38, 38, 1)")
        else:
            chart_labels.append(f"{label} ({rank}위)")
            chart_values.append(val)
            chart_bg_colors.append("rgba(59, 130, 246, 0.7)")  # 일반 국가 (파란색)
            chart_border_colors.append("rgba(37, 99, 235, 1)")

    # Chart.js용 상위 N + 대한민국 수평 막대 차트 데이터
    chart_data = {
        "type": "bar",
        "indexAxis": "y",
        "title": chart_title,
        "labels": chart_labels,
        "datasets": [{
            "label": f"수치 ({reference_period}년)",
            "data": chart_values,
            "backgroundColor": chart_bg_colors,
            "borderColor": chart_border_colors,
            "borderWidth": 1.5
        }]
    }

    data_payload = {
        "reference_period": str(reference_period),
        "top_n": chart_items,
        "bottom_n": bottom_list,
        "total_ranked_count": len(sorted_df)
    }
    if korea_item:
        data_payload["korea"] = korea_item

    return {
        "tool": "top_bottom_n",
        "reference_period": str(reference_period),
        "used_rows_count": int(len(valid_df)),
        "excluded_rows_count": total_excluded,
        "exclusion_reason": exclusion_reason,
        "used_columns": [label_column, ref_col],
        "unit": "수치 (예: %)",
        "caution": caution_text,
        "data": data_payload,
        "chart": chart_data
    }


# ==============================================================================
# 도구 8. group_summary (그룹별 평균·합계·개수 막대)
# ==============================================================================
def group_summary(df, reference_period, group_column=None, value_column=None, agg_func="mean", exclude_aggregates=True, **kwargs):
    """
    기준 시점을 기준으로 대륙/지역(Region)이나 소득군(IncomeGroup) 등 그룹별 평균/합계/개수 통계를 산출합니다.
    (규칙: 기준 시점 필수, 기준 시점 결측치 행 제외 및 제외 이유 반환)
    """
    if not reference_period or str(reference_period).strip() == "":
        raise ValueError("기준 시점(reference_period)은 필수 파라미터입니다.")

    val_col = str(value_column or reference_period)
    if val_col not in df.columns:
        raise ValueError(f"데이터셋에 기준 시점 열 '{val_col}'이 존재하지 않습니다.")

    label_col = get_first_label_column(df)
    work_df = df.copy()

    # 만약 group_column이 없거나 데이터에 없으면, 메타데이터 연계를 시도하거나 후보 탐색
    if not group_column or group_column not in work_df.columns:
        try:
            import glob, os
            meta_files = glob.glob(os.path.join("data", "**", "Metadata_Country*.csv"), recursive=True)
            if meta_files and "Country Code" in work_df.columns:
                meta_df = pd.read_csv(meta_files[0], encoding="utf-8-sig")
                avail_meta_cols = [c for c in ["Region", "IncomeGroup"] if c in meta_df.columns]
                if avail_meta_cols:
                    work_df = pd.merge(work_df, meta_df[["Country Code"] + avail_meta_cols], on="Country Code", how="left")
                    group_column = group_column if (group_column in avail_meta_cols) else avail_meta_cols[0]
        except Exception:
            pass

    if not group_column or group_column not in work_df.columns:
        candidate_cols = [c for c in work_df.select_dtypes(include=["object", "string"]).columns if c != label_col]
        if candidate_cols:
            group_column = candidate_cols[0]
        else:
            raise ValueError("그룹화할 범주형 열(예: Region, IncomeGroup 등)을 찾을 수 없습니다.")

    filtered_df, agg_excluded, _ = filter_aggregates(work_df, label_col=label_col, exclude_aggregates=exclude_aggregates)

    filtered_df["_numeric_val"] = pd.to_numeric(filtered_df[val_col], errors="coerce")
    valid_mask = filtered_df["_numeric_val"].notna() & filtered_df[group_column].notna() & (filtered_df[group_column].astype(str).str.strip() != "")
    valid_df = filtered_df[valid_mask].copy()

    nan_excluded = int(len(filtered_df) - len(valid_df))
    total_excluded = agg_excluded + nan_excluded

    reasons = []
    if agg_excluded > 0:
        reasons.append(f"집계 그룹 행 {agg_excluded}개 제외")
    if nan_excluded > 0:
        reasons.append(f"{reference_period}년 또는 그룹 정보 결측치 {nan_excluded}개 제외")
    exclusion_reason = ", ".join(reasons) if reasons else None

    grouped = valid_df.groupby(group_column)["_numeric_val"]
    if agg_func == "mean":
        agg_res = grouped.mean().round(4)
        agg_name = "평균"
    elif agg_func == "sum":
        agg_res = grouped.sum().round(4)
        agg_name = "합계"
    elif agg_func == "median":
        agg_res = grouped.median().round(4)
        agg_name = "중앙값"
    else:
        agg_res = grouped.count()
        agg_name = "개수"

    counts = grouped.count()
    result_list = []
    for grp_name, val in agg_res.sort_values(ascending=False).items():
        result_list.append({
            "group": str(grp_name),
            "value": round(float(val), 4),
            "count": int(counts[grp_name])
        })

    chart_data = {
        "type": "bar",
        "title": f"그룹({group_column})별 {agg_name} 비교 ({reference_period}년)",
        "labels": [x["group"] for x in result_list],
        "datasets": [{
            "label": f"{agg_name} 수치",
            "data": [x["value"] for x in result_list],
            "backgroundColor": "rgba(14, 165, 233, 0.7)"
        }]
    }

    return {
        "tool": "group_summary",
        "reference_period": str(reference_period),
        "used_rows_count": int(len(valid_df)),
        "excluded_rows_count": total_excluded,
        "exclusion_reason": exclusion_reason,
        "used_columns": [group_column, val_col],
        "unit": "수치 (예: %)",
        "caution": f"그룹별 수치는 각 그룹에 속한 국가들의 단순 {agg_name}이며, 인구 규모에 따른 가중치는 반영되지 않았습니다.",
        "data": {
            "group_column": group_column,
            "agg_func": agg_func,
            "groups": result_list
        },
        "chart": chart_data
    }


# ==============================================================================
# 도구 9. change_rate (두 시점 사이 변화량·변화율 막대)
# ==============================================================================
def change_rate(df, reference_period, compare_period=None, top_n=10, label_column=None, exclude_aggregates=True, **kwargs):
    """
    두 시점(비교 시점 vs 기준 시점) 사이의 절대 변화량(%p)과 변화율(%)을 산출하고 급성장 항목을 비교합니다.
    (규칙: 기준 시점 필수, 결측치 행 제외 및 제외 이유 반환)
    """
    if not reference_period or str(reference_period).strip() == "":
        raise ValueError("기준 시점(reference_period)은 필수 파라미터입니다.")

    ref_col = str(reference_period)
    if ref_col not in df.columns:
        raise ValueError(f"데이터셋에 기준 시점 열 '{ref_col}'이 존재하지 않습니다.")

    year_cols = detect_year_columns(df)
    if not compare_period:
        past_years = [y for y in year_cols if y < ref_col]
        if not past_years:
            raise ValueError(f"기준 시점({ref_col})보다 이전인 비교 시점 연도가 존재하지 않습니다.")
        target_past = str(int(ref_col) - 10)
        if target_past in past_years:
            comp_col = target_past
        else:
            comp_col = past_years[-1]
    else:
        comp_col = str(compare_period)
        if comp_col not in df.columns:
            raise ValueError(f"데이터셋에 비교 시점 열 '{comp_col}'이 존재하지 않습니다.")

    if label_column is None:
        label_column = get_first_label_column(df)

    filtered_df, agg_excluded, _ = filter_aggregates(df, label_col=label_column, exclude_aggregates=exclude_aggregates)

    s_ref = pd.to_numeric(filtered_df[ref_col], errors="coerce")
    s_comp = pd.to_numeric(filtered_df[comp_col], errors="coerce")

    valid_mask = s_ref.notna() & s_comp.notna()
    valid_df = filtered_df[valid_mask].copy()

    nan_excluded = int(len(filtered_df) - len(valid_df))
    total_excluded = agg_excluded + nan_excluded

    reasons = []
    if agg_excluded > 0:
        reasons.append(f"집계 그룹 행 {agg_excluded}개 제외")
    if nan_excluded > 0:
        reasons.append(f"{comp_col}년 또는 {ref_col}년 결측치 행 {nan_excluded}개 제외")
    exclusion_reason = ", ".join(reasons) if reasons else None

    v_ref = pd.to_numeric(valid_df[ref_col])
    v_comp = pd.to_numeric(valid_df[comp_col])

    valid_df["_diff_points"] = (v_ref - v_comp).round(4)
    valid_df["_pct_change"] = np.where(
        v_comp > 0,
        ((v_ref - v_comp) / v_comp * 100).round(2),
        np.nan
    )

    sorted_df = valid_df.sort_values(by="_diff_points", ascending=False)
    top_growth = sorted_df.head(top_n)

    top_growth_list = [
        {
            "rank": i + 1,
            "label": str(r[label_column]),
            "start_val": round(float(r[comp_col]), 2),
            "end_val": round(float(r[ref_col]), 2),
            "diff_points": round(float(r["_diff_points"]), 2),
            "pct_change": round(float(r["_pct_change"]), 2) if pd.notna(r["_pct_change"]) else None
        }
        for i, (_, r) in enumerate(top_growth.iterrows())
    ]

    chart_data = {
        "type": "bar",
        "title": f"보급률 증가 상위 {top_n}개 항목 ({comp_col}년 대비 {ref_col}년 포인트 변화량)",
        "labels": [x["label"] for x in top_growth_list],
        "datasets": [{
            "label": "변화량 (%p)",
            "data": [x["diff_points"] for x in top_growth_list],
            "backgroundColor": "rgba(16, 185, 129, 0.7)"
        }]
    }

    return {
        "tool": "change_rate",
        "reference_period": f"{comp_col} -> {ref_col}",
        "used_rows_count": int(len(valid_df)),
        "excluded_rows_count": total_excluded,
        "exclusion_reason": exclusion_reason,
        "used_columns": [label_column, comp_col, ref_col],
        "unit": "%p (포인트 변화량) / %",
        "caution": f"시작 시점({comp_col}년)의 초기 값이 매우 작았던 항목은 기저효과(Base effect)로 인해 변화율(%)이 지나치게 높게 계산될 수 있으므로 실제 증가 포인트(%p)를 함께 확인해야 합니다.",
        "data": {
            "start_year": comp_col,
            "end_year": ref_col,
            "top_growth": top_growth_list,
            "total_valid_count": int(len(valid_df))
        },
        "chart": chart_data
    }


# ==============================================================================
# 도구 10. distribution (구간별 빈도 분포 히스토그램)
# ==============================================================================
def distribution(df, reference_period, bins=10, value_column=None, exclude_aggregates=True, **kwargs):
    """
    기준 시점 수치의 구간별 데이터 분포(히스토그램 빈도 및 비율)를 산출합니다.
    (규칙: 기준 시점 필수, 결측치 행 제외 및 제외 이유 반환)
    """
    if not reference_period or str(reference_period).strip() == "":
        raise ValueError("기준 시점(reference_period)은 필수 파라미터입니다.")

    val_col = str(value_column or reference_period)
    if val_col not in df.columns:
        raise ValueError(f"데이터셋에 기준 시점 열 '{val_col}'이 존재하지 않습니다.")

    label_col = get_first_label_column(df)
    filtered_df, agg_excluded, _ = filter_aggregates(df, label_col=label_col, exclude_aggregates=exclude_aggregates)

    series = pd.to_numeric(filtered_df[val_col], errors="coerce").dropna()
    nan_excluded = int(len(filtered_df) - len(series))
    total_excluded = agg_excluded + nan_excluded

    reasons = []
    if agg_excluded > 0:
        reasons.append(f"집계 그룹 행 {agg_excluded}개 제외")
    if nan_excluded > 0:
        reasons.append(f"{reference_period}년 결측치 행 {nan_excluded}개 제외")
    exclusion_reason = ", ".join(reasons) if reasons else None

    if len(series) == 0:
        raise ValueError(f"'{val_col}' 열에 분포를 계산할 유효 수치가 없습니다.")

    counts, bin_edges = np.histogram(series, bins=bins)
    total_items = len(series)

    dist_list = []
    labels = []
    for i in range(len(counts)):
        low = round(float(bin_edges[i]), 1)
        high = round(float(bin_edges[i + 1]), 1)
        bin_label = f"{low}% ~ {high}%"
        cnt = int(counts[i])
        pct = round(cnt / total_items * 100, 2)
        labels.append(bin_label)
        dist_list.append({
            "range": bin_label,
            "min_val": low,
            "max_val": high,
            "count": cnt,
            "percentage": pct
        })

    chart_data = {
        "type": "bar",
        "title": f"{val_col} 구간별 데이터 분포 (히스토그램)",
        "labels": labels,
        "datasets": [{
            "label": "국가/항목 수",
            "data": [int(c) for c in counts],
            "backgroundColor": "rgba(168, 85, 247, 0.7)"
        }]
    }

    return {
        "tool": "distribution",
        "reference_period": str(reference_period),
        "used_rows_count": total_items,
        "excluded_rows_count": total_excluded,
        "exclusion_reason": exclusion_reason,
        "used_columns": [val_col],
        "unit": "개국 (빈도수)",
        "caution": f"{reference_period}년 수치의 좌우 편향(치우침)과 특정 구간에 집중된 밀집도를 확인하여 평균값의 신뢰성을 판단할 수 있습니다.",
        "data": {
            "bins_count": bins,
            "distribution": dist_list,
            "summary": {
                "min": round(float(series.min()), 2),
                "max": round(float(series.max()), 2),
                "total": total_items
            }
        },
        "chart": chart_data
    }


# ==============================================================================
# 도구 11. correlation_scatter (두 숫자 열 상관계수 및 산점도)
# ==============================================================================
def correlation_scatter(df, reference_period, x_column=None, y_column=None, label_column=None, exclude_aggregates=True, **kwargs):
    """
    두 수치 열 사이의 피어슨 상관계수를 계산하고 산점도 데이터를 도출합니다.
    (규칙: 기준 시점 필수, '상관관계는 인과관계가 아니다'를 주의사항에 반드시 포함)
    """
    if not reference_period or str(reference_period).strip() == "":
        raise ValueError("기준 시점(reference_period)은 필수 파라미터입니다.")

    y_col = str(y_column or reference_period)
    if y_col not in df.columns:
        raise ValueError(f"데이터셋에 기준 시점(Y축) 열 '{y_col}'이 존재하지 않습니다.")

    year_cols = detect_year_columns(df)
    if not x_column:
        past_years = [y for y in year_cols if y < y_col]
        if past_years:
            target_past = str(int(y_col) - 10)
            x_col = target_past if target_past in past_years else past_years[0]
        else:
            other_num = [c for c in df.select_dtypes(include=[np.number]).columns if c != y_col]
            if other_num:
                x_col = other_num[0]
            else:
                raise ValueError("상관관계를 비교할 X축 수치 열을 찾을 수 없습니다.")
    else:
        x_col = str(x_column)
        if x_col not in df.columns:
            raise ValueError(f"데이터셋에 X축 열 '{x_col}'이 존재하지 않습니다.")

    if label_column is None:
        label_column = get_first_label_column(df)

    filtered_df, agg_excluded, _ = filter_aggregates(df, label_col=label_column, exclude_aggregates=exclude_aggregates)

    sx = pd.to_numeric(filtered_df[x_col], errors="coerce")
    sy = pd.to_numeric(filtered_df[y_col], errors="coerce")

    valid_mask = sx.notna() & sy.notna()
    valid_df = filtered_df[valid_mask].copy()

    nan_excluded = int(len(filtered_df) - len(valid_df))
    total_excluded = agg_excluded + nan_excluded

    reasons = []
    if agg_excluded > 0:
        reasons.append(f"집계 그룹 행 {agg_excluded}개 제외")
    if nan_excluded > 0:
        reasons.append(f"{x_col} 또는 {y_col} 결측치 행 {nan_excluded}개 제외")
    exclusion_reason = ", ".join(reasons) if reasons else None

    if len(valid_df) < 2:
        raise ValueError("상관계수를 계산하기 위한 유효 행 수가 부족합니다 (최소 2행 필요).")

    vx = pd.to_numeric(valid_df[x_col])
    vy = pd.to_numeric(valid_df[y_col])

    corr = round(float(vx.corr(vy)), 4)

    if abs(corr) >= 0.7:
        strength = "매우 강한"
    elif abs(corr) >= 0.4:
        strength = "유의미한"
    else:
        strength = "다소 약한"
    direction = "양(+)의" if corr >= 0 else "음(-)의"
    interpretation = f"{x_col}와(과) {y_col} 사이에 {strength} {direction} 선형 상관관계(r={corr})가 나타납니다."

    points = []
    for _, r in valid_df.iterrows():
        points.append({
            "x": round(float(r[x_col]), 2),
            "y": round(float(r[y_col]), 2),
            "label": str(r[label_column])
        })

    chart_data = {
        "type": "scatter",
        "title": f"{x_col} vs {y_col} 상관관계 산점도 (r={corr})",
        "datasets": [{
            "label": f"국가별 위치 ({x_col} vs {y_col})",
            "data": [{"x": p["x"], "y": p["y"]} for p in points],
            "backgroundColor": "rgba(244, 63, 94, 0.6)"
        }],
        "point_labels": [p["label"] for p in points]
    }

    return {
        "tool": "correlation_scatter",
        "reference_period": str(reference_period),
        "used_rows_count": int(len(valid_df)),
        "excluded_rows_count": total_excluded,
        "exclusion_reason": exclusion_reason,
        "used_columns": [label_column, x_col, y_col],
        "unit": "피어슨 상관계수 (r)",
        # 중요 규칙: 반드시 '상관관계는 인과관계가 아니다'를 주의사항에 포함
        "caution": "상관관계는 인과관계가 아닙니다. 두 변수가 매우 높은 상관성을 보이더라도 한 변수가 다른 변수의 직접적인 원인이 됨을 뜻하지 않으며, 제3의 요인(경제 성장, 인프라 등)이 영향을 미쳤을 수 있습니다.",
        "data": {
            "x_column": x_col,
            "y_column": y_col,
            "correlation_coefficient": corr,
            "interpretation": interpretation,
            "points_count": len(points),
            "sample_points": points[:10]
        },
        "chart": chart_data
    }


# ==============================================================================
# 도구 12. compare_one_vs_all (특정 항목 vs 전체 평균·중앙값 강조 막대)
# ==============================================================================
def compare_one_vs_all(df, reference_period, target_item=None, value_column=None, label_column=None, exclude_aggregates=True, **kwargs):
    """
    특정 대상(예: 대한민국)의 수치를 전체 국가들의 평균 및 중앙값과 1:1 비교하여 강조 차트를 도출합니다.
    (규칙: 기준 시점 필수, 결측치 행 제외 및 제외 이유 반환)
    """
    if not reference_period or str(reference_period).strip() == "":
        raise ValueError("기준 시점(reference_period)은 필수 파라미터입니다.")

    val_col = str(value_column or reference_period)
    if val_col not in df.columns:
        raise ValueError(f"데이터셋에 기준 시점 열 '{val_col}'이 존재하지 않습니다.")

    if label_column is None:
        label_column = get_first_label_column(df)

    filtered_df, agg_excluded, _ = filter_aggregates(df, label_col=label_column, exclude_aggregates=exclude_aggregates)

    series = pd.to_numeric(filtered_df[val_col], errors="coerce")
    valid_mask = series.notna()
    valid_df = filtered_df[valid_mask].copy()
    valid_df["_numeric_val"] = pd.to_numeric(valid_df[val_col])

    nan_excluded = int(len(filtered_df) - len(valid_df))
    total_excluded = agg_excluded + nan_excluded

    reasons = []
    if agg_excluded > 0:
        reasons.append(f"집계 그룹 행 {agg_excluded}개 제외")
    if nan_excluded > 0:
        reasons.append(f"{reference_period}년 결측치 행 {nan_excluded}개 제외")
    exclusion_reason = ", ".join(reasons) if reasons else None

    if not target_item:
        korea_matches = valid_df[valid_df[label_column].astype(str).str.contains("Korea", case=False, na=False)]
        if len(korea_matches) > 0:
            target_item = str(korea_matches.iloc[0][label_column])
        else:
            target_item = str(valid_df.iloc[0][label_column])

    target_match = valid_df[valid_df[label_column] == target_item]
    if len(target_match) == 0:
        raise ValueError(f"지정한 항목 '{target_item}'이(가) {reference_period}년 유효 데이터 목록에 존재하지 않습니다.")

    target_val = round(float(target_match.iloc[0]["_numeric_val"]), 4)

    mean_val = round(float(valid_df["_numeric_val"].mean()), 4)
    median_val = round(float(valid_df["_numeric_val"].median()), 4)

    sorted_df = valid_df.sort_values(by="_numeric_val", ascending=False).reset_index(drop=True)
    target_rank = int(sorted_df[sorted_df[label_column] == target_item].index[0]) + 1
    total_count = len(sorted_df)
    percentile = round((total_count - target_rank + 1) / total_count * 100, 2)

    diff_from_mean = round(target_val - mean_val, 4)
    diff_from_median = round(target_val - median_val, 4)

    chart_data = {
        "type": "bar",
        "title": f"{target_item} vs 전체 집단 비교 ({reference_period}년)",
        "labels": [f"{target_item} (선택 대상)", "전체 평균값 (Mean)", "전체 중앙값 (Median)"],
        "datasets": [{
            "label": f"수치 ({reference_period}년)",
            "data": [target_val, mean_val, median_val],
            "backgroundColor": [
                "rgba(239, 68, 68, 0.8)",
                "rgba(107, 114, 128, 0.6)",
                "rgba(59, 130, 246, 0.6)"
            ]
        }]
    }

    return {
        "tool": "compare_one_vs_all",
        "reference_period": str(reference_period),
        "used_rows_count": total_count,
        "excluded_rows_count": total_excluded,
        "exclusion_reason": exclusion_reason,
        "used_columns": [label_column, val_col],
        "unit": "수치 (예: %)",
        "caution": f"{target_item}의 수치가 전체 집단과 비교하여 어느 백분위(상위 {round(100 - percentile, 1)}%)에 위치하는지 동일 시점({reference_period}년)에서 직접 확인합니다.",
        "data": {
            "target_item": target_item,
            "target_value": target_val,
            "mean": mean_val,
            "median": median_val,
            "diff_from_mean": diff_from_mean,
            "diff_from_median": diff_from_median,
            "rank": target_rank,
            "total_count": total_count,
            "percentile": percentile
        },
        "chart": chart_data
    }


