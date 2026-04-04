# Retrieval Notes

## 1. Current Chroma Setup

### Collection / Storage
- **Collection name**: `audit_reports_2014`
- **Chroma path**: `./chroma_store`

### Embedding Model
- **Embedding function**:
  `SentenceTransformerEmbeddingFunction`
- **Model name**:
  `paraphrase-multilingual-MiniLM-L12-v2`

### Current Document Ingestion
- Chroma document에는 `row["embedding_text"]`가 들어감
- Chroma metadata에는 아래 필드가 들어감:
  - `year`
  - `company`
  - `report_type`
  - `section_path`
  - `section_title`
  - `content_type`
- Chroma id에는 `row["chunk_id"]`가 들어감

### Current Chroma Record Mapping
- `documents.append(row["embedding_text"])`
- `metadatas.append({...})`
- `ids.append(row["chunk_id"])`

---

## 2. Upstream Data Processing Pipeline

### structured_flatten.py
- 원본 structured JSON을 **flat record** 형태로 변환
- text와 table을 **별도 record**로 나누어 생성
- 각 record에 section/category/path/title/content 관련 기본 필드 부여

### enrich_flattened_for_rag.py
- flattened record를 RAG 검색에 적합하도록 보강
- 주요 추가 필드:
  - `embedding_text`
  - `chunk_id`
  - `token_count`
  - `item_canonical_key`
  - `is_leaf`
  - `amount_unit`
  - 기타 enrich metadata

---

## 3. Embedding Text Structure

현재 Chroma에 들어가는 document는 `embedding_text` 기반이다.

### embedding_text 구성 원칙
- **section_title 우선**
- 이후 note/company/year/report_type 순으로 보강
- path / content_type / amount_unit 등 메타 정보 포함
- 마지막에 실제 본문(content_text) 포함

### 요약 구조
- `section_title`
- `note_number`
- `company`
- `year`
- `report_type`
- `section_path`
- `content_type`
- `amount_unit`
- `content_text`

즉, 검색 시 핵심 제목(section_title)이 먼저 보이도록 설계되어 있음.

---

## 4. Text / Table Handling

### Current Design
- text와 table은 **각각 별도 record**로 존재
- table record도 단순 구조 데이터가 아니라,
  문자열화된 `content_text`를 가짐
- 따라서 table도 일반 텍스트처럼 임베딩 및 검색 가능

### Implication
- 현재 collection에는 text와 table이 함께 들어가 있음
- 일부 질의에서는 **설명 text보다 table이 먼저 retrieval**될 수 있음
- 향후:
  - text/table 분리 collection
  - content_type 기반 filtering
  - text 우선 ranking
  등을 검토할 수 있음

---

## 5. Current Metadata Fields in Chroma

현재 Chroma metadata에 적재되는 필드:
- `year`
- `company`
- `report_type`
- `section_path`
- `section_title`
- `content_type`

### Notes
- upstream 단계에서는 더 풍부한 필드가 존재함
- 현재는 일부 핵심 필드만 metadata로 적재 중
- 향후 retrieval 개선을 위해 아래 필드 추가 적재 가능성 검토:
  - `note_number`
  - `section_category`
  - `section_id`
  - `parent_section_id`
  - `item_canonical_key`
  - `has_table`
  - `is_leaf`

---

## 6. Current Observations

### Strengths
- 2014년 감사보고서 기준 Chroma 적재 및 retrieval 테스트 가능
- multilingual embedding 모델 적용 완료
- section_title 우선 embedding_text로 검색 친화성 개선
- text/table 모두 검색 가능한 구조 확보

### Current Limitations
- 현재 test query는 pure vector retrieval 기반
- metadata filter 미적용
- reranker 미적용
- text와 table이 한 collection에 혼재
- 일부 질의에서 table이 먼저 노출될 가능성 있음

---

## 7. Planned Retrieval Improvements

### Step 1. Collection Inspection
- 현재 collection 구조 직접 확인
- sample ids / metadata / document format 점검

### Step 2. Baseline Retriever
- Chroma query를 함수화
- top-k retrieval wrapper 작성

### Step 3. Query Parsing
- 사용자 질문에서 다음 정보 추출
  - year
  - keyword
  - text/table intent
- retrieval 전 query 정제 수행

### Step 4. Metadata-aware Retrieval
- year / content_type 등 metadata filter 적용 검토

### Step 5. Reranking
- 1차 retrieval 결과에 대해 rerank 적용
- text/table 혼재 문제 완화 시도

### Step 6. API Integration
- retrieval pipeline을 backend API와 연결
- 이후 LLM answer generation과 결합

---

## 8. Open Questions

- text/table을 하나의 collection으로 유지할지, 분리할지
- metadata 필드를 현재보다 더 풍부하게 넣을지
- reranker를 어떤 모델로 선택할지
- query parsing을 rule-based로 시작할지, LLM 기반으로 확장할지
- answer generation용 LLM과 query refinement용 LLM을 분리할지