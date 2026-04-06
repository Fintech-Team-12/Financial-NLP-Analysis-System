import importlib.util
from pathlib import Path

import pytest


def _load_module():
    candidates = [
        Path(__file__).resolve().parent / "enrich_flattened_for_rag.py",
        Path(__file__).resolve().parent.parent / "enrich_flattened_for_rag.py",
        Path(__file__).resolve().parent.parent / "data_process" / "enrich_flattened_for_rag.py",
        Path.cwd() / "enrich_flattened_for_rag.py",
        Path.cwd() / "chroma" / "enrich_flattened_for_rag.py",
        Path.cwd() / "chroma" / "data_process" / "enrich_flattened_for_rag.py",
    ]

    target = next((p for p in candidates if p.exists()), None)
    if target is None:
        raise FileNotFoundError(
            "enrich_flattened_for_rag.py 파일을 찾지 못했습니다. "
            "테스트 파일과 같은 폴더, chroma/, 또는 chroma/data_process/ 아래에 두세요."
        )

    spec = importlib.util.spec_from_file_location("target_module", target)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


m = _load_module()


def test_normalize_path_trims_and_joins():
    assert m.normalize_path(" 주석 > 2 >  2.1 ") == "주석 > 2 > 2.1"
    assert m.normalize_path("") == ""
    assert m.normalize_path("주석") == "주석"


def test_make_parent_path():
    assert m.make_parent_path("주석 > 2 > 2.1") == "주석 > 2"
    assert m.make_parent_path("주석") == ""
    assert m.make_parent_path("") == ""


def test_make_section_uid():
    assert m.make_section_uid(2014, "주석 > 2 > 2.1") == "2014::주석 > 2 > 2.1"
    assert m.make_section_uid(2014, "") == "2014::ROOT"


def test_make_chunk_id_is_deterministic():
    first = m.make_chunk_id("2014_note_1", 3)
    second = m.make_chunk_id("2014_note_1", 3)
    third = m.make_chunk_id("2014_note_1", 4)

    assert first == second
    assert first != third
    assert first.startswith("2014_note_1_")


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("(단위: 원)", "원"),
        ("(단위 : 백만원)", "백만원"),
        ("(단위: 주, 원)", "주, 원"),
        ("(단위：천원)", "천원"),
        ("(원)", "원"),
        ("", None),
        (None, None),
    ],
)
def test_extract_amount_unit(raw, expected):
    assert m.extract_amount_unit(raw) == expected


def test_rebuild_ids_sets_section_id_and_parent_section_id():
    records = [
        {
            "year": 2014,
            "section_path": "주석 > 2 > 2.1",
            "section_title": "현금및현금성자산",
        }
    ]

    rebuilt = m.rebuild_ids(records)
    rec = rebuilt[0]

    assert rec["section_path"] == "주석 > 2 > 2.1"
    assert rec["section_id"] == "2014::주석 > 2 > 2.1"
    assert rec["parent_section_id"] == "2014::주석 > 2"


def test_compute_leaf_flags():
    records = [
        {"section_path": "주석"},
        {"section_path": "주석 > 2"},
        {"section_path": "주석 > 2 > 2.1"},
        {"section_path": "주석 > 3"},
    ]

    flags = m.compute_leaf_flags(records)
    assert flags == [False, False, True, True]


def test_make_structural_context_text_with_children():
    rec = {
        "top_section": "주석",
        "note_number": "2",
        "section_title": "현금및현금성자산",
    }
    children = [
        {"section_title": "당기"},
        {"section_title": "전기"},
    ]

    text = m.make_structural_context_text(rec, children)

    assert "주석" in text
    assert "주석 2" in text
    assert "현금및현금성자산" in text
    assert "하위 섹션: 당기, 전기" in text


def test_handle_empty_content_fills_parent_and_removes_empty_leaf(capsys):
    parent_id = "2014::주석 > 2"
    records = [
        {
            "section_id": parent_id,
            "parent_section_id": "2014::주석",
            "top_section": "주석",
            "note_number": "2",
            "section_title": "현금및현금성자산",
            "content_text": "",
        },
        {
            "section_id": "2014::주석 > 2 > 2.1",
            "parent_section_id": parent_id,
            "top_section": "주석",
            "note_number": "2",
            "section_title": "당기",
            "content_text": "당기 내용",
        },
        {
            "section_id": "2014::주석 > 3",
            "parent_section_id": "2014::주석",
            "top_section": "주석",
            "note_number": "3",
            "section_title": "제거대상",
            "content_text": "",
        },
    ]

    result = m.handle_empty_content(records)
    stderr = capsys.readouterr().err

    assert len(result) == 2
    filled_parent = next(r for r in result if r["section_id"] == parent_id)
    assert filled_parent["_enriched_empty_fill"] is True
    assert "하위 섹션" in filled_parent["content_text"]
    assert "[REMOVE EMPTY]" in stderr
    assert "제거대상" in stderr


def test_drop_raw_content():
    records = [{"raw_content": "원본", "content_text": "정제본", "year": 2014}]
    result = m.drop_raw_content(records)

    assert "raw_content" not in result[0]
    assert result[0]["content_text"] == "정제본"


def test_normalize_table_data_removes_note_column_and_collects_related_notes():
    table_data = {
        "unit": "(단위: 원)",
        "columns": ["계정", "금액", "주석"],
        "rows": [
            ["현금및현금성자산", "100", ["2", "3"]],
            ["매출채권", "200", ["4"]],
        ],
    }

    clean_table, related_notes, amount_unit = m.normalize_table_data(table_data)

    assert clean_table["columns"] == ["계정", "금액"]
    assert clean_table["rows"] == [
        ["현금및현금성자산", "100"],
        ["매출채권", "200"],
    ]
    assert related_notes == ["2", "3", "4"]
    assert amount_unit == "원"


def test_normalize_table_data_without_note_column():
    table_data = {
        "unit": "(단위: 백만원)",
        "columns": ["계정", "금액"],
        "rows": [["현금및현금성자산", "100"]],
    }

    clean_table, related_notes, amount_unit = m.normalize_table_data(table_data)

    assert clean_table == table_data
    assert related_notes == []
    assert amount_unit == "백만원"


def test_table_to_text():
    table_data = {
        "unit": "(단위: 원)",
        "columns": ["계정", "금액"],
        "rows": [["현금및현금성자산", "100"], ["매출채권", None]],
    }

    text = m.table_to_text(table_data)

    assert "단위 (단위: 원)" in text
    assert "컬럼: 계정, 금액" in text
    assert "현금및현금성자산 / 100" in text
    assert "매출채권 / " in text


def test_make_item_canonical_key_for_note():
    rec = {
        "top_section": "주석",
        "note_number": "2",
        "section_title": "현금및현금성자산",
        "section_path": "주석 > 2 > 2.1",
    }

    assert m.make_item_canonical_key(rec) == "주석__2"


def test_make_item_canonical_key_fallback_to_path():
    rec = {
        "top_section": "",
        "note_number": "",
        "section_title": "",
        "section_path": "주석 > 2 > 2.1",
    }

    assert m.make_item_canonical_key(rec) == "주석__2__2.1"


@pytest.mark.parametrize(
    "rec, expected",
    [
        (
            {"top_section": "감사보고서", "section_title": "본문", "section_level": 1},
            "감사보고서 본문형",
        ),
        (
            {"top_section": "재무상태표", "section_title": "재무상태표", "section_level": 1},
            "재무제표 설명형",
        ),
        (
            {"top_section": "주석", "section_title": "주석", "section_level": 1},
            "주석 상위요약형",
        ),
        (
            {"top_section": "주석", "section_title": "현금및현금성자산", "section_level": 2},
            "주석 설명형",
        ),
        (
            {"top_section": "부록", "section_title": "첨부", "section_level": 1},
            "부록 설명형",
        ),
    ],
)
def test_infer_text_type(rec, expected):
    assert m.infer_text_type(rec) == expected


@pytest.mark.parametrize(
    "rec, expected",
    [
        (
            {"top_section": "재무상태표", "section_level": 1, "note_number": ""},
            "대표 재무제표 표",
        ),
        (
            {"top_section": "주석", "section_level": 2, "note_number": "2"},
            "주석 표",
        ),
        (
            {"top_section": "부록", "section_level": 1, "note_number": ""},
            "부록 표",
        ),
        (
            {"top_section": "기타", "section_level": 1, "note_number": ""},
            "일반 표",
        ),
    ],
)
def test_infer_table_type(rec, expected):
    assert m.infer_table_type(rec) == expected


def test_build_text_for_embedding_contains_core_fields():
    rec = {
        "year": 2014,
        "company": "삼성전자",
        "report_type": "감사보고서",
        "top_section": "주석",
        "section_title": "현금및현금성자산",
        "note_number": "2",
        "content_text": "현금및현금성자산은 ...",
        "content_type": "text",
        "amount_unit": "",
        "section_path": "주석 > 2",
    }

    text = m.build_text_for_embedding(rec)

    assert "[삼성전자 2014년 감사보고서]" in text
    assert "현금및현금성자산" in text
    assert "주석 2" in text
    assert "경로: 주석 > 2" in text
    assert "유형: text" in text
    assert "현금및현금성자산은 ..." in text


def test_build_table_text_for_embedding_contains_table_metadata():
    rec = {
        "year": 2014,
        "company": "삼성전자",
        "report_type": "감사보고서",
        "top_section": "재무상태표",
        "section_title": "재무상태표",
        "note_number": "",
        "content_text": "컬럼: 계정, 금액 행: 현금및현금성자산 / 100",
        "content_type": "table",
        "amount_unit": "원",
        "section_path": "재무상태표",
        "section_level": 1,
    }

    text = m.build_table_text_for_embedding(rec)

    assert "대표 재무제표 표" in text
    assert "재무상태표" in text
    assert "삼성전자" in text
    assert "2014년" in text
    assert "단위: 원" in text
    assert "컬럼: 계정, 금액" in text


def test_enrich_records_text_and_table_integration():
    records = [
        {
            "doc_id": "2014_1_text",
            "year": 2014,
            "company": "삼성전자",
            "report_type": "감사보고서",
            "top_section": "주석",
            "note_number": "2",
            "note_title": "현금및현금성자산",
            "section_category": "note_section",
            "section_path": "주석 > 2",
            "section_id": "old",
            "parent_section_id": None,
            "section_level": 2,
            "section_title": "현금및현금성자산",
            "section_type": "note_section",
            "index_style": "numeric",
            "content_type": "text",
            "content_text": "현금및현금성자산은 ...",
            "raw_content": "원본 텍스트",
            "source_file": "sample.json",
            "order_index": 1,
            "has_sub_sections": 0,
            "has_tables": 0,
            "table_data": None,
        },
        {
            "doc_id": "2014_2_table",
            "year": 2014,
            "company": "삼성전자",
            "report_type": "감사보고서",
            "top_section": "재무상태표",
            "note_number": "",
            "note_title": "",
            "section_category": "statement",
            "section_path": "재무상태표",
            "section_id": "old2",
            "parent_section_id": None,
            "section_level": 1,
            "section_title": "재무상태표",
            "section_type": "statement",
            "index_style": "",
            "content_type": "table",
            "content_text": "",
            "raw_content": "원본 표",
            "source_file": "sample.json",
            "order_index": 2,
            "has_sub_sections": 0,
            "has_tables": 1,
            "table_data": {
                "unit": "(단위: 원)",
                "columns": ["계정", "금액", "주석"],
                "rows": [["현금및현금성자산", "100", ["2"]]],
            },
        },
    ]

    enriched = m.enrich_records(records)

    assert len(enriched) == 2

    text_rec = next(r for r in enriched if r["doc_id"] == "2014_1_text")
    table_rec = next(r for r in enriched if r["doc_id"] == "2014_2_table")

    # 공통 후처리
    assert "raw_content" not in text_rec
    assert "raw_content" not in table_rec
    assert text_rec["section_id"] == "2014::주석 > 2"
    assert table_rec["section_id"] == "2014::재무상태표"
    assert isinstance(text_rec["token_count"], int)
    assert isinstance(table_rec["token_count"], int)
    assert text_rec["chunk_id"].startswith("2014_1_text_")
    assert table_rec["chunk_id"].startswith("2014_2_table_")

    # text record
    assert text_rec["is_empty"] is False
    assert text_rec["has_table"] is False
    assert text_rec["text_type"] == "주석 설명형"
    assert "현금및현금성자산은 ..." in text_rec["text_for_embedding"]

    # table record
    assert table_rec["has_table"] is True
    assert table_rec["table_type"] == "대표 재무제표 표"
    assert table_rec["related_notes"] == ["2"]
    assert table_rec["amount_unit"] == "원"
    assert table_rec["content_text"] != ""
    assert "컬럼: 계정, 금액" in table_rec["content_text"]
    assert table_rec["table_data"]["columns"] == ["계정", "금액"]
    assert table_rec["table_data"]["rows"] == [["현금및현금성자산", "100"]]


def test_make_output_path():
    input_file = Path("samsung_2014_flattened.json")
    output_dir = Path("out")
    output_path = m.make_output_path(input_file, output_dir)

    assert output_path == output_dir / "samsung_2014_enriched.json"