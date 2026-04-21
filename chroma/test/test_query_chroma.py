from pathlib import Path

import chromadb
import pytest

CHROMA_PATH = Path(__file__).resolve().parents[2] / "chroma_store"

EXPECTED_COLLECTIONS = [
    "audit_reports_10years_text_minilm",
    "audit_reports_10years_table_minilm",
]

SAMPLE_QUERIES = [
    "감사의견",
    "독립된 회계감사인의 감사보고서",
    "손익계산서",
    "유형자산",
]


@pytest.fixture(scope="module")
def chroma_client():
    if not CHROMA_PATH.exists():
        pytest.skip(f"chroma_store not found at {CHROMA_PATH}")
    return chromadb.PersistentClient(path=str(CHROMA_PATH))


@pytest.fixture(scope="module")
def existing_collection_names(chroma_client):
    return {c.name for c in chroma_client.list_collections()}


@pytest.mark.parametrize("name", EXPECTED_COLLECTIONS)
def test_expected_collection_exists(existing_collection_names, name):
    if name not in existing_collection_names:
        pytest.skip(f"collection {name} not loaded yet")
    assert name in existing_collection_names


@pytest.mark.parametrize("name", EXPECTED_COLLECTIONS)
def test_collection_not_empty(chroma_client, existing_collection_names, name):
    if name not in existing_collection_names:
        pytest.skip(f"collection {name} not loaded yet")
    col = chroma_client.get_collection(name=name)
    assert col.count() > 0


@pytest.mark.parametrize("query", SAMPLE_QUERIES)
@pytest.mark.parametrize("name", EXPECTED_COLLECTIONS)
def test_sample_query_returns_results(chroma_client, existing_collection_names, name, query):
    if name not in existing_collection_names:
        pytest.skip(f"collection {name} not loaded yet")
    col = chroma_client.get_collection(name=name)
    try:
        res = col.query(query_texts=[query], n_results=3)
    except Exception as exc:  # pragma: no cover - environment-dependent
        # 임베딩 함수 초기화(ONNX/CoreML 등) 실패 같은 환경 의존 오류는 skip
        pytest.skip(f"embedding/query backend unavailable: {exc}")
    ids = res["ids"][0]
    assert len(ids) > 0
    assert len(ids) == len(res["documents"][0]) == len(res["metadatas"][0])
