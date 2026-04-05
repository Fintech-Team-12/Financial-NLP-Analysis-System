# Retrieval Notes

## 1. Current Chroma Storage

### Chroma Path
- `chroma/chroma_store`

### Collections
- text collection: `audit_reports_10years_text_minilm`
- table collection: `audit_reports_10years_table_minilm`

---

## 2. Current Collection Statistics

### Text Collection
- total documents: `2636`

### Table Collection
- total documents: `2829`

---

## 3. Metadata Schema

text/table 컬렉션 모두 아래 metadata key를 공통적으로 사용한다.

- `chunk_id`
- `company`
- `content_type`
- `doc_id`
- `note_number`
- `order_index`
- `report_type`
- `section_level`
- `section_path`
- `section_title`
- `section_type`
- `top_section`
- `year`

이 구조를 기준으로 year filtering, section/title hint retrieval, content type routing을 수행한다.

---

## 4. Content Type Distribution

### Text Collection
- `text`: 2636

### Table Collection
- `table`: 2829

---

## 5. Year Distribution

### Text Collection
- 2014: 278
- 2015: 271
- 2016: 223
- 2017: 291
- 2018: 229
- 2019: 262
- 2020: 277
- 2021: 280
- 2022: 280
- 2023: 122
- 2024: 123

### Table Collection
- 2014: 244
- 2015: 246
- 2016: 244
- 2017: 238
- 2018: 255
- 2019: 330
- 2020: 320
- 2021: 312
- 2022: 316
- 2023: 161
- 2024: 163

현재는 text/table 모두 2014~2024 연도 데이터를 포함한다.

---

## 6. Section Type Distribution

### Text Collection
- `leaf_section`: 527
- `top_section`: 97
- `subsection`: 2012

### Table Collection
- `table`: 2829

---

## 7. Current Retrieval Design

현재 retrieval 구조는 다음과 같다.

1. Query parsing
2. Question intent classification
3. Text / table collection routing
4. General retrieval
5. Section title / top section hint-based retrieval
6. Merge and heuristic score-based reranking

---

## 8. Observations After Re-parsing / Re-loading

- collection 구조는 정상적으로 text/table 분리 유지됨
- metadata schema는 이전과 동일하게 유지됨
- text와 table 모두 2024 데이터가 포함됨
- text preview와 table preview가 더 구조화된 문자열 형태로 저장되어 retrieval에 유리해짐
- 같은 section에 대해 여러 chunk가 상위에 함께 노출될 수 있어, 후속적으로 deduplication 기준을 더 정교하게 만들 여지가 있음

---

## 9. Interpretation

현재 Chroma collection 상태는 retrieval pipeline이 안정적으로 동작하기에 적절하다.  
특히 section_title, top_section, section_path 기반 힌트 검색과 metadata-aware 후처리를 적용하기 좋은 구조이다.