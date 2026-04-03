import sqlite3
import chromadb

DB_PATH = "./chroma/sqlite_by_year/audit_reports_2014.db"
CHROMA_PATH = "./chroma_store"
COLLECTION_NAME = "audit_reports_2014"

# 1. SQLite 연결
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# 2. 필요한 컬럼만 조회
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

# 3. Chroma 연결
client = chromadb.PersistentClient(path=CHROMA_PATH)

# 4. 컬렉션 만들기
collection = client.get_or_create_collection(name=COLLECTION_NAME)

# 5. Chroma에 넣을 데이터 준비
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

# 7. 검색 테스트
result = collection.query(
    query_texts=["유형자산"],
    n_results=3
)

print(result["ids"])
print(result["documents"][0][0])
print(result["metadatas"][0][0])