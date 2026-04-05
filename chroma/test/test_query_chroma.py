import chromadb

CHROMA_PATH = "./chroma_store"
COLLECTION_NAME = "audit_reports_2014_text_only"

client = chromadb.PersistentClient(path=CHROMA_PATH)

print("현재 컬렉션 목록:", client.list_collections())

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
    print("\n" + "=" * 90)
    print(f"질의: {q}")

    result = collection.query(
        query_texts=[q],
        n_results=3
    )

    ids = result["ids"][0]
    docs = result["documents"][0]
    metas = result["metadatas"][0]

    for i in range(len(ids)):
        meta = metas[i]
        doc_preview = docs[i][:300].replace("\n", " ")

        print("\n" + "-" * 60)
        print(f"[{i+1}위]")
        print(f"id           : {ids[i]}")
        print(f"section_title: {meta.get('section_title')}")
        print(f"section_path : {meta.get('section_path')}")
        print(f"content_type : {meta.get('content_type')}")
        print(f"top_section  : {meta.get('top_section')}")
        print(f"note_number  : {meta.get('note_number')}")
        print(f"section_level: {meta.get('section_level')}")
        print(f"section_type : {meta.get('section_type')}")
        print(f"order_index  : {meta.get('order_index')}")
        print(f"doc_id       : {meta.get('doc_id')}")
        print(f"chunk_id     : {meta.get('chunk_id')}")
        print(f"company/year : {meta.get('company')} / {meta.get('year')}")
        print(f"document     : {doc_preview}...")