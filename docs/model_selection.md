# Model Selection

## 1. Overall Objective

감사보고서 질의응답 시스템에서 사용자 질문에 맞는 문맥을 효과적으로 검색하고, 해당 문맥을 기반으로 답변 생성이 가능하도록 검색/후처리 구조를 설계한다.

본 프로젝트에서는 다음 세 가지를 중심으로 모델 및 구조를 검토하였다.

- Embedding model
- Retrieval / reranking strategy
- Answer generation structure

---

## 2. Embedding Model

### Selected Embedding Model
- `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`

### Selection Reason
- 한국어를 포함한 다국어 문서 검색에 사용할 수 있는 multilingual embedding 모델이다.
- 감사보고서와 같은 한국어 재무/회계 문서 retrieval baseline을 빠르게 구축할 수 있다.
- ChromaDB와의 연동이 용이하고 로컬 환경에서도 실험 가능하다.
- 시간 제약상 embedding 모델 다중 비교보다는 retrieval pipeline 구조 최적화가 더 중요하다고 판단하였다.

### Final Decision
- embedding model은 `paraphrase-multilingual-MiniLM-L12-v2`를 유지하였다.

---

## 3. Retrieval Strategy

### Collection Design
문서는 content type에 따라 두 개의 컬렉션으로 분리하였다.

- text collection
- table collection

### Why Split Text and Table
- 설명형 질문과 수치/표 질문은 필요한 문맥이 다르다.
- 예를 들어,
  - "재무제표에 대한 경영진의 책임이 뭐야?" → text 중심
  - "유형자산 표 보여줘", "법인세비용 수치 알려줘" → table 중심
- 따라서 질문 의도에 따라 적절한 collection으로 라우팅하는 것이 더 효율적이라고 판단하였다.

### Final Retrieval Pipeline
최종 retrieval baseline은 다음 구조를 사용한다.

1. Query parsing
2. Intent classification
3. Text / table routing
4. General retrieval
5. Section title / top section hint-based retrieval
6. Merge and heuristic score-based reranking

---

## 4. Query Parsing Design

질문을 그대로 dense retrieval에 넣지 않고 다음 정보를 추출한다.

- year
- clean_query
- question intent
- preferred content type
- section/title hint

### Example
- "유형자산 표 보여줘"
  - clean_query: `유형자산`
  - preferred content type: `table`
  - section_title_hint: `유형자산`

- "재무제표에 대한 경영진의 책임이 뭐야?"
  - clean_query: `재무제표 경영진 책임이`
  - preferred content type: `text`
  - section_title_hint: `재무제표에 대한 경영진의 책임`

### Why This Matters
감사보고서 질의는 section title 자체가 정답이 되는 경우가 많기 때문에, 단순 dense retrieval보다 question parsing + hint extraction이 큰 효과를 보였다.

---

## 5. Baseline Retrieval Result

재파싱/재적재 이후 baseline retrieval 평가 결과는 다음과 같다.

- Top1 hit: 5/5
- Top3 hit: 5/5

테스트 질의셋 기준으로 현재 baseline retrieval은 충분히 안정적이라고 판단하였다.

---

## 6. Reranker Candidate

### Tested Reranker
- `cross-encoder/ms-marco-MiniLM-L-6-v2`

### Purpose
dense retrieval + heuristic merge 이후의 후보 집합을 query-document relevance 기준으로 다시 재정렬하기 위함이다.

---

## 7. Reranker Experiment Result

재적재 이후 rerank evaluation 결과는 다음과 같다.

- Baseline Top1 hit: 5/5
- Baseline Top3 hit: 5/5
- Rerank Top1 hit: 5/5
- Rerank Top3 hit: 5/5

### Interpretation
reranker는 일부 질의에서 top1 문서의 순서를 바꾸었으나, hit rate 기준으로는 baseline 대비 명확한 성능 향상을 보여주지 않았다.  
즉, 현재 실험에서는 reranker의 주요 효과가 “정답 후보 내 순서 재조정”에 가까웠다.

또한 사용한 cross-encoder는 영어 중심 모델이므로, 한국어 감사보고서 질의응답에 완전히 최적이라고 보기 어렵다.

---

## 8. Final Selection

### Final Embedding Model
- `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`

### Final Retrieval Structure
- text/table split collections
- query parsing
- general retrieval
- hint-based retrieval merge
- heuristic score-based reranking

### Final Reranker Decision
- model-based reranker는 비교 실험만 수행
- 최종 채택은 보류
- 현재 프로젝트에서는 baseline retrieval 구조를 최종 선택

### Why
현재 테스트셋에서는 baseline만으로도 Top1/Top3 모두 100%를 달성했고, reranker가 명확한 추가 개선을 제공하지 않았기 때문이다.  
또한 baseline은 해석 가능성과 구조적 설명이 쉬워 발표 및 협업 측면에서도 더 적합하다.

---

## 9. LLM Answer Generation Structure

현재 answer generation은 retrieval 결과를 기반으로 prompt를 구성하고, 해당 문맥을 바탕으로 답변을 생성하도록 설계하였다.

현재 구현 상태:
- retrieval 결과 formatting
- answer prompt construction
- mock response generation
- rag service 연결

즉, 실제 LLM provider 연결 전 단계까지 구조를 분리하여 구현해두었고, 이후 backend 서비스에서 쉽게 이어서 연결할 수 있도록 설계하였다.

---

## 10. Conclusion

본 프로젝트에서는 단순히 모델 하나를 바꾸기보다, 질문 구조 해석과 metadata 활용을 포함한 retrieval pipeline 설계를 더 중요하게 보았다.

그 결과,
- multilingual embedding
- text/table 분리 retrieval
- hint 기반 retrieval merge
- heuristic rerank

구조가 현재 태스크에 가장 적합한 baseline으로 선정되었다.