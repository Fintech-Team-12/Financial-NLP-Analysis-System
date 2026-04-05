import sqlite3
from pathlib import Path
import chromadb
from chromadb.utils import embedding_functions

SQLITE_DIR = Path("./chroma/sqlite_by_year")
CHROMA_PATH = "./chroma_store"
COLLECTION_NAME = "audit_reports_10years_text_minilm"

#배치사이즈조정
BATCH_SIZE = 50
MAX_TEXT_LENGTH = 2000


def safe_metadata_value(value):
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def build_metadata(row):
    return {
        "chunk_id": safe_metadata_value(row["chunk_id"]),
        "doc_id": safe_metadata_value(row["doc_id"]),
        "year": safe_metadata_value(row["year"]),
        "company": safe_metadata_value(row["company"]),
        "report_type": safe_metadata_value(row["report_type"]),
        "top_section": safe_metadata_value(row["top_section"]),
        "note_number": safe_metadata_value(row["note_number"]),
        "section_path": safe_metadata_value(row["section_path"]),
        "section_level": safe_metadata_value(row["section_level"]),
        "section_title": safe_metadata_value(row["section_title"]),
        "section_type": safe_metadata_value(row["section_type"]),
        "content_type": safe_metadata_value(row["content_type"]),
        "order_index": safe_metadata_value(row["order_index"]),
    }


def fetch_rows_from_db(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT
            chunk_id,
            doc_id,
            year,
            company,
            report_type,
            top_section,
            note_number,
            section_path,
            section_level,
            section_title,
            section_type,
            content_type,
            order_index,
            embedding_text
        FROM audit_chunks
        WHERE embedding_text IS NOT NULL
          AND TRIM(embedding_text) != ''
          AND content_type = 'text'
    """)

    rows = cur.fetchall()
    conn.close()
    return rows


def batch_iter(items, batch_size):
    for i in range(0, len(items), batch_size):
        yield items[i:i + batch_size]


db_files = sorted(SQLITE_DIR.glob("audit_reports_*.db"))

if not db_files:
    raise FileNotFoundError(f"DB 파일을 찾을 수 없습니다: {SQLITE_DIR}")

print("찾은 DB 파일:")
for db_file in db_files:
    print("-", db_file.name)

client = chromadb.PersistentClient(path=CHROMA_PATH)

try:
    client.delete_collection(name=COLLECTION_NAME)
    print(f"기존 컬렉션 삭제 완료: {COLLECTION_NAME}")
except Exception:
    print("삭제할 기존 컬렉션 없음")

embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    device="mps"
)

collection = client.get_or_create_collection(
    name=COLLECTION_NAME,
    embedding_function=embedding_function
)

total_added = 0

for db_path in db_files:
    print(f"\n처리 중: {db_path.name}")
    rows = fetch_rows_from_db(db_path)
    print(f"가져온 row 수: {len(rows)}")

    ids = []
    documents = []
    metadatas = []

    for row in rows:
        text = row["embedding_text"]

        if len(text) > MAX_TEXT_LENGTH:
            text = text[:MAX_TEXT_LENGTH]

        ids.append(row["chunk_id"])
        documents.append(text)
        metadatas.append(build_metadata(row))

    for id_batch, doc_batch, meta_batch in zip(
        batch_iter(ids, BATCH_SIZE),
        batch_iter(documents, BATCH_SIZE),
        batch_iter(metadatas, BATCH_SIZE)
    ):
        collection.add(
            ids=id_batch,
            documents=doc_batch,
            metadatas=meta_batch
        )

    total_added += len(ids)
    print(f"{db_path.name} 적재 완료: {len(ids)}개")

print("\n=== 전체 적재 완료 ===")
print("총 적재 문서 수:", total_added)
print("컬렉션 count():", collection.count())