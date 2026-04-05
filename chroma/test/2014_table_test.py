import sqlite3
import chromadb
from chromadb.utils import embedding_functions

DB_PATH = "./chroma/sqlite_by_year/audit_reports_2014.db"
CHROMA_PATH = "./chroma_store"
COLLECTION_NAME = "audit_reports_2014_table_bgem3"


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


conn = sqlite3.connect(DB_PATH)
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
""")

rows = cur.fetchall()
conn.close()

print(f"가져온 row 수: {len(rows)}")

client = chromadb.PersistentClient(path=CHROMA_PATH)

try:
    client.delete_collection(name=COLLECTION_NAME)
    print(f"기존 컬렉션 삭제 완료: {COLLECTION_NAME}")
except Exception:
    print("삭제할 기존 컬렉션 없음")

embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="BAAI/bge-m3",
    device="mps"
)

collection = client.get_or_create_collection(
    name=COLLECTION_NAME,
    embedding_function=embedding_function
)

ids = []
documents = []
metadatas = []

for row in rows:
    if row["content_type"] != "table":
        continue

    ids.append(row["chunk_id"])
    documents.append(row["embedding_text"])
    metadatas.append(build_metadata(row))

collection.add(
    ids=ids,
    documents=documents,
    metadatas=metadatas
)

print("Chroma 적재 완료")
print("컬렉션 문서 수:", collection.count())