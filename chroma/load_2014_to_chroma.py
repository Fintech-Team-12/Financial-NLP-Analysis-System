from chromadb.utils import embedding_functions
embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="paraphrase-multilingual-MiniLM-L12-v2"
)

import sqlite3
import chromadb

DB_PATH = "./chroma/sqlite_by_year/audit_reports_2014.db"
CHROMA_PATH = "./chroma_store"
COLLECTION_NAME = "audit_reports_2014"

# 1. SQLite 연결
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("""
    SELECT
        chunk_id,
        year,
        company,
        report_type,
        section_path,
        section_title,
        content_type,
        embedding_text
    FROM audit_chunks
    WHERE embedding_text IS NOT NULL
      AND TRIM(embedding_text) != ''
""")

rows = cur.fetchall()
conn.close()

print(f"가져온 row 수: {len(rows)}")

# 2. Chroma 연결
client = chromadb.PersistentClient(path=CHROMA_PATH)

# 3. 기존 컬렉션 삭제
try:
    client.delete_collection(name=COLLECTION_NAME)
    print(f"기존 컬렉션 삭제 완료: {COLLECTION_NAME}")
except Exception:
    print("삭제할 기존 컬렉션 없음")

# 4. 새 컬렉션 생성
collection = client.get_or_create_collection(
    name=COLLECTION_NAME,
    embedding_function=embedding_function
)

# 5. 데이터 준비
ids = []
documents = []
metadatas = []

for row in rows:
    ids.append(row["chunk_id"])
    documents.append(row["embedding_text"])
    metadatas.append({
        "year": row["year"],
        "company": row["company"],
        "report_type": row["report_type"],
        "section_path": row["section_path"],
        "section_title": row["section_title"],
        "content_type": row["content_type"]
    })

# 6. 적재
collection.add(
    ids=ids,
    documents=documents,
    metadatas=metadatas
)

print("Chroma 적재 완료")
print("컬렉션 문서 수:", collection.count())