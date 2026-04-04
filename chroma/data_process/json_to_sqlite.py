import json
import sqlite3
import re
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
INPUT_DIR = BASE_DIR / "enriched_data"
OUTPUT_DIR = BASE_DIR / "sqlite_by_year"


def to_int_bool(value):
    return 1 if value else 0


def create_table(conn: sqlite3.Connection):
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS audit_chunks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chunk_id TEXT NOT NULL UNIQUE,
        doc_id TEXT NOT NULL,
        year INTEGER,
        company TEXT,
        report_type TEXT,
        top_section TEXT,
        note_number TEXT,
        note_title TEXT,
        section_category TEXT,
        section_path TEXT,
        section_id TEXT,
        parent_section_id TEXT,
        section_level INTEGER,
        section_title TEXT,
        section_type TEXT,
        index_style TEXT,
        content_type TEXT,
        content_text TEXT,
        source_file TEXT,
        order_index INTEGER,
        has_sub_sections INTEGER,
        has_tables INTEGER,
        related_notes TEXT,
        amount_unit TEXT,
        is_empty INTEGER,
        is_leaf INTEGER,
        char_len INTEGER,
        has_table INTEGER,
        item_canonical_key TEXT,
        text_for_embedding TEXT,
        embedding_text TEXT,
        token_count INTEGER,
        table_data_json TEXT
    )
    """)

    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_audit_chunks_year
    ON audit_chunks(year)
    """)
    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_audit_chunks_top_section
    ON audit_chunks(top_section)
    """)
    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_audit_chunks_note_number
    ON audit_chunks(note_number)
    """)
    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_audit_chunks_section_id
    ON audit_chunks(section_id)
    """)
    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_audit_chunks_parent_section_id
    ON audit_chunks(parent_section_id)
    """)
    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_audit_chunks_item_canonical_key
    ON audit_chunks(item_canonical_key)
    """)

    conn.commit()


def insert_records(conn: sqlite3.Connection, records: list[dict], source_file_name: str):
    cur = conn.cursor()

    sql = """
    INSERT OR REPLACE INTO audit_chunks (
        chunk_id, doc_id, year, company, report_type,
        top_section, note_number, note_title, section_category,
        section_path, section_id, parent_section_id, section_level,
        section_title, section_type, index_style, content_type,
        content_text, source_file, order_index,
        has_sub_sections, has_tables, related_notes, amount_unit,
        is_empty, is_leaf, char_len, has_table,
        item_canonical_key, text_for_embedding, embedding_text,
        token_count, table_data_json
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    rows = []
    for r in records:
        has_sub_sections = to_int_bool(r.get("has_sub_sections"))
        is_leaf = 0 if has_sub_sections == 1 else to_int_bool(r.get("is_leaf"))

        rows.append((
            r.get("chunk_id"),
            r.get("doc_id"),
            r.get("year"),
            r.get("company"),
            r.get("report_type"),
            r.get("top_section"),
            r.get("note_number"),
            r.get("note_title"),
            r.get("section_category"),
            r.get("section_path"),
            r.get("section_id"),
            r.get("parent_section_id"),
            r.get("section_level"),
            r.get("section_title"),
            r.get("section_type"),
            r.get("index_style"),
            r.get("content_type"),
            r.get("content_text"),
            source_file_name,
            r.get("order_index"),
            has_sub_sections,
            to_int_bool(r.get("has_tables")),
            json.dumps(r.get("related_notes", []), ensure_ascii=False),
            r.get("amount_unit"),
            to_int_bool(r.get("is_empty")),
            is_leaf,
            r.get("char_len"),
            to_int_bool(r.get("has_table")),
            r.get("item_canonical_key"),
            r.get("text_for_embedding"),
            r.get("embedding_text"),
            r.get("token_count"),
            json.dumps(r.get("table_data"), ensure_ascii=False) if r.get("table_data") is not None else None,
            ))
        
    cur.executemany(sql, rows)
    conn.commit()

    cur.executemany(sql, rows)
    conn.commit()


def extract_year_from_filename(file_name: str) -> str:
    match = re.search(r"(20\d{2})", file_name)
    if not match:
        raise ValueError(f"파일명에서 연도를 찾을 수 없습니다: {file_name}")
    return match.group(1)


def process_one_file(input_file: Path):
    with input_file.open("r", encoding="utf-8") as f:
        records = json.load(f)

    if not isinstance(records, list):
        raise ValueError(f"{input_file.name} 는 list JSON이어야 합니다.")

    year = extract_year_from_filename(input_file.name)
    db_path = OUTPUT_DIR / f"audit_reports_{year}.db"

    conn = sqlite3.connect(db_path)
    try:
        create_table(conn)
        insert_records(conn, records, input_file.name)

        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM audit_chunks")
        total = cur.fetchone()[0]

        print(f"{input_file.name}: {len(records)}건 적재 완료")
        print(f"→ 생성된 DB: {db_path}")
        print(f"→ DB 내 총 건수: {total}\n")
    finally:
        conn.close()


def main():
    if not INPUT_DIR.exists():
        raise FileNotFoundError(f"입력 폴더가 없습니다: {INPUT_DIR}")

    OUTPUT_DIR.mkdir(exist_ok=True)

    input_files = sorted(INPUT_DIR.glob("*_enriched.json"))
    if not input_files:
        raise FileNotFoundError(f"{INPUT_DIR} 안에 *_enriched.json 파일이 없습니다.")

    for input_file in input_files:
        process_one_file(input_file)

    print("연도별 DB 생성 완료")


if __name__ == "__main__":
    main()