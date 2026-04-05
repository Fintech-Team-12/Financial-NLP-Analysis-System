# Model Selection

## 1. Overall Goal
감사보고서 질의응답 시스템에서 사용자 질문을 적절한 문맥으로 연결하고, 그 문맥을 바탕으로 답변을 생성할 수 있도록 검색 및 후처리 구조를 설계한다.

본 프로젝트에서 모델 선정은 다음 세 가지 영역으로 나누어 검토하였다.

- Embedding model
- Retrieval / reranking strategy
- Answer generation structure

---

## 2. Embedding Model

### Selected Model
- `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`

### Selection Reason
- 한국어를 포함한 다국어 문서 검색에 사용 가능한 범용 multilingual embedding 모델이다.
- 감사보고서와 같은 한국어 재무/회계 문서에 대해 기본적인 dense retrieval을 빠르게 구성할 수 있다.
- ChromaDB와 연동이 간단하고, 로컬 환경에서도 실행 가능하다.
- 시간 제약상 embedding 모델 다중 비교보다는 retrieval 파이프라인 자체의 정교화가 더 중요하다고 판단하였다.

### Final Decision
- 본 프로젝트에서는 위 embedding 모델을 baseline embedding으로 유지하였다.

---

## 3. Retrieval Structure

### Collection Design
문서는 content type에 따라 두 개의 컬렉션으로 분리하였다.

- text collection
- table collection

### Why Split Text and Table
- 설명형 질문과 수치/표 질문의 검색 대상이 다르다.
- 예를 들어 "책임이 뭐야?"는 text가 적합하고,
  "유형자산 표 보여줘", "법인세비용 수치 알려줘"는 table이 적합하다.
- 따라서 질문 의도에 따라 검색 컬렉션을 다르게 선택하는 구조가 더 적절하다.

### Final Retrieval Pipeline
최종 baseline retrieval은 다음 구조를 사용하였다.

1. Query parsing
2. Question intent classification
3. Text / table collection routing
4. General retrieval
5. Section/title hint-based retrieval
6. Merge and heuristic score-based reranking

---

## 4. Query Parsing Strategy

질문을 그대로 검색하지 않고, 다음 정보를 추출하였다.

- year
- clean_query
- question intent
- preferred content type
- section/title hint

### Example
- "유형자산 표 보여줘"  
  → clean_query: `유형자산`  
  → preferred content type: `table`

- "재무제표에 대한 경영진의 책임이 뭐야?"  
  → clean_query: `재무제표 경영진 책임이`  
  → section_title_hint: `재무제표에 대한 경영진의 책임`  
  → preferred content type: `text`

---

## 5. Reranking Strategy

### Baseline Reranking
초기 baseline에서는 별도 모델 기반 reranker 대신, 다음 기준을 사용하는 heuristic rerank를 사용하였다.

- preferred content type 일치 여부
- section_title exact / partial match
- top_section exact / partial match
- section_path match
- document 내부 keyword 포함 여부

### Why This Was Effective
- 감사보고서 질의는 섹션 제목 자체가 정답인 경우가 많다.
- 예를 들어:
  - 재무제표에 대한 경영진의 책임
  - 포괄손익계산서
  - 유형자산
- 따라서 title / section metadata를 이용한 후처리만으로도 성능이 크게 개선되었다.

---

## 6. Model-based Reranker Experiment

### Tested Model
- `cross-encoder/ms-marco-MiniLM-L-6-v2`

### Purpose
dense retrieval + heuristic merge 이후의 후보들을 다시 query-document relevance 기준으로 재정렬하기 위함이다.

### Result Summary
실험 결과, 현재 테스트 질의셋에서는 model-based reranker가 baseline보다 일관된 성능 개선을 주지 못했다.

예를 들어 일부 질의에서는 baseline top1이 정답이었지만, reranker 적용 후 다른 문서가 top1로 올라와 성능이 악화되었다.

### Interpretation
- 현재 baseline retrieval이 이미 strong heuristic 구조를 가지고 있다.
- 사용한 cross-encoder는 영어 중심 모델이며, 한국어 감사보고서 문서에 최적화된 reranker라고 보기 어렵다.
- 현재 질의셋에서는 heuristic + hint 기반 구조가 더 안정적이었다.

### Final Decision
- model-based reranker는 실험은 수행했지만, 최종 선택에서는 채택하지 않았다.
- 최종 retrieval 구조는 heuristic + hint 기반 baseline을 유지하였다.

---

## 7. Final Selection Summary

### Final Embedding Model
- `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`

### Final Retrieval Strategy
- text/table split collections
- query parsing
- intent-based routing
- general retrieval + hint-based retrieval merge
- heuristic score-based rerank

### Final Reranker Decision
- 별도 cross-encoder reranker는 비교 실험만 수행
- 최종 선택은 baseline heuristic reranking 유지

---

## 8. Answer Generation Strategy

현재 answer generation은 retrieval 결과를 바탕으로 prompt를 구성한 뒤, LLM이 근거 기반 답변을 생성하도록 설계하였다.

현재 단계에서는:
- retrieval 결과 formatting
- prompt construction
- mock response generation

까지 구현하였고, 실제 LLM provider 연결은 후속 단계에서 쉽게 교체 가능하도록 service 형태로 분리하였다.

---

## 9. Conclusion

본 프로젝트에서는 단순히 모델 하나를 교체하기보다,  
질문 해석 → 검색 전략 → 후보 병합 → 근거 문맥 구성의 전체 흐름을 정교화하는 것이 더 중요하다고 판단하였다.

그 결과, multilingual embedding + text/table 분리 검색 + hint 기반 retrieval merge 구조가 현재 태스크에 가장 적합한 baseline으로 선정되었다.