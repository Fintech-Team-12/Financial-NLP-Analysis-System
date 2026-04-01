import json
import re
from pathlib import Path
from typing import Any


def load_json(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data: list[dict[str, Any]], path: str) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def clean_text(text: Any) -> str:
    """검색용 텍스트 정제"""
    if text is None:
        return ""
    text = str(text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def detect_index_style(section_id: str) -> str:
    """section id 형식 분류"""
    if re.fullmatch(r"\(\d+\)", section_id):
        return "paren_numeric"
    if re.fullmatch(r"[가-힣]\.", section_id):
        return "korean"
    if re.fullmatch(r"\d+(\.\d+)*", section_id):
        return "numeric"
    return "other"


def detect_section_type(section_level: int, has_sub_sections: bool, has_tables: bool) -> str:
    """섹션 유형 분류"""
    if has_tables and not has_sub_sections:
        return "table_section"
    if section_level == 1:
        return "note_section"
    return "subsection"


def table_to_text(table: dict[str, Any], section_title: str = "") -> str:
    """
    표를 검색용 텍스트로 변환
    """
    unit = clean_text(table.get("unit", ""))
    columns = table.get("columns", [])
    rows = table.get("rows", [])
    annotations = table.get("annotations", [])

    parts = []

    if section_title:
        parts.append(f"[{section_title}]")

    if unit:
        parts.append(f"단위: {unit}")

    if columns:
        parts.append("컬럼: " + ", ".join(clean_text(col) for col in columns))

    row_texts = []
    for row in rows:
        if not isinstance(row, list):
            continue

        if columns and len(columns) == len(row):
            pairs = [f"{clean_text(col)}: {clean_text(cell)}" for col, cell in zip(columns, row)]
            row_texts.append(" / ".join(pairs))
        else:
            row_texts.append(" / ".join(clean_text(cell) for cell in row))

    if row_texts:
        parts.append("행: " + " | ".join(row_texts))

    if annotations:
        ann_texts = []
        for ann in annotations:
            marker = clean_text(ann.get("marker", ""))
            text = clean_text(ann.get("text", ""))
            if marker or text:
                ann_texts.append(f"{marker} {text}".strip())
        if ann_texts:
            parts.append("주석: " + " | ".join(ann_texts))

    return clean_text(" ".join(parts))


def build_text_record(
    *,
    year: int,
    company: str,
    report_type: str,
    note_number: str,
    note_title: str,
    section_path_list: list[str],
    section_id: str,
    parent_section_id: str | None,
    section_title: str,
    raw_content: str,
    parse_status: str = "parsed",
    source_file: str = "",
    order_index: int = 0,
    has_sub_sections: bool = False,
    has_tables: bool = False,
) -> dict[str, Any]:
    section_path = " > ".join(section_path_list)
    section_level = len(section_path_list)
    section_type = detect_section_type(section_level, has_sub_sections, has_tables)
    index_style = detect_index_style(section_id)

    return {
        "doc_id": f"{year}_{'_'.join(section_path_list)}_text",
        "year": year,
        "company": company,
        "report_type": report_type,
        "note_number": note_number,
        "note_title": note_title,
        "section_path": section_path,
        "section_id": section_id,
        "parent_section_id": parent_section_id,
        "section_level": section_level,
        "section_title": section_title,
        "section_type": section_type,
        "index_style": index_style,
        "content_type": "text",
        "raw_content": raw_content,
        "content_text": clean_text(raw_content),
        "table_data": None,
        "parse_status": parse_status,
        "source_file": source_file,
        "order_index": order_index,
    }


def build_table_record(
    *,
    year: int,
    company: str,
    report_type: str,
    note_number: str,
    note_title: str,
    section_path_list: list[str],
    parent_section_id: str,
    section_title: str,
    table: dict[str, Any],
    table_idx: int,
    parse_status: str = "parsed",
    source_file: str = "",
    order_index: int = 0,
) -> dict[str, Any]:
    section_path = " > ".join(section_path_list)
    section_level = len(section_path_list)
    table_id = f"{parent_section_id}_table_{table_idx}"

    return {
        "doc_id": f"{year}_{'_'.join(section_path_list)}_table_{table_idx}",
        "year": year,
        "company": company,
        "report_type": report_type,
        "note_number": note_number,
        "note_title": note_title,
        "section_path": section_path,
        "section_id": table_id,
        "parent_section_id": parent_section_id,
        "section_level": section_level,
        "section_title": section_title,
        "section_type": "table_section",
        "index_style": "table",
        "content_type": "table",
        "raw_content": section_title,
        "content_text": table_to_text(table, section_title=section_title),
        "table_data": table,
        "parse_status": parse_status,
        "source_file": source_file,
        "order_index": order_index,
    }


def flatten_section_recursive(
    *,
    year: int,
    company: str,
    report_type: str,
    note_number: str,
    note_title: str,
    section_id: str,
    section_value: dict[str, Any],
    parent_section_id: str | None,
    path_list: list[str],
    source_file: str,
    records: list[dict[str, Any]],
    running_order: list[int],
) -> None:
    """
    각 섹션을 재귀적으로 순회하면서
    text 레코드와 table 레코드를 생성한다.
    """
    current_path = path_list + [section_id]

    section_title = clean_text(section_value.get("title", ""))
    content = section_value.get("content", "")
    raw_content = content if isinstance(content, str) else ""

    tables = section_value.get("tables", []) or []
    sub_sections = section_value.get("sub_sections", {}) or {}

    has_sub_sections = len(sub_sections) > 0
    has_tables = len(tables) > 0

    # text 레코드 생성
    if section_title or clean_text(raw_content):
        running_order[0] += 1
        records.append(
            build_text_record(
                year=year,
                company=company,
                report_type=report_type,
                note_number=note_number,
                note_title=note_title,
                section_path_list=current_path,
                section_id=section_id,
                parent_section_id=parent_section_id,
                section_title=section_title,
                raw_content=raw_content,
                parse_status="parsed",
                source_file=source_file,
                order_index=running_order[0],
                has_sub_sections=has_sub_sections,
                has_tables=has_tables,
            )
        )

    # table 레코드 생성
    for idx, table in enumerate(tables, start=1):
        running_order[0] += 1
        records.append(
            build_table_record(
                year=year,
                company=company,
                report_type=report_type,
                note_number=note_number,
                note_title=note_title,
                section_path_list=current_path,
                parent_section_id=section_id,
                section_title=section_title,
                table=table,
                table_idx=idx,
                parse_status="parsed",
                source_file=source_file,
                order_index=running_order[0],
            )
        )

    # 하위 섹션 재귀
    for child_section_id, child_section_value in sub_sections.items():
        flatten_section_recursive(
            year=year,
            company=company,
            report_type=report_type,
            note_number=note_number,
            note_title=note_title,
            section_id=child_section_id,
            section_value=child_section_value,
            parent_section_id=section_id,
            path_list=current_path,
            source_file=source_file,
            records=records,
            running_order=running_order,
        )


def flatten_notes_json(
    data: dict[str, Any],
    *,
    company: str = "삼성전자",
    report_type: str = "감사보고서",
    source_file: str = "",
) -> list[dict[str, Any]]:
    """
    11개년 structured notes JSON 전체를 팀 스키마에 맞춰 평탄화
    """
    records: list[dict[str, Any]] = []
    running_order = [0]

    for year_key, year_value in data.items():
        year = int(year_key)

        for note_number, note_value in year_value.items():
            note_title = clean_text(note_value.get("title", ""))

            flatten_section_recursive(
                year=year,
                company=company,
                report_type=report_type,
                note_number=note_number,
                note_title=note_title,
                section_id=note_number,
                section_value=note_value,
                parent_section_id=None,
                path_list=[],
                source_file=source_file,
                records=records,
                running_order=running_order,
            )

    return records


def main():
    input_path = "chroma/sample_data/notes_11years_structured_jonghyeon.json"
    output_path = "chroma/sample_data/flattened_notes_11years.json"

    data = load_json(input_path)
    flattened = flatten_notes_json(
        data,
        company="삼성전자",
        report_type="감사보고서",
        source_file=Path(input_path).name,
    )
    save_json(flattened, output_path)

    print(f"평탄화 완료: {output_path}")
    print(f"총 레코드 수: {len(flattened)}")

    if flattened:
        print("\n첫 번째 레코드 예시:")
        print(json.dumps(flattened[0], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()