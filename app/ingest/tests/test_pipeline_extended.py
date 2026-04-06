import json
import pytest
import pandas as pd
import numpy as np
from pathlib import Path
from bs4 import BeautifulSoup

from app.ingest.src.pipeline import (
    clean_amount,
    clean_account,
    clean_note,
    extract_financial_statement,
    extract_equity_statement,
    run_pipeline,
    parse_intro,
)

TEST_DATA_DIR = Path(__file__).parent / "test_data" / "raw"


# ==========================================
# 1. 단위 테스트: 데이터 정제 헬퍼 함수 검증
# ==========================================
@pytest.mark.parametrize(
    "raw, expected",
    [
        ("1,234,567", 1234567),
        ("(500)", -500),
        ("-", 0),
        ("", 0),
        (np.nan, 0),
        ("1,234.0", 1234),
        ("(1,234.0)", -1234),
        ("  1,234  ", 1234),
        ("N/A", "N/A"),
    ],
)
def test_clean_amount(raw, expected):
    assert clean_amount(raw) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Ⅰ. 유 동 자 산", "유동자산"),
        ("1. 매출액", "매출액"),
        ("  이 익 잉 여 금  ", "이익잉여금"),
        ("Ⅱ. 자 본 금", "자본금"),
        ("10. 당 기 순 이 익", "당기순이익"),
    ],
)
def test_clean_account(raw, expected):
    assert clean_account(raw) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("(주석 13, 14 참조)", ["13", "14"]),
        ("nan", []),
        (np.nan, []),
        ("주석 1", ["1"]),
        ("(주 12)", ["12"]),
        ("1, 2, 15", ["1", "2", "15"]),
        ("해당없음", []),
        ("주석 없음", []),
    ],
)
def test_clean_note(raw, expected):
    assert clean_note(raw) == expected


# ==========================================
# 2. 모의(Mock) 데이터 테스트: 재무제표 추출 로직 검증
# ==========================================
def test_extract_financial_statement_exclude_keywords():
    df_is = pd.DataFrame(
        [["매출액", "100", "50"], ["당기순이익", "10", "5"]],
        columns=["과목명", "당기", "전기"],
    )

    df_cis = pd.DataFrame(
        [["당기순이익", "10", "5"], ["총포괄손익", "12", "6"]],
        columns=["과목명", "당기", "전기"],
    )

    tables = [df_is, df_cis]

    result = extract_financial_statement(
        tables,
        title="포괄손익계산서",
        keywords=["당기순이익", "총포괄손익"],
        exclude_keywords=["매출액"],
    )

    assert "포괄손익계산서" in result
    extracted_rows = result["포괄손익계산서"]["tables"][0]["rows"]
    assert len(extracted_rows) == 2
    assert extracted_rows[1][0] == "총포괄손익"


def test_extract_financial_statement_without_note_column():
    df_bs = pd.DataFrame(
        [
            ["유동자산", "100", "80"],
            ["유동부채", "40", "30"],
            ["이익잉여금", "20", "10"],
        ],
        columns=["과목명", "당기", "전기"],
    )

    result = extract_financial_statement(
        [df_bs], title="재무상태표", keywords=["유동자산", "유동부채", "이익잉여금"]
    )

    assert "재무상태표" in result
    extracted_rows = result["재무상태표"]["tables"][0]["rows"]

    assert extracted_rows[0][1] == []
    assert extracted_rows[1][1] == []
    assert extracted_rows[2][1] == []


def test_extract_financial_statement_with_note_column():
    df_is = pd.DataFrame(
        [
            ["매출액", "주석 1", "100", "80"],
            ["영업이익", "주석 2", "30", "20"],
            ["당기순이익", "주석 3", "10", "5"],
        ],
        columns=["과목명", "주석", "당기", "전기"],
    )

    result = extract_financial_statement(
        [df_is], title="손익계산서", keywords=["매출액", "영업이익", "당기순이익"]
    )

    assert "손익계산서" in result
    extracted_rows = result["손익계산서"]["tables"][0]["rows"]

    assert extracted_rows[0][1] == ["1"]
    assert extracted_rows[1][1] == ["2"]
    assert extracted_rows[2][1] == ["3"]


def test_extract_financial_statement_four_value_columns():
    df_is = pd.DataFrame(
        [
            ["매출액", None, "100", None, "80"],
            ["영업이익", "30", None, "20", None],
            ["당기순이익", None, "10", None, "5"],
        ],
        columns=["과목명", "당기1", "당기2", "전기1", "전기2"],
    )

    result = extract_financial_statement(
        [df_is], title="손익계산서", keywords=["매출액", "영업이익", "당기순이익"]
    )

    assert "손익계산서" in result
    extracted_rows = result["손익계산서"]["tables"][0]["rows"]

    assert extracted_rows[0][2] == 100000000
    assert extracted_rows[0][3] == 80000000
    assert extracted_rows[1][2] == 30000000
    assert extracted_rows[1][3] == 20000000
    assert extracted_rows[2][2] == 10000000
    assert extracted_rows[2][3] == 5000000


def test_extract_financial_statement_returns_empty_when_no_match():
    df = pd.DataFrame([["자산", "100", "80"]], columns=["과목명", "당기", "전기"])

    result = extract_financial_statement(
        [df], title="재무상태표", keywords=["유동자산", "유동부채", "이익잉여금"]
    )

    assert result == {}


def test_extract_financial_statement_adjust_unit_exception_cases():
    df = pd.DataFrame(
        [
            ["주당순이익", "1.5", "1.2"],
            ["법인세비용차감후주당순이익", "2.0", "1.8"],
        ],
        columns=["과목명", "당기", "전기"],
    )

    result = extract_financial_statement(
        [df], title="주당이익표", keywords=["주당순이익"]
    )

    assert "주당이익표" in result
    extracted_rows = result["주당이익표"]["tables"][0]["rows"]

    assert extracted_rows[0][2] == 1
    assert extracted_rows[0][3] == 1
    assert extracted_rows[1][2] == 2
    assert extracted_rows[1][3] == 1


# ==========================================
# 3. 모의(Mock) 데이터 테스트: 자본변동표 검증
# ==========================================
def test_extract_equity_statement_nan_handling():
    df_eq = pd.DataFrame(
        [["기초자본", 100.0, np.nan], ["당기순이익", 50.0, 20.0]],
        columns=["자본금", "이익잉여금", "자본총계"],
    )

    tables = [df_eq]

    result = extract_equity_statement(tables, title="자본변동표")

    assert "자본변동표" in result
    extracted_rows = result["자본변동표"]["tables"][0]["rows"]

    기초자본_행 = extracted_rows[0]
    assert 기초자본_행[-1] == 0
    assert 기초자본_행[-2] == 100000000


def test_extract_equity_statement_balance_keywords():
    df_eq = pd.DataFrame(
        [
            ["기초자본", 100, 200, 300],
            ["당기순이익", 0, 50, 50],
            ["기말자본", 100, 250, 350],
        ],
        columns=["구분", "자본금", "이익잉여금", "자본총계"],
    )

    tables = [df_eq]

    result = extract_equity_statement(tables, title="자본변동표")

    assert "자본변동표" in result
    extracted_rows = result["자본변동표"]["tables"][0]["rows"]

    assert extracted_rows[0][0] == "기초 및 기말 잔액"
    assert extracted_rows[2][0] == "기초 및 기말 잔액"


def test_extract_equity_statement_parent_grouping():
    df_eq = pd.DataFrame(
        [
            ["기타 변동", 0, 0, 0],
            ["당기순이익", 0, 10, 10],
            ["배당", 0, -5, -5],
        ],
        columns=["구분", "자본금", "이익잉여금", "자본총계"],
    )

    tables = [df_eq]

    result = extract_equity_statement(tables, title="자본변동표")

    assert "자본변동표" in result
    extracted_rows = result["자본변동표"]["tables"][0]["rows"]

    assert extracted_rows[0][0] == "기타 변동"
    assert extracted_rows[1][0] == "기타 변동"


def test_extract_equity_statement_with_note_column():
    df_eq = pd.DataFrame(
        [
            ["당기순이익", "주석 10", 0, 50, 50],
            ["배당", "주석 12", 0, -10, -10],
        ],
        columns=["구분", "주석", "자본금", "이익잉여금", "자본총계"],
    )

    tables = [df_eq]

    result = extract_equity_statement(tables, title="자본변동표")

    assert "자본변동표" in result
    extracted_rows = result["자본변동표"]["tables"][0]["rows"]

    assert extracted_rows[0][2] == ["10"]
    assert extracted_rows[1][2] == ["12"]


def test_extract_equity_statement_returns_empty_when_no_match():
    df = pd.DataFrame(
        [
            ["유동자산", 100, 200],
            ["유동부채", 50, 60],
        ],
        columns=["과목명", "당기", "전기"],
    )

    result = extract_equity_statement([df], title="자본변동표")

    assert result == {}


# ==========================================
# 4. parse_intro 관련 테스트
# ==========================================
def test_parse_intro_spacing_recovery():
    html = """
    <html>
        <body>
            <p>감 사 보 고 서</p>
            <p>재 무 제 표 에 대 한 경 영 진 의 책 임</p>
            <p>이 문서는 테스트용입니다.</p>
            <p>(첨부) 재무제표</p>
        </body>
    </html>
    """
    soup = BeautifulSoup(html, "lxml")
    result = parse_intro(soup)

    assert "감사보고서" in result
    report = result["감사보고서"]

    assert "도입부" in report["sub_sections"]

    intro_text = report["sub_sections"]["도입부"]["content"]
    assert "감사보고서" in intro_text or "테스트용입니다." in intro_text


# ==========================================
# 5. 통합 테스트 (실제 HTML 파일 활용)
# ==========================================
def assert_section_schema(section):
    assert "title" in section
    assert "content" in section
    assert "tables" in section
    assert "sub_sections" in section


def assert_note_section_schema(section):
    assert "title" in section
    assert "content" in section

    assert isinstance(section["title"], str)
    assert isinstance(section["content"], str)

    if "tables" in section:
        assert isinstance(section["tables"], list)
    if "sub_sections" in section:
        assert isinstance(section["sub_sections"], dict)


def assert_table_schema(table):
    assert "unit" in table
    assert "columns" in table
    assert "rows" in table
    assert "annotations" in table


def test_full_pipeline_with_real_file(tmp_path):
    """
    실제 HTML 파일을 읽어 파이프라인 전체를 실행하고,
    생성된 JSON 파일의 구조가 완벽한지 검증합니다.
    """

    test_files = list(TEST_DATA_DIR.glob("*.htm*"))
    if not test_files:
        pytest.skip(
            f"테스트 중단: {TEST_DATA_DIR} 폴더에 HTML 파일이 없습니다. 파일을 하나 넣어주세요!"
        )

    run_pipeline(str(TEST_DATA_DIR), str(tmp_path))

    output_files = list(tmp_path.glob("*.json"))
    assert len(output_files) > 0, "에러: JSON 결과 파일이 생성되지 않았습니다!"

    with open(output_files[0], "r", encoding="utf-8") as f:
        data = json.load(f)

    year_key = list(data.keys())[0]
    year_data = data[year_key]

    # 기업명 검증 추가
    assert "company" in year_data, "'company' 필드가 누락되었습니다."
    assert "삼성전자" in year_data["company"], f"기업명이 올바르지 않습니다: {year_data['company']}"

    assert "감사보고서" in year_data, "'감사보고서' 섹션이 누락되었습니다."
    assert "재무상태표" in year_data, "'재무상태표' 섹션이 누락되었습니다."
    assert "손익계산서" in year_data, "'손익계산서' 섹션이 누락되었습니다."
    assert "포괄손익계산서" in year_data, "'포괄손익계산서' 섹션이 누락되었습니다."
    assert "자본변동표" in year_data, "'자본변동표' 섹션이 누락되었습니다."
    assert "부록" in year_data, "'부록' 섹션이 누락되었습니다."
    assert "주석" in year_data, "'주석' 섹션이 누락되었습니다."

    for section_name in [
        "감사보고서",
        "재무상태표",
        "손익계산서",
        "포괄손익계산서",
        "자본변동표",
        "부록",
    ]:
        assert_section_schema(year_data[section_name])
    # 주석은 구조가 다르므로 별도 검증
    notes = year_data["주석"]

    assert isinstance(notes, dict)
    assert len(notes) > 0, "주석이 비어있습니다."

    # 첫 번째 주석 항목 구조 검증
    first_key = list(notes.keys())[0]
    first_note = notes[first_key]

    assert_note_section_schema(first_note)
    assert "도입부" in year_data["감사보고서"]["sub_sections"], (
        "도입부 텍스트가 추출되지 않았습니다."
    )

    cis_tables = year_data["포괄손익계산서"].get("tables", [])
    if cis_tables:
        assert_table_schema(cis_tables[0])
        table_content_str = str(cis_tables[0]["rows"])
        assert "포괄" in table_content_str, (
            "포괄손익계산서 표 내용이 비정상적입니다 (표 섞임 의심)."
        )


# ==========================================
# 6. 파이프라인 입출력 예외/경계 테스트
# ==========================================
def test_run_pipeline_with_empty_input_dir(tmp_path, capsys):
    """
    입력 폴더가 비어 있을 때 예외 없이 종료되는지 확인합니다.
    """
    empty_raw_dir = tmp_path / "raw"
    processed_dir = tmp_path / "processed"

    empty_raw_dir.mkdir()
    processed_dir.mkdir()

    run_pipeline(str(empty_raw_dir), str(processed_dir))

    captured = capsys.readouterr()
    assert "HTML 파일이 없습니다" in captured.out
    assert list(processed_dir.glob("*.json")) == []


def test_run_pipeline_unknown_year_filename(tmp_path):
    """
    파일명에 연도가 없을 때 Unknown으로 처리되는지 확인합니다.
    """
    raw_dir = tmp_path / "raw"
    processed_dir = tmp_path / "processed"
    raw_dir.mkdir()
    processed_dir.mkdir()

    html = """
    <html>
        <body>
            <p>감사보고서</p>
            <p>재무제표에 대한 경영진의 책임</p>
            <table>
                <tr><th>과목명</th><th>당기</th><th>전기</th></tr>
                <tr><td>유동자산</td><td>100</td><td>80</td></tr>
                <tr><td>유동부채</td><td>40</td><td>30</td></tr>
                <tr><td>이익잉여금</td><td>20</td><td>10</td></tr>
            </table>
        </body>
    </html>
    """

    sample_file = raw_dir / "sample_report.html"
    sample_file.write_text(html, encoding="utf-8")

    run_pipeline(str(raw_dir), str(processed_dir))

    output_files = list(processed_dir.glob("*.json"))
    assert len(output_files) == 1
    # UnknownCompany_audit_report_Unknown_structured.json
    assert "UnknownCompany" in output_files[0].name
    assert "Unknown" in output_files[0].name


def test_run_pipeline_utf8_fallback(tmp_path):
    """
    UTF-8 파일도 fallback으로 읽을 수 있는지 확인합니다.
    """
    raw_dir = tmp_path / "raw"
    processed_dir = tmp_path / "processed"
    raw_dir.mkdir()
    processed_dir.mkdir()

    html = """
    <html>
        <body>
            <p>감사보고서</p>
            <p>재무제표에 대한 경영진의 책임</p>
            <table>
                <tr><th>과목명</th><th>당기</th><th>전기</th></tr>
                <tr><td>유동자산</td><td>100</td><td>80</td></tr>
                <tr><td>유동부채</td><td>40</td><td>30</td></tr>
                <tr><td>이익잉여금</td><td>20</td><td>10</td></tr>
            </table>
        </body>
    </html>
    """

    sample_file = raw_dir / "sample_2024.html"
    sample_file.write_text(html, encoding="utf-8")

    run_pipeline(str(raw_dir), str(processed_dir))

    output_files = list(processed_dir.glob("*.json"))
    assert len(output_files) == 1

    with open(output_files[0], "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "2024" in data
