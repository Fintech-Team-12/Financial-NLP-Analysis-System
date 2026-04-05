"""
질문 유형 분류 로직 단위 테스트.
HTTP 레이어 없이 router.classify_question() 를 직접 테스트.
"""
import pytest

from app.services.router import QuestionType, RoutingResult, classify_question


# ── 유형 분류 ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("question", [
    "2023년 매출채권 금액은 얼마인가요?",
    "재고자산 당기금액 알려줘",
    "유형자산 얼마야",
])
def test_classify_numeric(question: str) -> None:
    result = classify_question(question)
    assert result.question_type == QuestionType.NUMERIC


@pytest.mark.parametrize("question", [
    "매출채권 관련 주석 설명해줘",
    "재고자산 회계처리 방법은?",
    "매출채권 회계정책",
])
def test_classify_note_linked(question: str) -> None:
    result = classify_question(question)
    assert result.question_type == QuestionType.NOTE_LINKED


@pytest.mark.parametrize("question", [
    "2023년 감사의견은 무엇인가요?",
    "핵심감사사항을 알려줘",
    "독립된 감사인의 의견은?",
])
def test_classify_descriptive(question: str) -> None:
    result = classify_question(question)
    assert result.question_type == QuestionType.DESCRIPTIVE


# ── 연도 추출 ──────────────────────────────────────────────────────────────────

def test_year_extraction_from_question() -> None:
    result = classify_question("2022년 재고자산 금액은?")
    assert result.extracted_year == 2022


def test_year_extraction_missing_uses_default() -> None:
    result = classify_question("재고자산 금액은?", default_year=2023)
    assert result.extracted_year == 2023


def test_year_extraction_none_when_no_default() -> None:
    result = classify_question("재고자산 금액은?")
    assert result.extracted_year is None


# ── 과목명 추출 ────────────────────────────────────────────────────────────────

def test_item_extraction_found() -> None:
    result = classify_question("2023년 매출채권 설명해줘")
    assert result.extracted_item == "매출채권"


def test_item_extraction_not_found() -> None:
    result = classify_question("감사의견을 알려주세요")
    assert result.extracted_item is None


def test_item_extraction_longer_name_first() -> None:
    """'현금및현금성자산' 이 '현금' 보다 먼저 매칭되어야 한다."""
    result = classify_question("현금및현금성자산 금액은?")
    assert result.extracted_item == "현금및현금성자산"


# ── 반환 타입 ──────────────────────────────────────────────────────────────────

def test_classify_returns_routing_result() -> None:
    result = classify_question("2023년 감사의견은?")
    assert isinstance(result, RoutingResult)
    assert isinstance(result.question_type, QuestionType)
    assert 0.0 <= result.confidence <= 1.0


# ── 관련주석 연결 로직 (indexing 레이어 단위 테스트) ──────────────────────────

def test_note_linking_via_financial_statement(sample_data_dir: str) -> None:
    """
    재무상태표 매출채권 문서에 related_notes=["4","5","7"] 이 설정되어야 한다.
    """
    from app.core.config import settings
    from app.services import indexing

    # 초기화
    indexing._store.clear()
    indexing._indexed_years.clear()
    original = settings.data_dir
    settings.data_dir = sample_data_dir

    try:
        indexing.ingest_year(2023)
        doc = indexing.structured_lookup(2023, "매출채권")
        assert doc is not None
        assert "5" in doc.related_notes   # 주석 5번 포함
        assert "4" in doc.related_notes
    finally:
        settings.data_dir = original
        indexing._store.clear()
        indexing._indexed_years.clear()


def test_find_by_note_ids(sample_data_dir: str) -> None:
    """find_by_note_ids 로 주석 5번 문서를 조회할 수 있어야 한다."""
    from app.core.config import settings
    from app.services import indexing

    indexing._store.clear()
    indexing._indexed_years.clear()
    original = settings.data_dir
    settings.data_dir = sample_data_dir

    try:
        indexing.ingest_year(2023)
        docs = indexing.find_by_note_ids(2023, ["5"])
        assert len(docs) == 1
        assert docs[0].section == "5"
        assert "매출채권" in docs[0].content
    finally:
        settings.data_dir = original
        indexing._store.clear()
        indexing._indexed_years.clear()
