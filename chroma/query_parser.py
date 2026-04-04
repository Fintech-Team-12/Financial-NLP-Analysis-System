# 사용자의 질문을 검색 가능한 구조로 바꾸는 역할
# retrieval 전에 질문을 한 번 정리하는 단계

import re
from typing import Any


TEXT_HINT_WORDS = [
    "설명", "의미", "책임", "무엇", "뭐야", "알려줘", "개념", "내용"
]

TABLE_HINT_WORDS = [
    "표", "내역", "수치", "금액", "얼마", "행", "컬럼", "데이터", "숫자"
]


def extract_year(query: str) -> int | None:
    match = re.search(r"(20\d{2})년?", query)
    if match:
        return int(match.group(1))
    return None


def detect_table_intent(query: str) -> bool:
    return any(word in query for word in TABLE_HINT_WORDS)


def detect_text_intent(query: str) -> bool:
    return any(word in query for word in TEXT_HINT_WORDS)


def clean_query_text(query: str) -> str:
    cleaned = query.strip()

    # 연도 제거
    cleaned = re.sub(r"20\d{2}년?", " ", cleaned)

    # 질문형 표현 제거
    removable_patterns = [
        r"알려줘",
        r"보여줘",
        r"설명해줘",
        r"설명",
        r"뭐야",
        r"무엇이야",
        r"무엇인가",
        r"무엇",
        r"관련",
    ]

    for pattern in removable_patterns:
        cleaned = re.sub(pattern, " ", cleaned)

    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def infer_intent(query: str, want_text: bool, want_table: bool) -> str:
    if want_table and not want_text:
        return "table_lookup"
    if want_text and not want_table:
        return "text_explanation"
    if want_table and want_text:
        return "mixed"
    return "general_search"


def parse_query(query: str) -> dict[str, Any]:
    year = extract_year(query)
    want_table = detect_table_intent(query)
    want_text = detect_text_intent(query)

    # 아무 힌트가 없으면 기본은 설명형 + 일반 검색으로 둠
    if not want_table and not want_text:
        want_text = True

    clean_query = clean_query_text(query)
    intent = infer_intent(query, want_text, want_table)

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
    ]

    for q in sample_queries:
        print("=" * 80)
        print(parse_query(q))