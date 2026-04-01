import json
from pathlib import Path


def normalize_path(path_value: str) -> str:
    """
    section_path 공백 정리
    예: '2 > 2.6 > 가.' 형태를 일정하게 유지
    """
    if not path_value:
        return ""
    parts = [part.strip() for part in str(path_value).split(">")]
    parts = [part for part in parts if part]
    return " > ".join(parts)


def build_embedding_text(record: dict) -> str:
    company = str(record.get("company", "")).strip()
    year = str(record.get("year", "")).strip()
    report_type = str(record.get("report_type", "")).strip()
    note_number = str(record.get("note_number", "")).strip()
    note_title = str(record.get("note_title", "")).strip()
    section_path = normalize_path(record.get("section_path", ""))
    section_title = str(record.get("section_title", "")).strip()
    content_text = str(record.get("content_text", "")).strip()
    content_type = str(record.get("content_type", "")).strip()

    parts = [
        company,
        f"{year}년" if year else "",
        report_type,
        f"주석 {note_number}" if note_number else "",
        note_title,
        f"섹션경로 {section_path}" if section_path else "",
        f"섹션제목 {section_title}" if section_title else "",
        f"콘텐츠유형 {content_type}" if content_type else "",
        content_text,
    ]

    parts = [p for p in parts if p]
    return " ".join(parts)


def compute_leaf_flags(records: list[dict]) -> list[bool]:
    """
    section_path 기준으로 is_leaf 계산
    어떤 레코드의 section_path를 prefix로 가지는 더 긴 path가 있으면 leaf 아님
    """
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


def enrich_records(records: list[dict]) -> list[dict]:
    leaf_flags = compute_leaf_flags(records)
    enriched = []

    for record, is_leaf in zip(records, leaf_flags):
        new_record = dict(record)

        content_text = str(new_record.get("content_text", "") or "").strip()
        table_data = new_record.get("table_data")
        section_path = normalize_path(new_record.get("section_path", ""))

        new_record["section_path"] = section_path
        new_record["is_empty"] = (content_text == "")
        new_record["is_leaf"] = is_leaf
        new_record["char_len"] = len(content_text)
        new_record["has_table"] = table_data is not None
        new_record["embedding_text"] = build_embedding_text(new_record)

        enriched.append(new_record)

    return enriched


def main():
    input_path = Path("chroma/sample_data/flattened_notes_11years.json")
    output_path = Path("chroma/sample_data/flattened_notes_11years_enriched.json")

    if not input_path.exists():
        raise FileNotFoundError(f"입력 파일을 찾을 수 없습니다: {input_path}")

    with input_path.open("r", encoding="utf-8") as f:
        records = json.load(f)

    if not isinstance(records, list):
        raise ValueError("입력 JSON은 list 형태여야 합니다.")

    enriched_records = enrich_records(records)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(enriched_records, f, ensure_ascii=False, indent=2)

    print(f"후처리 완료: {output_path}")
    print(f"총 레코드 수: {len(enriched_records)}")

    # 샘플 확인
    print("\n샘플 5개:")
    for rec in enriched_records[:5]:
        print(
            rec["doc_id"],
            "| path =", rec["section_path"],
            "| is_leaf =", rec["is_leaf"],
            "| is_empty =", rec["is_empty"]
        )


if __name__ == "__main__":
    main()