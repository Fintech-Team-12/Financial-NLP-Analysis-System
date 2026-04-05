from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


# =========================================================
# 경로 설정
# =========================================================
# 이 파일 위치: chroma/enrich_flattened_for_rag.py
CHROMA_DIR = Path(__file__).resolve().parent
INPUT_DIR = CHROMA_DIR / "flattened_data"
OUTPUT_DIR = CHROMA_DIR / "enriched_data"


# =========================================================
# 토큰 카운터
# =========================================================
try:
    import tiktoken

    _ENCODER = tiktoken.get_encoding("cl100k_base")

    def count_tokens(text: str) -> int:
        return len(_ENCODER.encode(text or ""))

except ImportError:
    def count_tokens(text: str) -> int:
        """
        tiktoken 미설치 환경용 근사치.
        한국어는 대략 1글자 ~ 1.2토큰,
        기타 문자는 대략 0.25토큰으로 근사.
        """
        text = text or ""
        korean = sum(1 for c in text if "\uAC00" <= c <= "\uD7A3")
        others = len(text) - korean
        return int(korean * 1.2 + others * 0.25)


# =========================================================
# 기본 유틸
# =========================================================
def normalize_path(path_value: str) -> str:
    if not path_value:
        return ""
    parts = [part.strip() for part in str(path_value).split(">")]
    parts = [part for part in parts if part]
    return " > ".join(parts)


def make_parent_path(section_path: str) -> str:
    section_path = normalize_path(section_path)
    if not section_path or " > " not in section_path:
        return ""
    return " > ".join(section_path.split(" > ")[:-1])


def make_section_uid(year: Any, section_path: str) -> str:
    """
    전역 유일 section_id 생성.
    예: 2014::주석 > 2 > 2.6 > 가.
    """
    norm_path = normalize_path(section_path)
    return f"{year}::{norm_path}" if norm_path else f"{year}::ROOT"


def make_chunk_id(doc_id: str, order_index: Any) -> str:
    """
    사람이 추적 가능하게 doc_id 포함.
    """
    base = f"{doc_id}_{order_index}"
    digest = hashlib.sha256(base.encode("utf-8")).hexdigest()[:8]
    return f"{doc_id}_{digest}"

'''
def extract_amount_unit(raw_unit: str) -> str | None:
    """
    "(단위: 원)" -> "원"
    "(단위 : 백만원)" -> "백만원"
    """
    if not raw_unit:
        return None

    raw_unit = str(raw_unit).strip()
    match = re.search(r"단위\s*:\s*([^)]+)", raw_unit)
    if match:
        return match.group(1).strip()

    cleaned = raw_unit.replace("(", "").replace(")", "").strip()
    return cleaned or None
'''

def extract_amount_unit(raw_unit: str) -> str | None:
    """
    "(단위: 원)" -> "원"
    "(단위: 주, 원)" -> "주, 원"  # 🟢 복합 단위 대응
    """
    if not raw_unit:
        return None

    raw_unit = str(raw_unit).strip()
    
    # 1. '단위' 키워드 뒤의 내용을 추출 (반각 : 및 전각 ： 모두 대응)
    match = re.search(r"단위\s*[:：]\s*([^)]+)", raw_unit)
    if match:
        return match.group(1).strip()

    # 2. '단위'라는 글자가 없더라도 괄호 안의 내용만 깔끔하게 추출
    cleaned = raw_unit.replace("(", "").replace(")", "").replace("단위", "").replace(":", "").replace("：", "").strip()
    
    return cleaned or None

# =========================================================
# 구조 ID 재생성
# =========================================================
def rebuild_ids(records: list[dict]) -> list[dict]:
    rebuilt = []

    for rec in records:
        new_rec = dict(rec)

        year = new_rec.get("year", "")
        section_path = normalize_path(new_rec.get("section_path", ""))
        parent_path = make_parent_path(section_path)

        new_rec["section_path"] = section_path
        new_rec["section_id"] = make_section_uid(year, section_path)
        new_rec["parent_section_id"] = (
            make_section_uid(year, parent_path) if parent_path else None
        )

        rebuilt.append(new_rec)

    return rebuilt


# =========================================================
# leaf 계산
# =========================================================
def compute_leaf_flags(records: list[dict]) -> list[bool]:
    normalized_paths = [normalize_path(r.get("section_path", "")) for r in records]
    leaf_flags = []

    for current_path in normalized_paths:
        if not current_path:
            leaf_flags.append(True)
            continue

        prefix = current_path + " > "
        has_child = any(
            other_path != current_path and other_path.startswith(prefix)
            for other_path in normalized_paths
        )
        leaf_flags.append(not has_child)

    return leaf_flags


# =========================================================
# 빈 content_text 처리
# =========================================================
def build_parent_child_map(records: list[dict]) -> dict[str, list[dict]]:
    mapping: dict[str, list[dict]] = {}
    for rec in records:
        pid = rec.get("parent_section_id")
        if pid is not None:
            mapping.setdefault(pid, []).append(rec)
    return mapping


def make_structural_context_text(rec: dict, child_records: list[dict]) -> str:
    """
    자식 내용을 복붙하지 않고, 구조 컨텍스트 중심으로 content_text 생성.
    """
    top_section = str(rec.get("top_section", "")).strip()
    note_number = str(rec.get("note_number", "")).strip()
    section_title = str(rec.get("section_title", "")).strip()

    child_titles = []
    for child in child_records[:5]:
        title = str(child.get("section_title", "")).strip()
        if title and title not in child_titles:
            child_titles.append(title)

    parts = []
    if top_section:
        parts.append(top_section)
    if note_number:
        parts.append(f"주석 {note_number}")
    if section_title:
        parts.append(section_title)

    prefix = " > ".join(parts).strip()

    if child_titles:
        return f"{prefix}. 하위 섹션: {', '.join(child_titles)}"
    return prefix


def handle_empty_content(records: list[dict]) -> list[dict]:
    """
    - 빈 content_text + 자식 있음 -> 구조 컨텍스트 기반 content 생성
    - 빈 content_text + 자식 없음 -> 제거
    """
    parent_child = build_parent_child_map(records)
    result = []

    for rec in records:
        content_text = str(rec.get("content_text", "") or "").strip()
        if content_text:
            result.append(rec)
            continue

        children = parent_child.get(rec["section_id"], [])
        if children:
            filled_text = make_structural_context_text(rec, children)
            new_rec = dict(rec)
            new_rec["content_text"] = filled_text
            new_rec["_enriched_empty_fill"] = True
            result.append(new_rec)
        else:
            print(
                f"[REMOVE EMPTY] section_id={rec.get('section_id')} "
                f"title={rec.get('section_title')!r}",
                file=sys.stderr,
            )

    return result


# =========================================================
# raw_content 제거
# =========================================================
def drop_raw_content(records: list[dict]) -> list[dict]:
    return [{k: v for k, v in rec.items() if k != "raw_content"} for rec in records]


# =========================================================
# table_data 정규화
# =========================================================
def find_note_col_index(columns: list[str]) -> int | None:
    for i, col in enumerate(columns):
        if "주석" in str(col):
            return i
    return None


def is_list_col(rows: list[list], col_idx: int) -> bool:
    return any(
        isinstance(row[col_idx], list)
        for row in rows
        if isinstance(row, list) and col_idx < len(row)
    )


def normalize_table_data(table_data: dict | None) -> tuple[dict | None, list[str], str | None]:
    """
    반환:
      cleaned_table_data, related_notes, amount_unit
    """
    if table_data is None:
        return None, [], None

    table_copy = json.loads(json.dumps(table_data, ensure_ascii=False))

    columns = table_copy.get("columns", []) or []
    rows = table_copy.get("rows", []) or []
    amount_unit = extract_amount_unit(table_copy.get("unit", ""))

    note_idx = find_note_col_index(columns)

    if note_idx is None:
        for i in range(len(columns)):
            if rows and is_list_col(rows, i):
                note_idx = i
                break

    if note_idx is None:
        return table_copy, [], amount_unit

    all_notes: list[str] = []
    clean_rows: list[list] = []

    for row in rows:
        if not isinstance(row, list):
            clean_rows.append(row)
            continue

        row_notes = []
        if note_idx < len(row):
            cell = row[note_idx]
            if isinstance(cell, list):
                row_notes = [str(x).strip() for x in cell if str(x).strip()]
            elif cell not in [None, "", []]:
                row_notes = [str(cell).strip()]

        for note in row_notes:
            if note not in all_notes:
                all_notes.append(note)

        cleaned_row = [v for i, v in enumerate(row) if i != note_idx]
        clean_rows.append(cleaned_row)

    clean_columns = [c for i, c in enumerate(columns) if i != note_idx]

    clean_table = {
        **table_copy,
        "columns": clean_columns,
        "rows": clean_rows,
    }

    return clean_table, all_notes, amount_unit


def table_to_text(table_data: dict | None) -> str:
    if not table_data:
        return ""

    unit = str(table_data.get("unit", "")).strip()
    columns = table_data.get("columns", []) or []
    rows = table_data.get("rows", []) or []

    parts = []

    if unit:
        parts.append(f"단위 {unit}")

    if columns:
        parts.append("컬럼: " + ", ".join(map(str, columns)))

    row_texts = []
    for row in rows:
        if isinstance(row, list):
            row_texts.append(" / ".join("" if x is None else str(x) for x in row))
        else:
            row_texts.append(str(row))

    if row_texts:
        parts.append("행: " + " | ".join(row_texts))

    return " ".join(parts).strip()


# =========================================================
# canonical key
# =========================================================
def make_item_canonical_key(rec: dict) -> str:
    top = str(rec.get("top_section", "")).strip()
    title = str(rec.get("section_title", "")).strip()
    note_number = str(rec.get("note_number", "")).strip()
    section_path = normalize_path(rec.get("section_path", ""))

    top_norm = re.sub(r"\s+", "_", top)
    title_norm = re.sub(r"\s+", "_", title)

    if top == "주석" and note_number:
        return f"{top_norm}__{note_number}"

    if top_norm and title_norm:
        return f"{top_norm}__{title_norm}"

    if section_path:
        return re.sub(r"\s+", "_", section_path.replace(" > ", "__"))

    return "UNKNOWN"


# =========================================================
# embedding text
# =========================================================
def clean_field(value) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() == "none":
        return ""
    return text


def infer_text_type(rec: dict) -> str:
    top_section = clean_field(rec.get("top_section", ""))
    section_title = clean_field(rec.get("section_title", ""))
    section_level = rec.get("section_level")

    if top_section == "감사보고서":
        return "감사보고서 본문형"

    if top_section in ["재무상태표", "손익계산서", "포괄손익계산서", "자본변동표", "현금흐름표"]:
        return "재무제표 설명형"

    if top_section == "주석":
        if section_level == 1 or section_title == "주석":
            return "주석 상위요약형"
        return "주석 설명형"

    if top_section == "부록":
        return "부록 설명형"

    return "일반 설명형"

def infer_table_type(rec: dict) -> str:
    top_section = clean_field(rec.get("top_section", ""))
    section_level = rec.get("section_level")
    note_number = clean_field(rec.get("note_number", ""))

    # 대표 재무제표 표
    if top_section in ["재무상태표", "손익계산서", "포괄손익계산서", "자본변동표", "현금흐름표"] and section_level == 1:
        return "대표 재무제표 표"

    # 주석 표
    if top_section == "주석":
        return "주석 표"

    # 부록 표
    if top_section == "부록":
        return "부록 표"

    return "일반 표"

def build_table_text_for_embedding(rec: dict) -> str:
    year = clean_field(rec.get("year", ""))
    company = clean_field(rec.get("company", ""))
    report_type = clean_field(rec.get("report_type", ""))
    top_section = clean_field(rec.get("top_section", ""))
    section_title = clean_field(rec.get("section_title", ""))
    note_number = clean_field(rec.get("note_number", ""))
    content_text = clean_field(rec.get("content_text", ""))
    content_type = clean_field(rec.get("content_type", ""))
    amount_unit = clean_field(rec.get("amount_unit", ""))
    section_path = normalize_path(rec.get("section_path", ""))

    table_type = infer_table_type(rec)

    header_parts = []

    # 표 타입을 제일 앞에 넣어서 대표성 강조
    if table_type:
        header_parts.append(table_type)

    if section_title:
        header_parts.append(section_title)

    if top_section and top_section not in header_parts:
        header_parts.append(top_section)

    if note_number:
        header_parts.append(f"주석 {note_number}")

    if company:
        header_parts.append(company)

    if year:
        header_parts.append(f"{year}년")

    if report_type:
        header_parts.append(report_type)

    header = " | ".join([p for p in header_parts if p])

    meta_parts = []
    if section_path:
        meta_parts.append(f"경로: {section_path}")
    if content_type:
        meta_parts.append(f"유형: {content_type}")
    if amount_unit:
        meta_parts.append(f"단위: {amount_unit}")

    pieces = []
    if header:
        pieces.append(header)
    if meta_parts:
        pieces.append(" | ".join(meta_parts))
    if content_text:
        pieces.append(content_text)

    return "\n".join(pieces).strip()
'''
def build_text_for_embedding(rec: dict) -> str:
    year = clean_field(rec.get("year", ""))
    company = clean_field(rec.get("company", ""))
    report_type = clean_field(rec.get("report_type", ""))
    top_section = clean_field(rec.get("top_section", ""))
    section_title = clean_field(rec.get("section_title", ""))
    note_number = clean_field(rec.get("note_number", ""))
    content_text = clean_field(rec.get("content_text", ""))
    content_type = clean_field(rec.get("content_type", ""))
    amount_unit = clean_field(rec.get("amount_unit", ""))
    section_path = normalize_path(rec.get("section_path", ""))

    text_type = infer_text_type(rec)

    header_parts = []

    # 제목을 맨 앞에
    if section_title:
        header_parts.append(section_title)

    # 문서 성격 강조
    if text_type:
        header_parts.append(text_type)

    # 재무제표 계열이면 top_section도 강조
    if top_section and top_section not in header_parts:
        header_parts.append(top_section)

    if note_number:
        header_parts.append(f"주석 {note_number}")

    if company:
        header_parts.append(company)

    if year:
        header_parts.append(f"{year}년")

    if report_type:
        header_parts.append(report_type)

    header = " | ".join([p for p in header_parts if p])

    meta_parts = []
    if section_path:
        meta_parts.append(f"경로: {section_path}")
    if content_type:
        meta_parts.append(f"유형: {content_type}")
    if amount_unit:
        meta_parts.append(f"단위: {amount_unit}")

    pieces = []
    if header:
        pieces.append(header)
    if meta_parts:
        pieces.append(" | ".join(meta_parts))
    if content_text:
        pieces.append(content_text)

    return "\n".join(pieces).strip()
'''
def build_text_for_embedding(rec: dict) -> str:
    year = clean_field(rec.get("year", ""))
    company = clean_field(rec.get("company", ""))
    report_type = clean_field(rec.get("report_type", ""))
    top_section = clean_field(rec.get("top_section", ""))
    section_title = clean_field(rec.get("section_title", ""))
    note_number = clean_field(rec.get("note_number", ""))
    content_text = clean_field(rec.get("content_text", ""))
    content_type = clean_field(rec.get("content_type", ""))
    amount_unit = clean_field(rec.get("amount_unit", ""))
    section_path = normalize_path(rec.get("section_path", ""))

    text_type = infer_text_type(rec)

    header_parts = []

    # 1. 최우선 식별자: 누구의 어떤 보고서인지 명확히!
    if company and year:
        header_parts.append(f"[{company} {year}년 {report_type}]")
    
    # 2. 핵심 항목: 은정님이 정제한 그 제목!
    if section_title:
        header_parts.append(section_title)

    # 3. 보조 정보: 주석 번호나 섹션 유형 (중복 피하기)
    if note_number:
        header_parts.append(f"주석 {note_number}")
    elif top_section and top_section not in section_title:
        header_parts.append(top_section)

    header = " | ".join([p for p in header_parts if p])

    meta_parts = []
    if section_path:
        meta_parts.append(f"경로: {section_path}")
    if content_type:
        meta_parts.append(f"유형: {content_type}")
    if amount_unit:
        meta_parts.append(f"단위: {amount_unit}")

    pieces = []
    if header:
        pieces.append(header)
    if meta_parts:
        pieces.append(" | ".join(meta_parts))
    if content_text:
        pieces.append(content_text)

    return "\n".join(pieces).strip()



# =========================================================
# 메인 enrich
# =========================================================
def enrich_records(records: list[dict]) -> list[dict]:
    print(f"입력 레코드 수: {len(records)}", file=sys.stderr)

    # 1) path 정리 + 고유 ID 재생성
    records = rebuild_ids(records)

    # 2) 빈 content 처리
    records = handle_empty_content(records)
    print(f"빈 content 처리 후 레코드 수: {len(records)}", file=sys.stderr)

    # 3) raw_content 제거
    records = drop_raw_content(records)

    # 4) leaf 계산
    leaf_flags = compute_leaf_flags(records)

    enriched = []
    for rec, is_leaf in zip(records, leaf_flags):
        new_rec = dict(rec)

        # table 정규화
        cleaned_table, related_notes, amount_unit = normalize_table_data(
            new_rec.get("table_data")
        )
        new_rec["table_data"] = cleaned_table
        new_rec["related_notes"] = related_notes
        new_rec["amount_unit"] = amount_unit

        # table이면 content_text 보강
        content_type = str(new_rec.get("content_type", "")).strip()
        content_text = str(new_rec.get("content_text", "") or "").strip()

        if content_type == "table":
            serialized = table_to_text(cleaned_table)
            if serialized:
                new_rec["content_text"] = serialized
                content_text = serialized

        new_rec["is_empty"] = (content_text == "")
        new_rec["is_leaf"] = is_leaf
        new_rec["char_len"] = len(content_text)
        new_rec["has_table"] = cleaned_table is not None
        new_rec["item_canonical_key"] = make_item_canonical_key(new_rec)

        new_rec["text_type"] = infer_text_type(new_rec)

        if content_type == "table":
            new_rec["table_type"] = infer_table_type(new_rec)
            text_for_embedding = build_table_text_for_embedding(new_rec)
        else:
            new_rec["text_type"] = infer_text_type(new_rec)
            text_for_embedding = build_text_for_embedding(new_rec)

        new_rec["text_for_embedding"] = text_for_embedding
        new_rec["embedding_text"] = text_for_embedding
        new_rec["token_count"] = count_tokens(text_for_embedding)
        new_rec["chunk_id"] = make_chunk_id(
            str(new_rec.get("doc_id", "")),
            new_rec.get("order_index", 0),
        )

        enriched.append(new_rec)

    print(f"최종 enriched 레코드 수: {len(enriched)}", file=sys.stderr)
    return enriched



# =========================================================
# 파일 처리
# =========================================================
def iter_input_files(input_dir: Path) -> list[Path]:
    return sorted(input_dir.glob("*_flattened.json"))


def make_output_path(input_file: Path, output_dir: Path) -> Path:
    name = input_file.name.replace("_flattened.json", "_enriched.json")
    return output_dir / name


def process_one_file(input_file: Path, output_dir: Path) -> None:
    with input_file.open("r", encoding="utf-8") as f:
        records = json.load(f)

    if not isinstance(records, list):
        raise ValueError(f"{input_file} 는 list 형태 JSON이어야 합니다.")

    enriched = enrich_records(records)

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = make_output_path(input_file, output_dir)

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(enriched, f, ensure_ascii=False, indent=2)

    max_tokens = max((r.get("token_count", 0) for r in enriched), default=0)
    print(
        f"[SAVE] {output_path} | records={len(enriched)} | max_token_count={max_tokens}",
        file=sys.stderr,
    )


def main() -> None:
    if not INPUT_DIR.exists():
        raise FileNotFoundError(f"입력 폴더가 없습니다: {INPUT_DIR}")

    input_files = iter_input_files(INPUT_DIR)
    if not input_files:
        raise FileNotFoundError(f"{INPUT_DIR} 안에 *_flattened.json 파일이 없습니다.")

    print(f"입력 폴더: {INPUT_DIR}", file=sys.stderr)
    print(f"출력 폴더: {OUTPUT_DIR}", file=sys.stderr)
    print(f"처리 파일 수: {len(input_files)}", file=sys.stderr)

    for input_file in input_files:
        print(f"\n[PROCESS] {input_file.name}", file=sys.stderr)
        process_one_file(input_file, OUTPUT_DIR)

    print("\n모든 enrich 작업이 완료되었습니다.", file=sys.stderr)


if __name__ == "__main__":
    main()