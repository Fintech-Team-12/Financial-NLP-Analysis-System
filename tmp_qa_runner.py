#!/usr/bin/env python3
"""
tmp_qa_runner.py
삼성전자 감사보고서 JSON 기반 간이 QA 터미널.

사용법:
    python tmp_qa_runner.py

지원 질문 유형:
    1. 숫자형     : 2023년 매출채권 금액은?
    2. 설명형     : 2023년 감사의견은?
    3. 주석조회형  : 2023년 매출채권 관련 주석은?

종료: 'exit' 입력
"""

import json
import re
import sys
from pathlib import Path
from typing import Any, Optional

# ── 데이터 경로 (필요 시 아래 경로를 수정) ────────────────────────────────────
DATA_DIR = Path(
    "/Users/snu/Library/Mobile Documents/com~apple~CloudDocs"
    "/SNU_Fintech/자연어처리/project/parsing/output"
)

# ── 재무제표 섹션 이름 ─────────────────────────────────────────────────────────
FINANCIAL_SECTIONS = [
    "재무상태표",
    "손익계산서",
    "포괄손익계산서",
    "현금흐름표",
    "자본변동표",
]

# ── 감사보고서 섹션 키워드 매핑 ───────────────────────────────────────────────
# 질문에 포함된 키워드 → 감사보고서 sub_section 이름
AUDIT_KEYWORDS: dict[str, list[str]] = {
    "감사의견":                          ["감사의견"],
    "감사의견근거":                       ["감사의견근거", "의견근거", "근거"],
    "핵심감사사항":                       ["핵심감사사항", "핵심감사", "핵심"],
    "기타사항":                          ["기타사항"],
    "도입부":                            ["도입부"],
    "재무제표에 대한 경영진과 지배기구의 책임": ["경영진", "지배기구", "경영진의 책임"],
    "재무제표감사에 대한 감사인의 책임":     ["감사인의 책임", "감사인"],
}


# ────────────────────────────────────────────────────────────────────────────
# 1. 데이터 로딩
# ────────────────────────────────────────────────────────────────────────────

def load_all_data(data_dir: Path) -> dict[int, dict]:
    """
    data_dir 안의 audit_report_{year}_structured.json 을 모두 읽는다.
    반환: {연도(int): year_data(dict)}
    """
    result: dict[int, dict] = {}

    for filepath in sorted(data_dir.glob("audit_report_*_structured.json")):
        m = re.search(r"audit_report_(\d{4})_structured", filepath.name)
        if not m:
            continue
        year = int(m.group(1))
        try:
            with open(filepath, encoding="utf-8") as f:
                raw: dict = json.load(f)
            # 최상위 키가 연도 문자열인 경우 ("2023": {...}) 내부로 진입
            year_data = raw.get(str(year), raw)
            result[year] = year_data
        except Exception as e:
            print(f"[경고] {filepath.name} 로드 실패: {e}", file=sys.stderr)

    return result


# ────────────────────────────────────────────────────────────────────────────
# 2. 질문 전처리
# ────────────────────────────────────────────────────────────────────────────

def extract_year(question: str, available_years: list[int]) -> Optional[int]:
    """
    질문에서 4자리 연도를 추출한다.
    명시 연도가 없으면 가장 최신 연도를 반환한다.
    """
    m = re.search(r"(20\d{2})년?", question)
    if m:
        year = int(m.group(1))
        if year in available_years:
            return year
        # 데이터가 없는 연도면 가장 가까운 연도로 대체
        closest = min(available_years, key=lambda y: abs(y - year))
        print(f"  [참고] {year}년 데이터 없음 → {closest}년 데이터를 사용합니다.")
        return closest
    # 연도 미기재 시 최신 연도
    return max(available_years) if available_years else None


def classify_question(question: str) -> str:
    """
    질문을 3가지 유형으로 분류한다.

    반환값:
        "numeric"     - 금액·수치 조회
        "descriptive" - 감사보고서 서술 내용 조회
        "note_linked" - 주석 번호·내용 조회
    """
    q = question

    # 주석 조회형 — 먼저 판단 (금액 질문보다 우선)
    if re.search(r"주석|관련\s*(내용|설명)|회계처리|회계정책|처리방법", q):
        return "note_linked"

    # 감사보고서 설명형
    if re.search(r"감사의견|핵심감사|감사인|감사보고|경영진|지배기구|책임|의견\s*은|근거", q):
        return "descriptive"

    # 숫자형 (기본)
    return "numeric"


def extract_item_keyword(question: str) -> str:
    """
    질문에서 재무제표 과목명으로 쓸 핵심 키워드를 추출한다.
    연도, 질문 어미, 조사, 불필요한 단어를 제거한다.
    """
    q = question
    q = re.sub(r"20\d{2}년?", "", q)                         # 연도 제거
    q = re.sub(r"삼성전자|삼성", "", q)                        # 회사명 제거
    q = re.sub(r"관련\s*(주석|설명|내용|회계처리|회계정책)?", "", q)  # 주석 어구 제거
    q = re.sub(r"회계처리|회계정책|처리방법|인식방법|측정방법", "", q)  # 추가 어구 제거
    q = re.sub(r"금액|얼마|알려줘|알려주세요|보여줘|는\??|은\??|가\??|이\??|\?", "", q)
    q = re.sub(r"\s+", " ", q).strip()
    return q


# ────────────────────────────────────────────────────────────────────────────
# 3. 재무제표 검색
# ────────────────────────────────────────────────────────────────────────────

def _col_idx(columns: list, candidates: list[str]) -> Optional[int]:
    """columns 리스트에서 후보 이름 중 처음 일치하는 인덱스를 반환한다."""
    for c in candidates:
        if c in columns:
            return columns.index(c)
    return None


def find_financial_item(
    year_data: dict,
    keyword: str,
) -> list[dict[str, Any]]:
    """
    모든 재무제표 섹션에서 keyword 를 과목명에 포함하는 row 를 찾는다.

    반환: [{"section": str, "columns": list, "row": list}, ...]
    """
    results = []
    keyword = keyword.strip()
    if not keyword:
        return results

    for section_name in FINANCIAL_SECTIONS:
        section = year_data.get(section_name)
        if not section:
            continue

        for table in section.get("tables", []):
            columns: list = table.get("columns", [])
            rows: list = table.get("rows", [])

            # 과목명 컬럼: "과목명" 또는 "구분" (자본변동표는 "구분")
            name_col = _col_idx(columns, ["과목명", "구분"])
            if name_col is None:
                continue

            for row in rows:
                if not isinstance(row, list) or len(row) <= name_col:
                    continue
                item_name = str(row[name_col])
                if keyword in item_name:  # 부분 포함 매칭
                    results.append({
                        "section": section_name,
                        "columns": columns,
                        "row": row,
                    })

    return results


# ────────────────────────────────────────────────────────────────────────────
# 4. 답변 생성
# ────────────────────────────────────────────────────────────────────────────

def fmt_num(value: Any) -> str:
    """숫자를 천 단위 콤마 포함 문자열로 변환. 변환 불가 시 그대로 반환."""
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return str(value)


# ── 숫자형 ────────────────────────────────────────────────────────────────────

def answer_numeric(year: int, year_data: dict, question: str) -> str:
    """금액 질문: 재무제표에서 과목명을 찾아 금액과 관련주석을 반환한다."""
    keyword = extract_item_keyword(question)
    if not keyword:
        return "  질문에서 과목명을 찾을 수 없습니다.\n  예) 2023년 매출채권 금액은?"

    matches = find_financial_item(year_data, keyword)
    if not matches:
        return (
            f"  '{keyword}' 에 해당하는 항목을 찾을 수 없습니다.\n"
            f"  재무상태표, 손익계산서, 현금흐름표 등을 확인했습니다."
        )

    lines: list[str] = []
    for hit in matches[:3]:  # 최대 3개 항목
        section  = hit["section"]
        columns  = hit["columns"]
        row      = hit["row"]

        name_col = _col_idx(columns, ["과목명", "구분"]) or 0
        note_col = _col_idx(columns, ["관련주석"])
        item_name = str(row[name_col])

        # 관련주석
        notes_str = ""
        if note_col is not None and note_col < len(row):
            raw_notes = row[note_col]
            if isinstance(raw_notes, list) and raw_notes:
                notes_str = ", ".join(str(n) for n in raw_notes)

        # 금액 컬럼 (과목명·구분·관련주석·상위구분 제외한 나머지)
        skip_cols = {"과목명", "구분", "관련주석", "상위구분"}
        amount_lines: list[str] = []
        for idx, col_name in enumerate(columns):
            if col_name in skip_cols:
                continue
            if idx < len(row) and row[idx] not in (None, "", []):
                amount_lines.append(f"    [{col_name}] {fmt_num(row[idx])}")

        lines.append(f"  [연도]   {year}")
        lines.append(f"  [문서]   {section}")
        lines.append(f"  [과목명] {item_name}")
        lines.extend(amount_lines)
        if notes_str:
            lines.append(f"  [관련주석] {notes_str}")
        lines.append("")  # 항목 사이 빈 줄

    return "\n".join(lines).rstrip()


# ── 설명형 ────────────────────────────────────────────────────────────────────

def answer_descriptive(year: int, year_data: dict, question: str) -> str:
    """감사보고서 설명 질문: sub_sections 에서 해당 섹션 내용을 반환한다."""
    audit = year_data.get("감사보고서", {})
    sub   = audit.get("sub_sections", {})

    if not sub:
        return "  감사보고서 섹션을 찾을 수 없습니다."

    target = _match_audit_subsection(question, list(sub.keys()))
    if not target:
        return (
            "  질문에서 해당 섹션을 특정하지 못했습니다.\n"
            f"  사용 가능한 섹션: {', '.join(sub.keys())}"
        )

    content = sub[target].get("content", "").strip()
    if not content:
        return (
            f"  [연도] {year}\n"
            f"  [섹션] 감사보고서 > {target}\n"
            f"  [답변] (내용 없음)"
        )

    return (
        f"  [연도] {year}\n"
        f"  [섹션] 감사보고서 > {target}\n"
        f"  [답변] {content}"
    )


def _match_audit_subsection(question: str, available: list[str]) -> Optional[str]:
    """
    질문 키워드로 감사보고서 sub_section 이름을 매칭한다.
    1순위: AUDIT_KEYWORDS 규칙
    2순위: available 목록 중 질문에 포함된 이름
    3순위: 첫 번째 실질 섹션 (도입부 제외)
    """
    # 1순위
    for key, kws in AUDIT_KEYWORDS.items():
        if key in available and any(kw in question for kw in kws):
            return key
    # 2순위
    for key in available:
        if key in question:
            return key
    # 3순위: 첫 번째 실질 섹션
    for key in available:
        if key != "도입부":
            return key
    return available[0] if available else None


# ── 주석조회형 ────────────────────────────────────────────────────────────────

def answer_note_linked(year: int, year_data: dict, question: str) -> str:
    """
    주석 조회 질문:
    1. 재무제표에서 과목명 → 관련주석 번호 추출
    2. 주석 섹션에서 해당 번호의 내용 출력
    3. 매칭 실패 시 주석 전체에서 키워드 직접 검색
    """
    keyword      = extract_item_keyword(question)
    notes_section: dict = year_data.get("주석", {})

    # ── 재무제표에서 관련주석 번호 추출 ──────────────────────────────────────
    note_ids: list[str] = []
    source_section: Optional[str] = None

    if keyword:
        matches = find_financial_item(year_data, keyword)
        if matches:
            hit      = matches[0]
            note_col = _col_idx(hit["columns"], ["관련주석"])
            source_section = hit["section"]
            if note_col is not None and note_col < len(hit["row"]):
                raw = hit["row"][note_col]
                if isinstance(raw, list):
                    note_ids = [str(n) for n in raw if n]

    # ── 헤더 출력 ─────────────────────────────────────────────────────────────
    lines: list[str] = [f"  [연도] {year}"]
    if source_section:
        lines.append(f"  [재무제표] {source_section}")
    if keyword:
        lines.append(f"  [조회 키워드] {keyword}")

    # ── 관련주석 번호가 있으면 내용 표시 ─────────────────────────────────────
    if note_ids:
        lines.append(f"  [관련주석 번호] {', '.join(note_ids)}")
        lines.append("")

        for nid in note_ids[:5]:  # 너무 길어지지 않게 최대 5개
            note = notes_section.get(nid)
            if not note or not isinstance(note, dict):
                lines.append(f"  ── 주석 {nid}: (데이터 없음)")
                continue

            title   = note.get("title", "").strip()
            content = note.get("content", "").strip()

            lines.append(f"  ── 주석 {nid}: {title}")
            if content:
                preview = content[:250] + ("..." if len(content) > 250 else "")
                lines.append(f"     {preview}")
            else:
                # content가 없으면 sub_sections 제목만 나열
                sub = note.get("sub_sections", {})
                if sub:
                    sub_titles = [f"{k}: {v.get('title','')}" for k, v in list(sub.items())[:3]]
                    lines.append(f"     (하위 항목: {' / '.join(sub_titles)})")
            lines.append("")

    else:
        # 관련주석 번호 없음 → 주석 전체에서 키워드 직접 검색
        if keyword:
            found = _search_notes_by_keyword(notes_section, keyword)
            if found:
                lines.append(f"  [주석 직접 검색] 키워드 '{keyword}' 포함 결과:")
                lines.append("")
                for nid, title, preview in found[:3]:
                    lines.append(f"  ── 주석 {nid}: {title}")
                    lines.append(f"     {preview}")
                    lines.append("")
            else:
                lines.append(f"  '{keyword}' 관련 주석을 찾지 못했습니다.")
        else:
            lines.append("  질문에서 과목명을 찾을 수 없습니다.")

    return "\n".join(lines).rstrip()


def _search_notes_by_keyword(
    notes_section: dict,
    keyword: str,
) -> list[tuple[str, str, str]]:
    """주석 전체에서 keyword 를 포함하는 항목을 반환한다."""
    results: list[tuple[str, str, str]] = []
    for nid, note in notes_section.items():
        if not isinstance(note, dict):
            continue
        title   = note.get("title", "")
        content = note.get("content", "")
        if keyword in (title + content):
            preview = content[:150] + ("..." if len(content) > 150 else "")
            results.append((nid, title.strip(), preview))
    return results


# ────────────────────────────────────────────────────────────────────────────
# 5. 메인 라우터
# ────────────────────────────────────────────────────────────────────────────

def answer(all_data: dict[int, dict], question: str) -> str:
    """
    질문을 분류하고 적절한 답변 함수로 라우팅한다.
    """
    available = sorted(all_data.keys())
    if not available:
        return "  로드된 데이터가 없습니다."

    year = extract_year(question, available)
    if year is None:
        return "  연도를 특정할 수 없습니다. 예: '2023년 매출채권 금액은?'"

    year_data = all_data[year]
    q_type    = classify_question(question)

    if q_type == "numeric":
        return answer_numeric(year, year_data, question)
    elif q_type == "descriptive":
        return answer_descriptive(year, year_data, question)
    else:  # note_linked
        return answer_note_linked(year, year_data, question)


# ────────────────────────────────────────────────────────────────────────────
# 6. REPL 루프
# ────────────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 62)
    print("  삼성전자 감사보고서 QA 터미널")
    print(f"  데이터 경로: {DATA_DIR}")
    print("=" * 62)

    if not DATA_DIR.exists():
        print(f"[오류] 경로를 찾을 수 없습니다: {DATA_DIR}")
        print("  스크립트 상단 DATA_DIR 변수를 수정해주세요.")
        sys.exit(1)

    print("데이터 로딩 중...", end=" ", flush=True)
    all_data = load_all_data(DATA_DIR)
    if not all_data:
        print(f"\n[오류] JSON 파일을 찾지 못했습니다.")
        sys.exit(1)
    years_str = ", ".join(str(y) for y in sorted(all_data.keys()))
    print(f"완료  [{years_str}]\n")

    print("예시 질문:")
    print("  2023년 매출채권 금액은?")
    print("  2023년 감사의견은?")
    print("  2023년 매출채권 관련 주석은?")
    print("  2021년 자산총계 알려줘")
    print("  2023년 핵심감사사항 알려줘")
    print("  (종료: exit)\n")

    while True:
        try:
            question = input("질문: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n종료합니다.")
            break

        if not question:
            continue
        if question.lower() in ("exit", "quit", "종료", "q"):
            print("종료합니다.")
            break

        result = answer(all_data, question)
        print(f"\n답변:\n{result}\n")
        print("-" * 40)


if __name__ == "__main__":
    main()
