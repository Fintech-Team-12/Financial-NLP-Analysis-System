# Agent Flow

## 1. Goal
사용자 질문을 그대로 벡터 검색에 넣지 않고,  
질문의 의도와 구조를 분석한 뒤 검색 전략을 결정하여  
더 적절한 retrieval과 answer generation을 수행한다.

---

## 2. High-Level Flow

사용자 질문 입력  
→ 질문 전처리  
→ 질문 구조 분석  
→ 검색 계획 생성  
→ Chroma retrieval  
→ 필요 시 rerank  
→ context 정리  
→ LLM answer generation  
→ 응답 반환

---

## 3. Detailed Flow

### Step 1. User Input
사용자가 자연어 질문을 입력한다.

예:
- 2014년 현금및현금성자산 알려줘
- 유형자산 표 보여줘
- 재무제표에 대한 경영진의 책임이 뭐야?

### Step 2. Query Parsing
사용자 질문에서 아래 정보를 추출한다.

- year
- keyword
- question intent
- preferred content type (text / table)
- cleaned query

### Step 3. Search Plan Generation
질문 분석 결과를 바탕으로 retrieval 전략을 정한다.

예:
- 설명형 질문 → text 우선
- 수치형 / 표 요청 질문 → table 우선
- 연도 언급 시 year filter 적용
- 특정 section title 언급 시 keyword 강화

### Step 4. Retrieval
검색 전략에 따라 Chroma 검색을 수행한다.

가능한 방식:
- 기본 dense retrieval
- metadata filter 적용 retrieval
- 향후 text/table 분리 collection 라우팅

### Step 5. Reranking
초기 retrieval 결과를 query relevance 기준으로 재정렬한다.

목적:
- 질문 의도와 더 맞는 문서를 상위에 배치
- text/table 혼재 문제 완화

### Step 6. Context Construction
최종 retrieval 결과를 LLM 입력용 context로 정리한다.

포함 가능 요소:
- document snippet
- section_title
- section_path
- content_type
- year

### Step 7. Answer Generation
LLM이 retrieval context를 바탕으로 답변을 생성한다.

원칙:
- 검색된 근거 기반 답변
- 불확실할 경우 추정하지 않음
- 가능하면 section_title 등 출처 정보 포함

### Step 8. Response Return
최종 사용자 응답 반환

예상 응답 구성:
- answer
- retrieved contexts
- citations / metadata
- debug info (optional)

---

## 4. Current Development Scope

### Can be implemented now
- query parsing
- search plan generation
- API request/response structure
- retrieval pipeline skeleton
- agent flow design

### Requires completed ingestion / collection
- actual Chroma inspection
- real retrieval validation
- evaluation metrics
- rerank before/after comparison

---

## 5. Planned Components

### In `chroma/`
- query_parser.py
- retriever.py
- search_pipeline.py
- evaluation.py
- reranker.py

### In `app/api/`
- routes/ask.py
- services/rag_service.py
- services/llm_service.py

---

## 6. Future Improvement Ideas
- text/table separate collection routing
- richer metadata filter
- reranker model comparison
- answer LLM and query-refinement LLM separation
- fallback strategy when retrieval confidence is low