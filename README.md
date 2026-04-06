# Financial NLP Analysis System

삼성전자 감사보고서(2014–2024) 기반 RAG 질의응답 시스템.
HTM 원본 파싱 → 구조화 JSON → ChromaDB 벡터 인덱싱 → LLM 답변 생성의 전체 파이프라인을 포함한다.

---

## 실행 방법


### 1. 로컬 개발 — API 서버

```bash
pip install -r requirements.txt   # Python 3.11

cd app/api
uvicorn app.main:app --reload --port 8000
# → http://localhost:8000/docs
```

---

### 2. 로컬 개발 — Frontend

```bash
cd app/frontend
npm install .
npm run dev   # http://localhost:5173
```



./ ⇒ 프로젝트 root라고 가정

- ./env 파일
    
    ```bash
    APP_ENV=dev
    CHROMA_HOST=chroma
    CHROMA_PORT=8000
    OLLAMA_BASE_URL=http://host.docker.internal:11434
    SQLITE_PATH=/workspace/data/processed/finance.db
    ```
    
- ./app/api/.env 파일
    
    ```bash
    ANTHROPIC_API_KEY=키 받아서 입력하세요
    GOOGLE_CLIENT_ID=키 받아서 입력하세요.apps.googleusercontent.com
    JWT_SECRET_KEY=my_super_secret_jwt_key
    MOCK_MODE=falseANONYMOUS_TELEMETRY=False
    ```
    
- ./app/frontend/.env 파일
    
    ```bash
    VITE_GOOGLE_CLIENT_ID=키 받아서 입력하세요.apps.googleusercontent.com
    ```
    
- .gitignore 파일
    
    ```bash
    # Environment
    .env
    .venv
    .venv_api
    .venv_ingest
    venv/
    env/
    .agent
    
    # OS / Editor
    .DS_Store
    
    # Python
    __pycache__/
    *.py[cod]
    *$py.class
    *.so
    .pytest_cache/
    .ruff_cache
    .coverage
    .coverage.*
    
    # Database
    *.db
    *.sqlite3
    example_finance.db
    
    # Backend / app data
    app/api/app/data
    uploaded_files/
    
    # Chroma / generated data
    chroma/flattened_data/
    chroma_store/
    chroma_db/
    data/processed/
    chroma/data_process/enriched_data/
    chroma/data_process/flattened_data/
    chroma/data_process/sqlite_by_year/
    
    # Frontend
    node_modules/
    dist/
    dist-ssr/
    .vite
    *.local
    data/processed/
    
    .coverage
    .coverage.*
    .pytest_cache
    .ruff_cache
    .venv
    .venv_api
    .venv_ingest
    .agent
    ```


---

## RAG 파이프라인

```
[data/raw/*.htm]
      │
      ▼  app/ingest/src/pipeline.py  (HTML 파싱)
[data/processed/*_structured.json]
      │
      ├──▶ chroma/data_process/structured_flatten.py  (텍스트 청크 평탄화)
      │         │
      │         ▼  chroma/data_process/enrich_flattened_for_rag.py
      │    [enriched_data/*.json]  ─────────────────────────────────────────┐
      │                                                                      │
      └──▶ chroma/data_process/json_to_sqlite.py  (테이블 → SQLite)          │
                │                                                            │
                ▼                                                            ▼
        [sqlite_by_year/*.db]           chroma/load_text_to_chroma.py  (텍스트 컬렉션 적재)
                │                       chroma/load_table_to_chroma.py (테이블 컬렉션 적재)
                └─────────────────────────────────────────────────────┐
                                                                       ▼
                                                              [ChromaDB — PersistentClient]
                                                               ├ audit_reports_..._text
                                                               └ audit_reports_..._table
                                                                       │
      [POST /api/chat]                                                  │
            │                                                           │
            ▼  chroma/query_parser.py  (연도·컨텐츠 타입 추출)           │
            ▼  chroma/retriever.py     (텍스트+테이블 병렬 검색) ◀───────┘
            ▼  chroma/search_pipeline.py  (결과 병합·스코어링)
            │
            ▼  app/api/app/services/llm_service.py
               ├ provider=claude  →  Anthropic API
               ├ provider=ollama  →  Ollama (로컬)
               └ provider=mock   →  Mock 응답
            │
            ▼  ChatResponse (answer + citations)
```

---

## 프로젝트 구조

```
Financial-NLP-Analysis-System/
├── .github/workflows/
│   ├── ci.yml                         # Ruff + Pytest + Docker build
│   └── cd.yml                         # GHCR 이미지 배포
│
├── app/
│   ├── api/                           # FastAPI 백엔드
│   │   ├── app/
│   │   │   ├── main.py                # 앱 진입점, 라우터 등록, 시작 시 자동 인덱싱
│   │   │   ├── background/
│   │   │   │   └── chroma_indexer.py  # 업로드 후 백그라운드 ChromaDB 인덱싱
│   │   │   ├── core/
│   │   │   │   ├── config.py          # 환경변수 로딩 (app/api/.env)
│   │   │   │   └── auth_deps.py       # JWT 인증 의존성
│   │   │   ├── db/
│   │   │   │   ├── models.py          # User, ChatSession, Message, UploadedReport, IngestionJob
│   │   │   │   └── session.py         # SQLAlchemy 세션
│   │   │   ├── routes/
│   │   │   │   ├── chat.py            # POST /api/chat  (RAG 질의응답)
│   │   │   │   ├── upload.py          # POST /api/upload (HTM 업로드 + 인덱싱 트리거)
│   │   │   │   ├── files.py           # GET /api/files  (업로드 파일 목록/상태)
│   │   │   │   ├── chats.py           # GET/DELETE /api/chats (채팅 세션 관리)
│   │   │   │   ├── auth.py            # POST /api/auth/google
│   │   │   │   ├── ingest.py          # POST /api/ingest (연도별 수동 인덱싱)
│   │   │   │   ├── vector.py          # GET /api/vector/search
│   │   │   │   └── health.py          # GET /health
│   │   │   ├── services/
│   │   │   │   ├── rag_service.py     # run_rag() — 검색 + LLM 파사드
│   │   │   │   ├── llm_service.py     # Claude / Ollama / Mock 어댑터
│   │   │   │   ├── vector_store.py    # ChromaDB 연동 (텍스트+테이블 컬렉션)
│   │   │   │   ├── indexing.py        # JSON → NormalizedDocument 변환
│   │   │   │   ├── answering.py       # LLM 응답 생성 (레거시 경로)
│   │   │   │   ├── retrieval.py       # ChromaDB 검색 (레거시 경로)
│   │   │   │   ├── chat_history_service.py
│   │   │   │   ├── auth_service.py
│   │   │   │   └── router.py          # 질문 유형 분류
│   │   │   └── schemas/
│   │   │       ├── request.py         # ChatRequest (question, provider, model, ...)
│   │   │       └── response.py        # ChatResponse (answer, citations, ...)
│   │   ├── tests/
│   │   │   ├── test_qa.py
│   │   │   ├── test_vector.py
│   │   │   ├── test_vector_integration.py
│   │   │   ├── test_upload_indexing.py
│   │   │   └── ...
│   │   ├── .env.example               # 환경변수 템플릿
│   │   ├── requirements.txt           # API 전용 (하위호환 유지)
│   │   └── Dockerfile
│   │
│   ├── frontend/                      # React + Vite 프론트엔드
│   │   ├── src/
│   │   │   ├── pages/
│   │   │   │   ├── Login.jsx          # Google OAuth 로그인
│   │   │   │   └── ChatPage.jsx       # 채팅 UI (LLM 선택 포함)
│   │   │   └── components/
│   │   │       ├── Layout.jsx
│   │   │       └── FileUploader.jsx   # HTM 파일 업로드
│   │   ├── package.json
│   │   ├── package-lock.json
│   │   └── Dockerfile
│   │
│   └── ingest/                        # HTM 파싱 파이프라인
│       ├── src/pipeline.py            # HTM → 구조화 JSON
│       ├── tests/
│       └── Dockerfile
│
├── chroma/                            # 검색 파이프라인
│   ├── search_pipeline.py             # 파서 → 검색기 → 결과 통합
│   ├── retriever.py                   # 텍스트+테이블 병렬 검색, 스코어 병합
│   ├── query_parser.py                # 질문에서 연도·컨텐츠 타입 추출
│   ├── load_text_to_chroma.py         # 텍스트 컬렉션 일괄 적재
│   ├── load_table_to_chroma.py        # 테이블 컬렉션 일괄 적재
│   ├── evaluation.py                  # 검색 성능 평가
│   ├── reranker.py                    # Cross-encoder 재순위 실험
│   └── data_process/
│       ├── structured_flatten.py      # JSON → 청크 평탄화
│       ├── enrich_flattened_for_rag.py# 메타데이터 보강
│       └── json_to_sqlite.py          # 테이블 → SQLite
│
├── data/
│   ├── raw/                           # 감사보고서 원본 HTM (2014–2024)
│   └── processed/                     # 파이프라인 출력 JSON (gitignore)
│
├── docs/                              # 실험 기록 및 설계 문서
├── docker-compose.yml
├── requirements.txt                   # 통합 Python 의존성 (Python 3.11)
└── .env.example                       # 환경변수 빠른 참조
```

---

## 환경변수 설정

```bash
cp app/api/.env.example app/api/.env
```

| 변수 | 설명 | 기본값 |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude API 키 | — |
| `CLAUDE_MODEL` | 사용할 Claude 모델 | `claude-sonnet-4-6` |
| `OLLAMA_BASE_URL` | Ollama 서버 주소 | `http://localhost:11434` |
| `OLLAMA_MODEL` | Ollama 모델명 | `llama3` |
| `JWT_SECRET_KEY` | JWT 서명 키 (`openssl rand -hex 32`) | — |
| `GOOGLE_CLIENT_ID` | Google OAuth 클라이언트 ID | — |
| `MOCK_MODE` | `true` 이면 ChromaDB 없이 실행 | `false` |
| `LLM_MODE` | `mock` 이면 LLM 항상 Mock 응답 | — |
| `CHROMA_PERSIST_PATH` | ChromaDB 저장 경로 | `chroma_store` |
| `APP_DB_URL` | SQLite 경로 | `sqlite:///data/app.db` |

> ⚠️ `.env` 파일은 `.gitignore`로 보호됩니다. 절대 커밋하지 마세요.

### LLM 선택 (요청 시 동적 지정)

```json
POST /api/chat
{
  "question": "2023년 매출채권 금액은?",
  "provider": "claude",
  "model": "claude-sonnet-4-6"
}
```

`provider`: `"claude"` | `"ollama"` | `"mock"` | 미지정(API 키 유무로 자동 선택)

---

## 네트워크 구조

```
[호스트 머신]
   ├─ localhost:8501  →  frontend 컨테이너 (React/Nginx)
   ├─ localhost:8000  →  api 컨테이너 (FastAPI)
   └─ localhost:11434 →  Ollama (호스트에서 직접 실행)

[Docker 내부 네트워크]
   ├─ frontend  ──HTTP──▶  api:8000
   ├─ api       ──HTTP──▶  chroma:8000  (ChromaDB)
   ├─ api       ──HTTP──▶  host.docker.internal:11434  (Ollama)
   └─ ingest    ──HTTP──▶  chroma:8000
      (profiles: ingest — 별도 실행)
```

---

## 커밋 규칙

| 타입 | 내용 |
|---|---|
| `feat` | 새로운 기능 |
| `fix` | 버그 수정 |
| `refactor` | 코드 리팩터링 |
| `test` | 테스트 코드 |
| `chore` | 설정, 의존성 등 기타 수정 |
| `docs` | 문서 수정 |
| `build` | 빌드·모듈 관련 |
| `ci` | CI/CD 설정 |
| `perf` | 성능 개선 |

---

## 의존성

> 전체 Python 의존성은 루트 `requirements.txt` 한 파일로 관리 (Python 3.11)

```
# Web framework
fastapi==0.116.1
uvicorn[standard]==0.35.0
pydantic==2.11.7

# DB
sqlalchemy==2.0.41

# HTTP client
httpx==0.28.1

# LLM
anthropic>=0.40.0

# Vector DB
chromadb==0.5.23
sentence-transformers==3.0.1

# Auth
PyJWT==2.10.1
passlib[bcrypt]==1.7.4
python-multipart==0.0.12
google-auth>=2.29.0

# Data processing
pandas==2.3.3
numpy==2.4.3
scipy==1.16.3
beautifulsoup4==4.12.3
lxml==5.3.0
html5lib==1.1
regex==2024.11.6
pathlib2==2.3.7.post1

# Streamlit (선택)
streamlit==1.45.1
requests==2.32.3

# Env / Test / Lint
python-dotenv==1.0.1
pytest==8.4.2
pytest-cov==6.2.1
anyio[trio]==4.9.0
ruff==0.12.7
```

Node.js 의존성은 `app/frontend/package-lock.json` 기준으로 `npm ci`로 재현한다.
