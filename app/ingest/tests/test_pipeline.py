import os
import json
import pytest
import pandas as pd
import numpy as np
from src.pipeline import (
    clean_amount, 
    clean_account, 
    clean_note, 
    extract_financial_statement, 
    extract_equity_statement,
    run_pipeline
)
from pathlib import Path

TEST_DATA_DIR = Path(__file__).parent / "test_data" / "raw"

# ==========================================
# 1. 단위 테스트: 데이터 정제 헬퍼 함수 검증
# ==========================================
def test_clean_amount():
    # 일반 콤마 숫자
    assert clean_amount("1,234,567") == 1234567
    # 괄호 쳐진 음수
    assert clean_amount("(500)") == -500
    # 하이픈 및 빈칸 처리
    assert clean_amount("-") == 0
    assert clean_amount("") == 0
    assert clean_amount(np.nan) == 0

def test_clean_account():
    # 로마자 및 숫자 넘버링 제거 확인
    assert clean_account("Ⅰ. 유 동 자 산") == "유동자산"
    assert clean_account("1. 매출액") == "매출액"
    assert clean_account("  이 익 잉 여 금  ") == "이익잉여금"

def test_clean_note():
    # 문자열에서 주석 번호만 리스트로 잘 뽑아내는지 확인
    assert clean_note("(주석 13, 14 참조)") == ['13', '14']
    assert clean_note("nan") == []
    assert clean_note(np.nan) == []

# ==========================================
# 2. 모의(Mock) 데이터 테스트: 제외 키워드(exclude_keywords) 검증
# ==========================================
def test_extract_financial_statement_exclude_keywords():
    # 가짜 손익계산서 데이터
    df_is = pd.DataFrame([
        ["매출액", "100", "50"], 
        ["당기순이익", "10", "5"]
    ], columns=["과목명", "당기", "전기"])
    
    # 가짜 포괄손익계산서 데이터
    df_cis = pd.DataFrame([
        ["당기순이익", "10", "5"], 
        ["총포괄손익", "12", "6"]
    ], columns=["과목명", "당기", "전기"])

    tables = [df_is, df_cis]

    # 포괄손익계산서를 추출할 때, '매출액'이 들어간 표(손익계산서)는 배제하도록 지시
    result = extract_financial_statement(
        tables, 
        title="포괄손익계산서", 
        keywords=['당기순이익', '총포괄손익'], 
        exclude_keywords=['매출액']
    )

    # 손익계산서를 건너뛰고 포괄손익계산서가 정확히 추출되었는지 검증
    assert "포괄손익계산서" in result
    extracted_rows = result["포괄손익계산서"]["tables"][0]["rows"]
    assert len(extracted_rows) == 2
    assert extracted_rows[1][0] == "총포괄손익"

# ==========================================
# 3. 모의(Mock) 데이터 테스트: 자본변동표 NaN 에러 방어 검증
# ==========================================
def test_extract_equity_statement_nan_handling():
    # 가짜 자본변동표 데이터 (의도적으로 NaN 값을 주입)
    df_eq = pd.DataFrame([
        ["기초자본", 100.0, np.nan],  # 전기 금액이 없는 경우 (NaN)
        ["당기순이익", 50.0, 20.0]
    ], columns=["자본금", "이익잉여금", "자본총계"])

    tables = [df_eq]

    # 자본변동표 파서 실행
    result = extract_equity_statement(tables, title="자본변동표")

    assert "자본변동표" in result
    extracted_rows = result["자본변동표"]["tables"][0]["rows"]
    
    # 기초자본 행(첫 번째 행)의 자본총계(마지막 열) 데이터가 NaN 대신 0으로 안전하게 변환되었는지 검증
    # 행 구조: ["상위구분", "구분", "관련주석", "자본금", "이익잉여금", "자본총계"]
    기초자본_행 = extracted_rows[0]
    assert 기초자본_행[-1] == 0 
    assert 기초자본_행[-2] == 100000000  # 100.0 이 100만 배 처리되어 정수로 들어갔는지 확인

# ==========================================
#🚀 4. 통합 테스트 (실제 HTML 파일 활용)
# ==========================================
def test_full_pipeline_with_real_file(tmp_path):
    """
    실제 HTML 파일을 읽어 파이프라인 전체를 실행하고, 
    생성된 JSON 파일의 구조가 완벽한지 검증합니다.
    """
    
    # 1. 준비: 테스트용 HTML 파일이 폴더에 있는지 확인
    test_files = list(TEST_DATA_DIR.glob("*.htm*"))
    if not test_files:
        pytest.skip(f"테스트 중단: {TEST_DATA_DIR} 폴더에 HTML 파일이 없습니다. 파일을 하나 넣어주세요!")

    # 2. 실행: 파이프라인 가동!
    # tmp_path는 pytest가 제공하는 '일회용 임시 폴더'입니다.
    # 테스트가 끝나면 결과물을 자동으로 싹 지워주어 폴더가 지저분해지지 않습니다.
    run_pipeline(str(TEST_DATA_DIR), str(tmp_path))

    # 3. 검증 1: JSON 파일이 제대로 생성되었는가?
    output_files = list(tmp_path.glob("*.json"))
    assert len(output_files) > 0, "에러: JSON 결과 파일이 생성되지 않았습니다!"

    # 4. 검증 2: 생성된 JSON을 열어서 내부 구조가 맞는지 꼼꼼히 확인
    with open(output_files[0], 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 최상위 키(연도) 추출 (예: "2018")
    year_key = list(data.keys())[0]
    
    # 해당 연도 데이터 추출
    year_data = data[year_key]

    # 우리가 파이프라인에서 추출하기로 한 '핵심 6대장'이 잘 들어있는지 확인
    assert "감사보고서" in year_data, "'감사보고서' 섹션이 누락되었습니다."
    assert "재무상태표" in year_data, "'재무상태표' 섹션이 누락되었습니다."
    assert "손익계산서" in year_data, "'손익계산서' 섹션이 누락되었습니다."
    assert "포괄손익계산서" in year_data, "'포괄손익계산서' 섹션이 누락되었습니다."
    assert "자본변동표" in year_data, "'자본변동표' 섹션이 누락되었습니다."
    assert "부록" in year_data, "'부록' 섹션이 누락되었습니다."
    assert "주석" in year_data, "'주석' 섹션이 누락되었습니다."

    # 5. 검증 3: 상세 로직 확인 (예: 도입부가 잘 파싱되었는지?)
    assert "도입부" in year_data["감사보고서"]["sub_sections"], "도입부 텍스트가 추출되지 않았습니다."
    
    # 6. 검증 4: 배제 단어(exclude_keywords)가 잘 작동해서 표가 섞이지 않았는지 간접 확인
    # 포괄손익계산서 안에 '총포괄손익'이 있는지 확인 (자본변동표로 대체되었다면 이 테스트에서 걸림)
    cis_tables = year_data["포괄손익계산서"].get("tables", [])
    if cis_tables:
        # 표의 모든 텍스트를 하나의 문자열로 합쳐서 확인
        table_content_str = str(cis_tables[0]["rows"])
        assert "포괄" in table_content_str, "포괄손익계산서 표 내용이 비정상적입니다 (표 섞임 의심)."