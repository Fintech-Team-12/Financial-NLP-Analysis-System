import chromadb
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CHROMA_PATH = "./chroma_store"
COLLECTION_NAME = "audit_reports_2014"

client = chromadb.PersistentClient(path=str(CHROMA_PATH))
collection = client.get_collection(name=COLLECTION_NAME)

test_queries = [
    "감사의견",
    "독립된 회계감사인의 감사보고서",
    "재무제표에 대한 경영진의 책임",
    "손익계산서",
    "포괄손익계산서",
    "법인세비용",
    "현금및현금성자산",
    "유형자산"
]

for q in test_queries:
    print("\n" + "=" * 70)
    print("질의:", q)

    result = collection.query(
        query_texts=[q],
        n_results=3
    )

    for i in range(len(result["ids"][0])):
        print(f"\n[{i+1}위]")
        print("id:", result["ids"][0][i])
        print("metadata:", result["metadatas"][0][i])
        print("document:", result["documents"][0][i][:250])