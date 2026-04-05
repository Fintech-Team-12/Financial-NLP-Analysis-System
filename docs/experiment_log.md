# Experiment Log

## 1. Goal
감사보고서 기반 질의응답 시스템에서 retrieval 성능을 개선하고, 모델 기반 reranker 도입 여부를 비교 실험을 통해 판단한다.

---

## 2. Collection Inspection

### Collection Setup
- text collection: `audit_reports_10years_text_minilm`
- table collection: `audit_reports_10years_table_minilm`

### Inspection Findings
- text와 table이 분리 적재되어 있음
- metadata keys는 두 컬렉션에서 공통적으로 유지됨
- 주요 metadata:
  - year
  - company
  - report_type
  - section_path
  - section_title
  - content_type
  - top_section
  - note_number
  - section_level
  - section_type
  - order_index

### Interpretation
- 질의 의도에 따라 text/table 라우팅이 가능함
- metadata 기반 후처리 전략을 적용하기 적합한 구조임

---

## 3. Query Parsing Improvement

### Initial Problem
초기에는 질문을 그대로 dense retrieval에 넣었기 때문에 다음과 같은 문제가 있었다.

- "재무제표" 안의 "표" 때문에 table 의도로 잘못 분류됨
- "유형자산 표 보여줘"에서 clean_query가 충분히 정제되지 않음
- "포괄손익계산서 관련 내용 설명해줘"에서 불필요 표현이 남음

### Applied Fix
- year 추출
- clean_query 정제
- 표/수치형 힌트 강화
- 설명형 힌트 강화
- 대표 section/title keyword 기반 hint 추출

### Result
질문 해석 결과가 다음처럼 개선되었다.

- "유형자산 표 보여줘" → `table_lookup`, clean_query=`유형자산`
- "법인세비용 수치 알려줘" → `table_lookup`, clean_query=`법인세비용`
- "포괄손익계산서 관련 내용 설명해줘" → `text_explanation`, clean_query=`포괄손익계산서`

---

## 4. Retrieval Baseline Design

### Baseline Pipeline
1. Query parsing
2. Collection routing (text/table)
3. General retrieval
4. Section/title hint retrieval
5. Merge
6. Heuristic score-based reranking

### Rationale
감사보고서 질의는 section title이나 top section이 직접적으로 정답이 되는 경우가 많아, dense retrieval 결과에 metadata-aware boosting을 적용하는 것이 효과적이라고 판단하였다.

---

## 5. Baseline Evaluation

### Test Queries
- 2014년 현금및현금성자산 알려줘
- 유형자산 표 보여줘
- 재무제표에 대한 경영진의 책임이 뭐야?
- 법인세비용 수치 알려줘
- 포괄손익계산서 관련 내용 설명해줘

### Baseline Result
- Top1 hit: 5/5
- Top3 hit: 5/5

### Key Observations
- `현금및현금성자산`은 general retrieval만으로도 잘 검색됨
- `유형자산`, `재무제표에 대한 경영진의 책임`, `포괄손익계산서`는 section_title_hint가 큰 역할을 함
- `법인세비용`은 table retrieval이 효과적이었음

---

## 6. Model-based Reranker Experiment

### Tested Reranker
- `cross-encoder/ms-marco-MiniLM-L-6-v2`

### Experiment Setup
- baseline top candidates를 대상으로 cross-encoder reranking 수행
- baseline 결과와 rerank 결과를 CSV로 비교

### Result
- baseline Top1 hit: 5/5
- baseline Top3 hit: 5/5
- rerank Top1 hit: 일부 질의에서 유지, 일부 질의에서 악화
- rerank Top3 hit: 유지

### Example
- "2014년 현금및현금성자산 알려줘"의 경우 baseline top1은 정답이었으나, rerank 후 다른 문서가 top1이 되어 성능이 저하되었다.

### Interpretation
- 현재 baseline이 이미 강한 heuristic 구조를 가지고 있어 추가 모델 rerank의 이득이 크지 않았다.
- 사용 모델이 영어 중심 cross-encoder라 한국어 감사보고서 문서와 완전히 맞지 않았을 가능성이 있다.

### Decision
- model-based reranker는 실험만 수행하고, 최종 구조에는 채택하지 않음

---

## 7. Final Retrieval Decision

### Selected Final Pipeline
- multilingual embedding
- text/table split collections
- query parsing
- general retrieval + hint-based retrieval merge
- heuristic rerank

### Reason
현재 질의셋에서 가장 안정적이고 설명 가능한 결과를 제공했기 때문이다.

---

## 8. Remaining Work

### Implemented
- query parser
- retriever
- search pipeline
- evaluation
- reranker experiment
- llm service skeleton
- rag service skeleton

### Not Fully Finalized
- 실제 LLM provider 연결
- backend endpoint와 완전 통합
- frontend와의 연동
- 추가 질의셋 확장 평가

---

## 9. Conclusion

이번 실험에서는 단순 dense retrieval보다,  
질문 구조를 먼저 해석하고 section/title 정보를 적극 활용하는 retrieval 전략이 감사보고서 QA에 더 적합하다는 점을 확인하였다.

또한 모델 기반 reranker를 추가로 실험했지만, 현재 데이터와 질의셋에서는 heuristic + hint 기반 baseline이 더 안정적이라는 결론을 얻었다.