# Backend 문서

삼성전자 2014–2024 감사보고서 기반 금융 NLP 시스템의 FastAPI backend.

---

## 디렉토리 구조

```
app/api/
├── app/
│   ├── main.py               # FastAPI 앱 진입점
│   ├── core/config.py        # 환경변수 설정 (DATA_DIR, MOCK_MODE 등)
│   ├── db/                   # 사용자/채팅이력용 SQLite (RAG 데이터와 분리)
│   │   ├── base.py           # SQLAlchemy DeclarativeBase
│   │   ├── session.py        # engine + get_session()
│   │   ├── models.py         # User / OAuthAccount / ChatSession / ChatMessage
│   │   └── init_db.py        # create_tables()
│   ├── models/document.py    # RAG 내부 정규화 문서 스키마 (NormalizedDocument)
│   ├── schemas/              # Pydantic 요청/응답 스키마
│   ├── routes/               # FastAPI 라우터
│   │   ├── health.py         # GET  /health
│   │   ├── ingest.py         # POST /reports/ingest
│   │   └── qa.py             # POST /qa
│   └── services/             # 비즈니스 로직
│       ├── router.py         # 질문 유형 분류
│       ├── indexing.py       # JSON → in-memory 인덱스
│       ├── retrieval.py      # RetrieverBase + MockRetriever
│       ├── answering.py      # GeneratorBase + MockGenerator
│       ├── auth_service.py   # 사용자 조회/생성
│       └── chat_history_service.py  # 세션/메시지 CRUD
└── tests/
    ├── conftest.py           # 공통 fixture (sample JSON, store 초기화, TestClient)
    ├── test_health.py
    ├── test_ingest.py
    ├── test_qa.py
    ├── test_routing.py
    ├── test_auth_service.py
    └── test_chat_history_service.py
```

---

## 주요 엔드포인트

### `GET /health`

서비스 상태 및 현재 인덱싱된 문서 수를 반환한다.

```
Response 200
{
  "status": "ok",
  "indexed_years": [2023],
  "total_documents": 142
}
```

---

### `POST /reports/ingest`

`data/processed/audit_report_{year}_structured.json` 을 읽어 in-memory 인덱스에 적재한다.
QA 호출 전에 반드시 먼저 실행해야 한다.

```
Request
{ "year": 2023, "force": false }

Response 200
{ "year": 2023, "indexed_count": 142, "message": "2023년 감사보고서 142개 문서 인덱싱 완료." }

Response 404  →  해당 연도 파일 없음
```

---

### `POST /qa`

질문을 3가지 유형으로 분류하고 관련 문서를 검색해 답변을 생성한다.

| 유형 | 예시 질문 | 검색 전략 |
|---|---|---|
| `numeric` | 2023년 매출채권 금액은? | structured_lookup → retrieval fallback |
| `note_linked` | 매출채권 관련 회계처리는? | 관련주석 번호 추출 → 주석 섹션 우선 |
| `descriptive` | 2023년 감사의견은? | 감사보고서 + 주석 텍스트 검색 |

```
Request
{ "question": "2023년 매출채권 금액은?", "year": 2023, "top_k": 5 }

Response 200
{
  "answer": "...",
  "citations": [{ "doc_id": "...", "year": 2023, "section": "매출채권", "excerpt": "..." }],
  "question_type": "numeric",
  "used_documents": ["재무상태표_2023_매출채권"]
}

Response 503  →  인덱싱된 문서 없음 (ingest 먼저 호출 필요)
```

---

## 실행 방법

### 로컬

```bash
# 프로젝트 루트에서
pip install -r app/api/requirements.txt

# 서버 실행 (mock 모드 — Chroma/Ollama 없이 동작)
PYTHONPATH=app/api MOCK_MODE=true uvicorn app.main:app --reload

# Swagger UI
open http://localhost:8000/docs
```

### 데이터 인덱싱 (서버 실행 후)

```bash
curl -X POST http://localhost:8000/reports/ingest \
  -H "Content-Type: application/json" \
  -d '{"year": 2023}'
```

### SQLite DB 초기화 (사용자/채팅이력 기능 사용 시)

```bash
PYTHONPATH=app/api python -m app.db.init_db
# → data/app.db 생성
```

### Docker

```bash
# 전체 서비스 기동
docker compose up api

# ingest 파이프라인 별도 실행
docker compose --profile ingest run ingest
```

---

## 테스트 방법

```bash
# 전체 테스트 실행
PYTHONPATH=app/api MOCK_MODE=true pytest app/api/tests -v

# 커버리지 포함
PYTHONPATH=app/api MOCK_MODE=true pytest app/api/tests --cov=app/api/app --cov-report=term-missing

# 특정 파일만
PYTHONPATH=app/api pytest app/api/tests/test_qa.py -v
```

테스트는 `conftest.py`의 임시 sample JSON을 사용하므로 실제 `data/processed/` 파일이 없어도 실행된다.

---

## 환경변수

| 변수 | 기본값 | 설명 |
|---|---|---|
| `DATA_DIR` | `data/processed` | processed JSON 파일 디렉토리 |
| `MOCK_MODE` | `true` | `true`: MockRetriever+MockGenerator / `false`: Chroma+Ollama |
| `APP_DB_URL` | `sqlite:///data/app.db` | 사용자/채팅이력 SQLite 경로 |
| `CHROMA_HOST` | `localhost` | ChromaDB 호스트 (`MOCK_MODE=false` 시 사용) |
| `CHROMA_PORT` | `8000` | ChromaDB 포트 |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama API URL |
| `OLLAMA_MODEL` | `llama3` | 사용할 Ollama 모델명 |

---

## Chroma / Ollama 연결 방법 (담당자용)

현재 `MOCK_MODE=true` 상태에서는 Chroma와 Ollama 없이 동작한다.
실제 모델을 붙이려면:

1. `app/api/app/services/retrieval.py` — `ChromaRetriever` 구현 후 `get_retriever()` 주석 해제
2. `app/api/app/services/answering.py` — `OllamaGenerator` 구현 후 `get_generator()` 주석 해제
3. 환경변수 `MOCK_MODE=false` 설정

**`routes/`, `schemas/`, `tests/`는 변경하지 않아도 된다.** 인터페이스(`RetrieverBase`, `GeneratorBase`)가 유지되는 한 기존 테스트가 그대로 통과한다.

---

## 트러블슈팅

**`503 Service Unavailable` — 인덱싱된 문서가 없습니다**

`POST /reports/ingest` 를 먼저 호출하지 않은 경우.
서버를 재시작하면 in-memory 인덱스가 초기화되므로 매번 ingest 가 필요하다.
자동화하려면 `app/main.py` lifespan 에 `ingest_year(2023)` 을 추가한다.

```python
# app/main.py lifespan 예시
async def lifespan(app):
    from app.services.indexing import ingest_year
    for year in range(2014, 2025):
        try:
            ingest_year(year)
        except FileNotFoundError:
            pass
    yield
```

---

**`404 Not Found` — Processed data not found**

`DATA_DIR` 경로에 해당 연도 파일이 없는 경우.
로컬 실행 시 `data/processed/audit_report_{year}_structured.json` 이 존재하는지 확인.
Docker 환경에서는 `docker-compose.yml` 의 `volumes` 마운트 경로를 확인.

---

**`ModuleNotFoundError: No module named 'app'`**

`PYTHONPATH=app/api` 설정 누락.

```bash
# 올바른 실행
PYTHONPATH=app/api uvicorn app.main:app --reload

# pytest 도 동일
PYTHONPATH=app/api pytest app/api/tests
```
