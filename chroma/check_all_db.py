import sqlite3
from pathlib import Path

DB_DIR = Path("chroma/sqlite_by_year")


def check_db(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    print(f"\n===== {db_path.name} =====")

    cur.execute("SELECT COUNT(*) FROM audit_chunks")
    print("[1] total_rows:", cur.fetchone()[0])

    cur.execute("SELECT DISTINCT year FROM audit_chunks")
    print("[2] year:", [r[0] for r in cur.fetchall()])

    cur.execute("SELECT DISTINCT source_file FROM audit_chunks")
    print("[3] source_file:", [r[0] for r in cur.fetchall()])

    checks = {
        "empty_content": """
            SELECT COUNT(*) FROM audit_chunks
            WHERE content_text IS NULL OR TRIM(content_text) = ''
        """,
        "empty_embedding": """
            SELECT COUNT(*) FROM audit_chunks
            WHERE embedding_text IS NULL OR TRIM(embedding_text) = ''
        """,
        "duplicate_chunk_id": """
            SELECT COUNT(*) FROM (
                SELECT chunk_id
                FROM audit_chunks
                GROUP BY chunk_id
                HAVING COUNT(*) > 1
            )
        """,
        "leaf_conflict": """
            SELECT COUNT(*) FROM audit_chunks
            WHERE has_sub_sections = 1 AND is_leaf = 1
        """,
        "table_missing": """
            SELECT COUNT(*) FROM audit_chunks
            WHERE has_table = 1
              AND (table_data_json IS NULL OR TRIM(table_data_json) = '')
        """
    }

    for key, query in checks.items():
        cur.execute(query)
        print(f"[{key}]:", cur.fetchone()[0])

    conn.close()


def main():
    db_files = sorted(DB_DIR.glob("*.db"))

    if not db_files:
        print("검사할 DB 파일이 없습니다.")
        return

    for db_path in db_files:
        check_db(db_path)


if __name__ == "__main__":
    main()