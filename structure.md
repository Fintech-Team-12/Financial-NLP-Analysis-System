<!-- # Current Structure
```bash
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
```

# 구조
api: FastAPI + RAG endpoint<br>
frontend: Streamlit 혹은 js(가능하다면..)<br>
ingest: HTML 파싱/전처리/인덱싱 파이프라인<br>
chroma: 벡터 저장소 볼륨(faiss사용해도 됨)<br>
data/processed: SQLite 산출물(json 형식일수도)<br>
cd.yml: main 반영 후 GHCR 이미지 배포 (dockerhub도 가능)<br>
ci.yml: ruff + pytest + docker compose config + image build<br>



# 커밋 규칙
타입 이름	내용<br>
feat	새로운 기능에 대한 커밋<br>
fix	버그 수정에 대한 커밋<br>
build	빌드 관련 파일 수정 / 모듈 설치 또는 삭제에 대한 커밋<br>
chore	그 외 자잘한 수정에 대한 커밋<br>
ci	ci 관련 설정 수정에 대한 커밋<br>
docs	문서 수정에 대한 커밋<br>   
style	코드 스타일 혹은 포맷 등에 관한 커밋<br>
refactor	코드 리팩토링에 대한 커밋<br>
test	테스트 코드 수정에 대한 커밋<br>
perf	성능 개선에 대한 커밋<br> -->
