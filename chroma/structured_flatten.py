import json
import re
from pathlib import Path
from typing import Any


# -------------------------------
# 기본 유틸
# -------------------------------
def load_json(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data: list[dict[str, Any]], path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def clean_text(text: Any) -> str:
    if text is None:
        return ""
    text = str(text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def detect_index_style(section_id: str) -> str:
    if re.fullmatch(r"\d+(\.\d+)*", section_id):
        return "numeric"
    if re.fullmatch(r"[가-힣]\.", section_id):
        return "korean"
    if re.fullmatch(r"\(\d+\)", section_id):
        return "paren_numeric"
    if re.fullmatch(r"[A-Za-z]+", section_id):
        return "alphabet"
    return "other"


def extract_year_from_data(data: dict[str, Any]) -> int:
    if len(data) != 1:
        raise ValueError("최상위에는 연도 키가 1개만 있어야 합니다.")
    year_key = next(iter(data.keys()))
    if not str(year_key).isdigit():
        raise ValueError(f"연도 키가 숫자가 아닙니다: {year_key}")
    return int(year_key)


def extract_company_from_data(year_block: dict[str, Any], default: str = "삼성전자") -> str:
    # 감사보고서 도입부나 주석 1에서 회사명을 추정하고 싶으면 나중에 확장 가능
    return default


# -------------------------------
# 표 텍스트화
# -------------------------------
def table_to_text(table: dict[str, Any], section_title: str = "") -> str:
    unit = clean_text(table.get("unit", ""))
    columns = table.get("columns", []) or []
    rows = table.get("rows", []) or []
    annotations = table.get("annotations", []) or []

    parts: list[str] = []

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

        cleaned_row = [clean_text(cell) for cell in row]

        if columns and len(columns) == len(cleaned_row):
            pairs = [f"{clean_text(col)}: {cell}" for col, cell in zip(columns, cleaned_row)]
            row_texts.append(" / ".join(pairs))
        else:
            row_texts.append(" / ".join(cleaned_row))

    if row_texts:
        parts.append("행: " + " | ".join(row_texts))

    ann_texts = []
    for ann in annotations:
        if not isinstance(ann, dict):
            continue
        marker = clean_text(ann.get("marker", ""))
        text = clean_text(ann.get("text", ""))
        combined = f"{marker} {text}".strip()
        if combined:
            ann_texts.append(combined)

    if ann_texts:
        parts.append("주석: " + " | ".join(ann_texts))

    return clean_text(" ".join(parts))


# -------------------------------
# 레코드 생성
# -------------------------------
def build_text_record(
    *,
    year: int,
    company: str,
    report_type: str,
    top_section: str,
    note_number: str | None,
    note_title: str,
    section_id: str,
    section_title: str,
    parent_section_id: str | None,
    section_path_list: list[str],
    raw_content: str,
    source_file: str,
    order_index: int,
    has_sub_sections: bool,
    has_tables: bool,
) -> dict[str, Any]:
    section_path = " > ".join(section_path_list)
    section_level = len(section_path_list)
    index_style = detect_index_style(section_id)

    if top_section == "주석":
        section_category = "note"
    elif top_section in {"재무상태표", "손익계산서", "포괄손익계산서", "자본변동표", "현금흐름표"}:
        section_category = "statement"
    elif top_section == "부록":
        section_category = "appendix"
    else:
        section_category = "report"

    if section_level == 1:
        section_type = "top_section"
    elif has_tables and not has_sub_sections:
        section_type = "leaf_section"
    else:
        section_type = "subsection"

    return {
        "doc_id": f"{year}_{'_'.join(section_path_list)}_text",
        "year": year,
        "company": company,
        "report_type": report_type,
        "top_section": top_section,
        "note_number": note_number,
        "note_title": note_title,
        "section_category": section_category,
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
        "source_file": source_file,
        "order_index": order_index,
        "has_sub_sections": has_sub_sections,
        "has_tables": has_tables,
    }


def build_table_record(
    *,
    year: int,
    company: str,
    report_type: str,
    top_section: str,
    note_number: str | None,
    note_title: str,
    parent_section_id: str,
    section_title: str,
    section_path_list: list[str],
    table: dict[str, Any],
    table_idx: int,
    source_file: str,
    order_index: int,
) -> dict[str, Any]:
    section_path = " > ".join(section_path_list)
    section_level = len(section_path_list)

    if top_section == "주석":
        section_category = "note"
    elif top_section in {"재무상태표", "손익계산서", "포괄손익계산서", "자본변동표", "현금흐름표"}:
        section_category = "statement"
    elif top_section == "부록":
        section_category = "appendix"
    else:
        section_category = "report"

    table_id = f"{parent_section_id}_table_{table_idx}"

    return {
        "doc_id": f"{year}_{'_'.join(section_path_list)}_table_{table_idx}",
        "year": year,
        "company": company,
        "report_type": report_type,
        "top_section": top_section,
        "note_number": note_number,
        "note_title": note_title,
        "section_category": section_category,
        "section_path": section_path,
        "section_id": table_id,
        "parent_section_id": parent_section_id,
        "section_level": section_level,
        "section_title": section_title,
        "section_type": "table",
        "index_style": "table",
        "content_type": "table",
        "raw_content": section_title,
        "content_text": table_to_text(table, section_title=section_title),
        "table_data": table,
        "source_file": source_file,
        "order_index": order_index,
        "has_sub_sections": False,
        "has_tables": False,
    }


# -------------------------------
# 재귀 flatten
# -------------------------------
def flatten_section_recursive(
    *,
    year: int,
    company: str,
    report_type: str,
    top_section: str,
    note_number: str | None,
    note_title: str,
    section_id: str,
    section_value: dict[str, Any],
    parent_section_id: str | None,
    path_list: list[str],
    source_file: str,
    records: list[dict[str, Any]],
    running_order: list[int],
) -> None:
    current_path = path_list + [section_id]

    section_title = clean_text(section_value.get("title", ""))
    raw_content = section_value.get("content", "")
    if not isinstance(raw_content, str):
        raw_content = ""

    tables = section_value.get("tables", []) or []
    sub_sections = section_value.get("sub_sections", {}) or {}

    has_tables = len(tables) > 0
    has_sub_sections = len(sub_sections) > 0

    # 텍스트 레코드: 제목 또는 본문이 있으면 생성
    if section_title or clean_text(raw_content):
        running_order[0] += 1
        records.append(
            build_text_record(
                year=year,
                company=company,
                report_type=report_type,
                top_section=top_section,
                note_number=note_number,
                note_title=note_title,
                section_id=section_id,
                section_title=section_title,
                parent_section_id=parent_section_id,
                section_path_list=current_path,
                raw_content=raw_content,
                source_file=source_file,
                order_index=running_order[0],
                has_sub_sections=has_sub_sections,
                has_tables=has_tables,
            )
        )

    # 표 레코드
    for idx, table in enumerate(tables, start=1):
        running_order[0] += 1
        records.append(
            build_table_record(
                year=year,
                company=company,
                report_type=report_type,
                top_section=top_section,
                note_number=note_number,
                note_title=note_title,
                parent_section_id=section_id,
                section_title=section_title,
                section_path_list=current_path,
                table=table,
                table_idx=idx,
                source_file=source_file,
                order_index=running_order[0],
            )
        )

    # 하위 섹션 재귀
    for child_section_id, child_section_value in sub_sections.items():
        if not isinstance(child_section_value, dict):
            continue

        flatten_section_recursive(
            year=year,
            company=company,
            report_type=report_type,
            top_section=top_section,
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


# -------------------------------
# 최상위 구조 flatten
# -------------------------------
def flatten_structured_audit_json(
    data: dict[str, Any],
    *,
    source_file: str,
    report_type: str = "감사보고서",
    default_company: str = "삼성전자",
) -> list[dict[str, Any]]:
    year = extract_year_from_data(data)
    year_block = data[str(year)]

    if not isinstance(year_block, dict):
        raise ValueError("연도 아래 블록은 dict 구조여야 합니다.")

    company = extract_company_from_data(year_block, default=default_company)

    records: list[dict[str, Any]] = []
    running_order = [0]

    for top_key, top_value in year_block.items():
        if not isinstance(top_value, dict):
            continue

        # 주석은 특별 처리
        if top_key == "주석":
            note_group_title = clean_text(top_value.get("title", "주석"))

            # 주석 그룹 자체를 하나의 텍스트 레코드로 만들고 싶으면 여기서 가능
            running_order[0] += 1
            records.append(
                build_text_record(
                    year=year,
                    company=company,
                    report_type=report_type,
                    top_section="주석",
                    note_number=None,
                    note_title=note_group_title,
                    section_id="주석",
                    section_title=note_group_title,
                    parent_section_id=None,
                    section_path_list=["주석"],
                    raw_content=clean_text(top_value.get("content", "")),
                    source_file=source_file,
                    order_index=running_order[0],
                    has_sub_sections=bool(top_value.get("sub_sections")),
                    has_tables=bool(top_value.get("tables")),
                )
            )

            for note_number, note_value in top_value.items():
                if note_number in {"title", "content", "tables", "sub_sections"}:
                    continue
                if not isinstance(note_value, dict):
                    continue

                note_title = clean_text(note_value.get("title", ""))

                flatten_section_recursive(
                    year=year,
                    company=company,
                    report_type=report_type,
                    top_section="주석",
                    note_number=str(note_number),
                    note_title=note_title,
                    section_id=str(note_number),
                    section_value=note_value,
                    parent_section_id="주석",
                    path_list=["주석"],
                    source_file=source_file,
                    records=records,
                    running_order=running_order,
                )

        else:
            # 감사보고서, 재무제표, 부록 등
            top_title = clean_text(top_value.get("title", ""))
            flatten_section_recursive(
                year=year,
                company=company,
                report_type=report_type,
                top_section=top_key,
                note_number=None,
                note_title=top_title,
                section_id=top_key,
                section_value=top_value,
                parent_section_id=None,
                path_list=[],
                source_file=source_file,
                records=records,
                running_order=running_order,
            )

    return records


# -------------------------------
# 실행
# -------------------------------
def process_one_file(input_path: Path, output_dir: Path) -> list[dict[str, Any]]:
    data = load_json(input_path)

    flattened = flatten_structured_audit_json(
        data,
        source_file=input_path.name,
        report_type="감사보고서",
        default_company="삼성전자",
    )

    output_file = output_dir / input_path.name.replace("_structured.json", "_flattened.json")
    save_json(flattened, output_file)

    print(f"완료: {input_path.name} -> {output_file.name} ({len(flattened)} records)")
    return flattened


def main():
    base_dir = Path(__file__).resolve().parent
    project_dir = base_dir.parent

    input_dir = project_dir / "data" / "processed"
    output_dir = project_dir / "chroma" / "flattened_data"
    output_dir.mkdir(parents=True, exist_ok=True)

    input_files = sorted(input_dir.glob("*_structured.json"))
    if not input_files:
        raise FileNotFoundError(f"{input_dir} 안에 *_structured.json 파일이 없습니다.")

    for input_file in input_files:
        flattened = process_one_file(input_file, output_dir)
        print(f"{input_file.name}: {len(flattened)}개 레코드 생성")

if __name__ == "__main__":
    main()