"""
JSON → NormalizedDocument 변환 및 in-memory 인덱스 관리.

현재: dict 기반 in-memory store
교체 포인트: _store 에 추가하는 부분을 ChromaDB add() 로 교체 가능
             (retrieval.py 의 ChromaRetriever 와 함께 교체)
"""
import json
from pathlib import Path
from typing import Optional

from app.core.config import settings
from app.models.document import NormalizedDocument


# ── In-memory store ───────────────────────────────────────────────────────────
# doc_id → NormalizedDocument
_store: dict[str, NormalizedDocument] = {}
_indexed_years: set[int] = set()


# ── 공개 조회 API ─────────────────────────────────────────────────────────────

def get_all_documents() -> list[NormalizedDocument]:
    return list(_store.values())


def get_indexed_years() -> list[int]:
    return sorted(_indexed_years)


def get_document_count() -> int:
    return len(_store)


def get_documents_by_year(year: int) -> list[NormalizedDocument]:
    return [d for d in _store.values() if d.year == year]


def find_by_note_ids(year: int, note_ids: list[str]) -> list[NormalizedDocument]:
    """주석 번호로 해당 주석 섹션 문서를 반환. 주석연결형 질문에서 사용."""
    return [
        d for d in _store.values()
        if d.year == year and d.doc_type == "note" and d.section in note_ids
    ]


def structured_lookup(year: int, item_name: str) -> Optional[NormalizedDocument]:
    """
    재무제표에서 과목명으로 직접 조회 (숫자형 질문 우선 경로).
    정확히 일치하는 section 먼저, 없으면 content 포함 검색.
    """
    # 1순위: section 이 정확히 일치
    for doc in _store.values():
        if doc.year == year and doc.doc_type == "financial_statement":
            if doc.section == item_name:
                return doc
    # 2순위: content 포함
    for doc in _store.values():
        if doc.year == year and doc.doc_type == "financial_statement":
            if item_name in doc.content:
                return doc
    return None


# ── 인덱싱 진입점 ─────────────────────────────────────────────────────────────

def ingest_year(year: int, force: bool = False) -> int:
    """
    지정 연도의 processed JSON 을 읽어 NormalizedDocument 로 변환 후 store 에 저장.
    반환값: 이번에 새로 인덱싱된 문서 수 (force=False 이고 이미 있으면 0)
    """
    if year in _indexed_years and not force:
        return 0

    data_path = settings.get_data_path(year)
    if not Path(data_path).exists():
        raise FileNotFoundError(f"Processed data not found: {data_path}")

    with open(data_path, encoding="utf-8") as f:
        raw: dict = json.load(f)

    # 최상위 키가 연도 문자열인 경우 ("2023": {...}) 내부로 진입
    year_data: dict = raw.get(str(year), raw)

    # force 시 해당 연도 문서 먼저 제거
    if force:
        for key in [k for k, v in _store.items() if v.year == year]:
            del _store[key]
        _indexed_years.discard(year)

    count = 0
    for section_name, section_data in year_data.items():
        if not isinstance(section_data, dict):
            continue

        if section_name == "감사보고서":
            count += _index_audit_report(year, section_data)
        elif _is_notes_section(section_name):
            count += _index_notes(year, section_data)
        elif _is_financial_statement(section_name):
            count += _index_financial_statement(year, section_name, section_data)
        else:
            # 기타 섹션 — content 있으면 단순 저장
            content = section_data.get("content", "")
            if content:
                doc = NormalizedDocument(
                    doc_id=f"{section_name}_{year}",
                    doc_type="other",
                    year=year,
                    section=section_name,
                    content=f"[{year}년 {section_name}]\n{content}",
                )
                _store[doc.doc_id] = doc
                count += 1

    _indexed_years.add(year)
    return count


# ── 섹션 유형 판별 ────────────────────────────────────────────────────────────

def _is_financial_statement(name: str) -> bool:
    keywords = ["재무상태표", "손익계산서", "포괄손익", "현금흐름표", "자본변동표"]
    return any(k in name for k in keywords)


def _is_notes_section(name: str) -> bool:
    return "주석" in name


# ── 감사보고서 색인 ───────────────────────────────────────────────────────────

def _index_audit_report(year: int, section_data: dict) -> int:
    """
    감사보고서 sub_sections (감사의견, 핵심감사사항 등) 를 각각 문서로 변환.
    실제 데이터 구조: {"sub_sections": {"감사의견": {"title":..., "content":...}, ...}}
    """
    count = 0
    for sub_name, sub_data in section_data.get("sub_sections", {}).items():
        if not isinstance(sub_data, dict):
            continue
        content = sub_data.get("content", "").strip()
        if not content:
            continue
        doc_id = f"감사보고서_{year}_{sub_name}"
        _store[doc_id] = NormalizedDocument(
            doc_id=doc_id,
            doc_type="audit_report",
            year=year,
            section=sub_name,
            content=f"[{year}년 {sub_name}]\n{content}",
        )
        count += 1
    return count


# ── 재무제표 색인 ─────────────────────────────────────────────────────────────

def _index_financial_statement(year: int, section_name: str, section_data: dict) -> int:
    """
    재무제표 테이블의 각 row 를 문서로 변환.
    실제 데이터 구조: columns = ["과목명","관련주석","당기금액","전기금액"]
                      rows    = [["매출채권", ["4","5"], 27363016000000, 20503223000000], ...]
    """
    count = 0
    for table in section_data.get("tables", []):
        columns: list = table.get("columns", [])
        rows: list = table.get("rows", [])
        unit: str = table.get("unit", "")

        # 컬럼 인덱스 계산
        name_idx = _col_idx(columns, "과목명", fallback=0)
        note_idx = _col_idx(columns, "관련주석")
        amount_cols = {
            col: idx
            for idx, col in enumerate(columns)
            if "금액" in col or col in ("자본금", "이익잉여금", "기타포괄손익누계액", "결손금")
        }

        for row in rows:
            if not isinstance(row, list) or len(row) <= name_idx:
                continue

            item_name: str = str(row[name_idx]).strip()
            if not item_name:
                continue

            # 관련주석 추출
            related_notes: list[str] = []
            if note_idx is not None and note_idx < len(row):
                raw_notes = row[note_idx]
                if isinstance(raw_notes, list):
                    related_notes = [str(n) for n in raw_notes if n]
                elif isinstance(raw_notes, (str, int)) and raw_notes:
                    related_notes = [str(raw_notes)]

            # 금액 추출
            numeric_value: dict[str, int] = {}
            for col_name, col_idx in amount_cols.items():
                if col_idx < len(row) and row[col_idx] is not None:
                    try:
                        numeric_value[col_name] = int(row[col_idx])
                    except (TypeError, ValueError):
                        pass

            # 검색용 content 생성
            parts = [f"[{year}년 {section_name}] {item_name}"]
            if unit:
                parts.append(f"단위: {unit}")
            if numeric_value:
                parts.append(", ".join(f"{k} {v:,}원" for k, v in numeric_value.items()))
            if related_notes:
                parts.append(f"관련주석: {', '.join(related_notes)}")

            doc_id = f"{section_name}_{year}_{item_name}"
            _store[doc_id] = NormalizedDocument(
                doc_id=doc_id,
                doc_type="financial_statement",
                year=year,
                section=item_name,
                content="\n".join(parts),
                numeric_value=numeric_value or None,
                related_notes=related_notes,
            )
            count += 1

    return count


# ── 주석 색인 ─────────────────────────────────────────────────────────────────

def _index_notes(year: int, section_data: dict) -> int:
    """주석 sub_sections 를 재귀적으로 순회하며 문서로 변환."""
    return _index_note_sections(year, section_data.get("sub_sections", {}), parent=None)


def _index_note_sections(
    year: int, sections: dict, parent: Optional[str]
) -> int:
    count = 0
    for key, data in sections.items():
        if not isinstance(data, dict):
            continue

        title = data.get("title", key)
        content = data.get("content", "").strip()

        # 테이블도 텍스트로 변환
        table_texts = [_table_to_text(t) for t in data.get("tables", [])]
        full_content = content
        if table_texts:
            full_content += "\n" + "\n".join(table_texts)

        if full_content.strip():
            doc_id = f"주석_{year}_{key}"
            _store[doc_id] = NormalizedDocument(
                doc_id=doc_id,
                doc_type="note",
                year=year,
                section=key,
                content=f"[{year}년 주석 {key} {title}]\n{full_content}",
                parent_section=parent,
            )
            count += 1

        # 재귀: sub_sections
        sub = data.get("sub_sections", {})
        if sub:
            count += _index_note_sections(year, sub, parent=key)

    return count


# ── 유틸 ──────────────────────────────────────────────────────────────────────

def _col_idx(columns: list, name: str, fallback: Optional[int] = None) -> Optional[int]:
    try:
        return columns.index(name)
    except ValueError:
        return fallback


def _table_to_text(table: dict) -> str:
    lines: list[str] = []
    unit = table.get("unit", "")
    if unit:
        lines.append(f"({unit})")
    cols = table.get("columns", [])
    if cols:
        lines.append(" | ".join(str(c) for c in cols))
    for row in table.get("rows", []):
        lines.append(" | ".join(str(c) for c in row))
    return "\n".join(lines)
