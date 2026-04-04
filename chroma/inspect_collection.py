import chromadb
from pathlib import Path
from collections import Counter
from pprint import pprint

# =========================
# 기본 설정
# =========================
CHROMA_PATH = "./chroma_store"
COLLECTION_NAME = "audit_reports_2014"
SAMPLE_SIZE = 5


def main():
    print("=" * 80)
    print("Chroma Collection Inspection")
    print("=" * 80)

    chroma_path = Path(CHROMA_PATH)
    print(f"[INFO] CHROMA_PATH: {chroma_path.resolve()}")
    print(f"[INFO] COLLECTION_NAME: {COLLECTION_NAME}")

    # 1. Chroma client 연결
    client = chromadb.PersistentClient(path=str(chroma_path))

    # 2. collection 가져오기
    collection = client.get_collection(name=COLLECTION_NAME)

    # 3. 전체 개수 확인
    total_count = collection.count()
    print(f"[INFO] Total documents in collection: {total_count}")

    # 4. 샘플 데이터 가져오기
    sample_n = min(SAMPLE_SIZE, total_count)
    result = collection.get(
        limit=sample_n,
        include=["documents", "metadatas"]
    )

    ids = result.get("ids", [])
    docs = result.get("documents", [])
    metas = result.get("metadatas", [])

    print("\n" + "=" * 80)
    print(f"Sample Records (top {sample_n})")
    print("=" * 80)

    all_metadata_keys = set()
    content_type_counter = Counter()

    for i in range(sample_n):
        print(f"\n[Record {i+1}]")
        print("-" * 80)

        record_id = ids[i] if i < len(ids) else None
        metadata = metas[i] if i < len(metas) else {}
        document = docs[i] if i < len(docs) else ""

        print(f"id: {record_id}")

        print("metadata:")
        pprint(metadata, width=100)

        if metadata:
            all_metadata_keys.update(metadata.keys())
            if "content_type" in metadata:
                content_type_counter[metadata["content_type"]] += 1

        print("document preview:")
        print((document[:500] + "...") if len(document) > 500 else document)

    # 5. metadata key 요약
    print("\n" + "=" * 80)
    print("Metadata Keys Summary")
    print("=" * 80)
    print(sorted(all_metadata_keys))

    # 6. content_type 분포 확인용 샘플
    print("\n" + "=" * 80)
    print("Sample content_type distribution")
    print("=" * 80)
    print(dict(content_type_counter))

    # 7. 전체에서 content_type 분포도 보고 싶으면 (metadata만 가져오기)
    print("\n" + "=" * 80)
    print("Full Collection Metadata Scan")
    print("=" * 80)

    full_result = collection.get(include=["metadatas"])
    full_metas = full_result.get("metadatas", [])

    full_content_type_counter = Counter()
    full_metadata_keys = set()

    for meta in full_metas:
        if not meta:
            continue
        full_metadata_keys.update(meta.keys())
        if "content_type" in meta:
            full_content_type_counter[meta["content_type"]] += 1

    print("[INFO] All metadata keys found in full collection:")
    print(sorted(full_metadata_keys))

    print("\n[INFO] Full content_type distribution:")
    print(dict(full_content_type_counter))

    print("\n" + "=" * 80)
    print("Inspection Complete")
    print("=" * 80)


if __name__ == "__main__":
    main()