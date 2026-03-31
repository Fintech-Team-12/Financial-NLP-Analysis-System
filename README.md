# Financial Audit RAG

Minimal project scaffold for Samsung audit report RAG assignment.


# Sample Structure

rag_finance_project/
├── .github/
│   └── workflows/
│       ├── ci.yml
│       └── cd.yml
├── app/
│   ├── api/
│   │   ├── app/
│   │   │   └── main.py
│   │   ├── tests/
│   │   │   ├── test_ask.py
│   │   │   └── test_health.py
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   ├── frontend/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── streamlit_app.py
│   └── ingest/
│       ├── src/
│       │   └── pipeline.py
│       ├── Dockerfile
│       └── requirements.txt
├── chroma/
├── data/
│   ├── raw/
│   └── processed/
├── docs/
├── scripts/
│   └── run_quality.sh
├── .dockerignore
├── .env
├── .gitignore
├── docker-compose.yml
└── README.md


api: FastAPI + RAG endpoint
frontend: Streamlit 혹은 js(가능하다면..)
ingest: HTML 파싱/전처리/인덱싱 파이프라인
chroma: 벡터 저장소 볼륨(faiss사용해도 됨)
data/processed: SQLite 산출물(json 형식일수도)
cd.yml: main 반영 후 GHCR 이미지 배포 (dockerhub도 가능)
ci.yml: ruff + pytest + docker compose config + image build

