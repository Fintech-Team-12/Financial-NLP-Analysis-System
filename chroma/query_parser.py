from __future__ import annotations

import re
from typing import Any


# 설명형 힌트
TEXT_HINT_PATTERNS = [
    r"설명",
    r"의미",
    r"무엇",
    r"뭐야",
    r"뭔가",
    r"책임",
    r"개념",
    r"본문",
]

# 표/수치형 힌트
TABLE_HINT_PATTERNS = [
    r"\b표\b",          # 영어 단어 경계는 한글에 약해서 아래 보조 규칙도 같이 씀
    r"표\s*보여",
    r"표\s*알려",
    r"수치",
    r"금액",
    r"얼마",
    r"내역",
    r"숫자",
    r"행",
    r"컬럼",
    r"데이터",
]

# top_section/section_title 힌트로 확장 가능한 대표 섹션명
KNOWN_SECTION_KEYWORDS = [
    "감사의견",
    "감사보고서",
    "재무제표에 대한 경영진의 책임",
    "감사인의 책임",
    "재무상태표",
    "손익계산서",
    "포괄손익계산서",
    "자본변동표",
    "현금흐름표",
    "현금및현금성자산",
    "유형자산",
    "법인세비용",
]


def extract_year(query: str) -> int | None:
    match = re.search(r"(20\d{2})년?", query)
    if match:
        return int(match.group(1))
    return None


def contains_standalone_table_hint(query: str) -> bool:
    """
    '표'가 독립적으로 쓰인 경우만 table 힌트로 본다.
    예:
      - '유형자산 표 보여줘' -> True
      - '재무제표에 대한 책임' -> False
    """
    # 재무제표는 table 힌트로 취급하지 않음
    protected_words = ["재무제표", "대표", "발표"]
    replaced = query
    for word in protected_words:
        replaced = replaced.replace(word, "")

    # 보조 규칙: 공백/문장부호 기준으로 '표'가 독립적으로 있는지 확인
    if re.search(r"(^|[\s\(\)\[\],.!?])표($|[\s\(\)\[\],.!?])", replaced):
        return True

    # "표 보여줘", "표 알려줘" 같은 형태
    if re.search(r"표\s*(보여|알려|찾아|출력)", replaced):
        return True

    return False


def detect_table_intent(query: str) -> bool:
    if contains_standalone_table_hint(query):
        return True

    for pattern in TABLE_HINT_PATTERNS:
        if re.search(pattern, query):
            return True
    return False


def detect_text_intent(query: str) -> bool:
    for pattern in TEXT_HINT_PATTERNS:
        if re.search(pattern, query):
            return True
    return False


def clean_query_text(query: str) -> str:
    cleaned = query.strip()

    # 연도 제거
    cleaned = re.sub(r"20\d{2}년?", " ", cleaned)

    # 불필요 표현 제거
    removable_patterns = [
        r"관련",
        r"내용",
        r"설명해줘",
        r"설명해\s*줘",
        r"설명",
        r"알려줘",
        r"알려\s*줘",
        r"보여줘",
        r"보여\s*줘",
        r"찾아줘",
        r"찾아\s*줘",
        r"무엇이야",
        r"무엇인가",
        r"무엇",
        r"뭐야",
        r"뭔가",
        r"인가요",
        r"인가",
        r"이야",
        r"에 대한",
        r"에대한",
        r"의",
        r"\?",
    ]

    for pattern in removable_patterns:
        cleaned = re.sub(pattern, " ", cleaned)

    # table 힌트 단어도 clean query에서는 제거
    table_words_to_remove = [
        r"\b표\b",
        r"수치",
        r"금액",
        r"얼마",
        r"내역",
        r"숫자",
        r"데이터",
        r"행",
        r"컬럼",
    ]
    for pattern in table_words_to_remove:
        cleaned = re.sub(pattern, " ", cleaned)

    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def extract_section_keyword(clean_query: str) -> str:
    """
    clean_query에 대표 섹션명이 들어 있으면 그대로 유지.
    없으면 clean_query 자체를 반환.
    """
    for keyword in sorted(KNOWN_SECTION_KEYWORDS, key=len, reverse=True):
        if keyword in clean_query:
            return keyword
    return clean_query


def infer_intent(
    *,
    query: str,
    want_text: bool,
    want_table: bool,
) -> str:
    if want_table and not want_text:
        return "table_lookup"
    if want_text and not want_table:
        return "text_explanation"
    if want_table and want_text:
        return "mixed"
    return "general_search"


def adjust_intent_by_semantics(
    *,
    raw_query: str,
    clean_query: str,
    want_text: bool,
    want_table: bool,
) -> tuple[bool, bool]:
    """
    규칙 보정:
    - '수치/금액/내역/얼마'가 있으면 table 우선
    - '설명/책임/무엇/뭐야'가 있으면 text 우선
    - 둘 다 있으면 mixed 유지
    """
    numeric_like = bool(re.search(r"수치|금액|내역|얼마|숫자", raw_query))
    explain_like = bool(re.search(r"설명|책임|무엇|뭐야|개념|본문", raw_query))

    if numeric_like and not explain_like:
        return False, True

    if explain_like and not numeric_like:
        return True, False

    return want_text, want_table


def parse_query(query: str) -> dict[str, Any]:
    year = extract_year(query)

    want_table = detect_table_intent(query)
    want_text = detect_text_intent(query)

    # 의미 기반 추가 보정
    want_text, want_table = adjust_intent_by_semantics(
        raw_query=query,
        clean_query=query,
        want_text=want_text,
        want_table=want_table,
    )

    # 아무 힌트가 없으면 기본은 text 우선 일반 검색
    if not want_text and not want_table:
        want_text = True

    clean_query = clean_query_text(query)
    clean_query = extract_section_keyword(clean_query)

    intent = infer_intent(
        query=query,
        want_text=want_text,
        want_table=want_table,
    )

    return {
        "raw_query": query,
        "clean_query": clean_query,
        "year": year,
        "want_text": want_text,
        "want_table": want_table,
        "intent": intent,
    }


if __name__ == "__main__":
    sample_queries = [
        "2014년 현금및현금성자산 알려줘",
        "유형자산 표 보여줘",
        "재무제표에 대한 경영진의 책임이 뭐야?",
        "법인세비용 수치 알려줘",
        "포괄손익계산서 관련 내용 설명해줘",
        "재무상태표 표 보여줘",
    ]

    for q in sample_queries:
        print("=" * 100)
        print(parse_query(q))