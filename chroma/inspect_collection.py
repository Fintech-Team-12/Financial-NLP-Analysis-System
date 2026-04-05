import chromadb
from pathlib import Path
from collections import Counter
from pprint import pprint

BASE_DIR = Path(__file__).resolve().parent
CHROMA_PATH = BASE_DIR / "chroma_store"
COLLECTION_NAMES = [
    "audit_reports_10years_text_minilm",
    "audit_reports_10years_table_minilm",
]
SAMPLE_SIZE = 5


def inspect_one_collection(client, collection_name: str, sample_size: int = 5) -> None:
    print("\n" + "=" * 100)
    print(f"Inspecting Collection: {collection_name}")
    print("=" * 100)

    collection = client.get_collection(name=collection_name)
    total_count = collection.count()
    print(f"[INFO] Total documents: {total_count}")

    sample_n = min(sample_size, total_count)
    if sample_n == 0:
        print("[INFO] Collection is empty.")
        return

    result = collection.get(
        limit=sample_n,
        include=["documents", "metadatas"]
    )

    ids = result.get("ids", [])
    docs = result.get("documents", [])
    metas = result.get("metadatas", [])

    all_metadata_keys = set()
    sample_content_type_counter = Counter()
    sample_year_counter = Counter()

    print("\n[Sample Records]")
    for i in range(sample_n):
        print("\n" + "-" * 100)
        print(f"[Record {i + 1}]")

        record_id = ids[i] if i < len(ids) else None
        metadata = metas[i] if i < len(metas) else {}
        document = docs[i] if i < len(docs) else ""

        print(f"id: {record_id}")

        print("metadata:")
        pprint(metadata, width=120)

        if metadata:
            all_metadata_keys.update(metadata.keys())
            if "content_type" in metadata:
                sample_content_type_counter[str(metadata["content_type"])] += 1
            if "year" in metadata:
                sample_year_counter[str(metadata["year"])] += 1

        print("document preview:")
        print((document[:500] + "...") if len(document) > 500 else document)

    print("\n[Sample metadata keys]")
    print(sorted(all_metadata_keys))

    print("\n[Sample content_type distribution]")
    print(dict(sample_content_type_counter))

    print("\n[Sample year distribution]")
    print(dict(sample_year_counter))

    # 전체 메타데이터 스캔
    print("\n[Full metadata scan]")
    full_result = collection.get(include=["metadatas"])
    full_metas = full_result.get("metadatas", [])

    full_metadata_keys = set()
    full_content_type_counter = Counter()
    full_year_counter = Counter()
    full_section_type_counter = Counter()

    for meta in full_metas:
        if not meta:
            continue

        full_metadata_keys.update(meta.keys())

        if "content_type" in meta:
            full_content_type_counter[str(meta["content_type"])] += 1
        if "year" in meta:
            full_year_counter[str(meta["year"])] += 1
        if "section_type" in meta:
            full_section_type_counter[str(meta["section_type"])] += 1

    print("[INFO] All metadata keys:")
    print(sorted(full_metadata_keys))

    print("\n[INFO] Full content_type distribution:")
    print(dict(full_content_type_counter))

    print("\n[INFO] Full year distribution:")
    print(dict(full_year_counter))

    print("\n[INFO] Full section_type distribution:")
    print(dict(full_section_type_counter))


def main():
    print("=" * 100)
    print("Chroma Multi-Collection Inspection")
    print("=" * 100)

    chroma_path = Path(CHROMA_PATH)
    print(f"[INFO] CHROMA_PATH: {chroma_path.resolve()}")

    if not chroma_path.exists():
        print("[ERROR] chroma_store folder does not exist.")
        return

    client = chromadb.PersistentClient(path=str(chroma_path))

    collections = client.list_collections()
    available_names = [c.name for c in collections]

    print("\n[INFO] Available collections:")
    print(available_names if available_names else "(none)")

    for collection_name in COLLECTION_NAMES:
        if collection_name not in available_names:
            print("\n" + "=" * 100)
            print(f"[WARNING] Collection not found: {collection_name}")
            print("=" * 100)
            continue

        inspect_one_collection(client, collection_name, sample_size=SAMPLE_SIZE)

    print("\n" + "=" * 100)
    print("Inspection Complete")
    print("=" * 100)


if __name__ == "__main__":
    main()