"""
질문 유형 분류 및 라우팅.

현재: 키워드 패턴 매칭 기반 (빠르고 의존성 없음)
교체 포인트: classify_question() 내부를 LLM 분류기로 교체 가능
"""
import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class QuestionType(str, Enum):
    NUMERIC = "numeric"           # 특정 항목 금액 조회
    NOTE_LINKED = "note_linked"   # 계정과목의 주석/회계정책 설명 요청
    DESCRIPTIVE = "descriptive"   # 감사의견·핵심감사사항 등 서술형


# ── 재무제표 과목명 (주석 연결 판단에 사용) ───────────────────────────────────
_FINANCIAL_ITEMS: list[str] = [
    "매출채권", "재고자산", "유형자산", "무형자산", "현금및현금성자산", "현금",
    "매입채무", "자본금", "이익잉여금", "부채", "자산", "수익", "비용",
    "손익", "투자자산", "금융자산", "금융부채", "충당부채", "이연법인세",
    "단기금융상품", "미수금", "선급비용", "종속기업", "관계기업", "공동기업",
    "순확정급여자산", "기타포괄손익",
]

# ── 패턴 정의 ─────────────────────────────────────────────────────────────────
_NUMERIC_PATTERNS: list[str] = [
    r"얼마",
    r"금액",
    r"\d+\s*원",
    r"당기금액",
    r"전기금액",
    r"수치",
    r"규모",
    r"얼마나",
]

_NOTE_PATTERNS: list[str] = [
    r"관련\s*(주석|설명|내용)",
    r"회계처리",
    r"회계정책",
    r"어떻게\s*(처리|인식|측정)",
    r"주석\s*\d+",
    r"설명해",
    r"처리방법",
    r"정책",
]

_DESCRIPTIVE_PATTERNS: list[str] = [
    r"감사의견",
    r"핵심감사",
    r"감사인",
    r"감사보고서",
    r"감사범위",
    r"독립된",
    r"의견은",
    r"결론",
    r"위험",
    r"불확실",
]


@dataclass
class RoutingResult:
    question_type: QuestionType
    extracted_year: Optional[int]
    extracted_item: Optional[str]   # 재무제표 과목명 (숫자/주석형에서 추출)
    confidence: float               # 0~1 (LLM 교체 후 확률값으로 대체 가능)


def classify_question(
    question: str,
    default_year: Optional[int] = None,
) -> RoutingResult:
    """
    질문을 3가지 유형으로 분류.

    교체 방법: 함수 본문을 LLM 호출로 교체하되 반환 타입(RoutingResult)은 유지.
    """
    q = question.strip()

    extracted_year = _extract_year(q) or default_year
    extracted_item = _extract_financial_item(q)

    numeric_score = _score(q, _NUMERIC_PATTERNS)
    note_score = _score(q, _NOTE_PATTERNS)
    desc_score = _score(q, _DESCRIPTIVE_PATTERNS)

    # 과목명 + 금액 키워드 → 숫자형
    if extracted_item and numeric_score > 0:
        return RoutingResult(QuestionType.NUMERIC, extracted_year, extracted_item, 0.9)

    # 과목명 + 주석/설명 키워드 → 주석연결형
    if extracted_item and (note_score > 0 or "관련" in q or "설명" in q):
        return RoutingResult(QuestionType.NOTE_LINKED, extracted_year, extracted_item, 0.85)

    # 감사보고서 키워드 → 설명형
    if desc_score > 0:
        return RoutingResult(QuestionType.DESCRIPTIVE, extracted_year, None, 0.8)

    # 과목명만 있고 키워드 불명확 → 숫자형 기본
    if extracted_item:
        return RoutingResult(QuestionType.NUMERIC, extracted_year, extracted_item, 0.6)

    # 기본값 → 설명형
    return RoutingResult(QuestionType.DESCRIPTIVE, extracted_year, None, 0.5)


# ── 내부 헬퍼 ─────────────────────────────────────────────────────────────────

def _score(question: str, patterns: list[str]) -> int:
    return sum(1 for p in patterns if re.search(p, question))


def _extract_year(question: str) -> Optional[int]:
    m = re.search(r"(20\d{2})년?", question)
    return int(m.group(1)) if m else None


def _extract_financial_item(question: str) -> Optional[str]:
    # 긴 항목명 먼저 검사 (예: "현금및현금성자산" vs "현금")
    for item in sorted(_FINANCIAL_ITEMS, key=len, reverse=True):
        if item in question:
            return item
    return None
