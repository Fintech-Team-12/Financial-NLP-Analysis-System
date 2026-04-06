# Retrieval Notes

## 1. Chroma Storage
- path: `chroma/chroma_store`
- text collection: `audit_reports_10years_text_minilm`
- table collection: `audit_reports_10years_table_minilm`

## 2. Current Collection Status
- text documents: `3162`
- table documents: `3385`

## 3. Shared Metadata Schema
두 컬렉션 모두 아래 metadata key를 공통적으로 사용한다.

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

이 구조를 기준으로 year filtering, section/title hint retrieval, content-type routing을 수행한다.

## 4. Year Distribution

### Text
- 2014: 346
- 2015: 338
- 2016: 360
- 2017: 357
- 2018: 363
- 2019: 316
- 2020: 277
- 2021: 280
- 2022: 280
- 2023: 122
- 2024: 123

### Table
- 2014: 320
- 2015: 324
- 2016: 349
- 2017: 313
- 2018: 363
- 2019: 444
- 2020: 320
- 2021: 312
- 2022: 316
- 2023: 161
- 2024: 163

## 5. Section Type Distribution

### Text
- `leaf_section`: 706
- `top_section`: 97
- `subsection`: 2359

### Table
- `table`: 3385

## 6. Current Retrieval Design
1. Query parsing
2. Intent classification
3. Text / table routing
4. General retrieval
5. Section title / top section hint retrieval
6. Merge and heuristic reranking

## 7. Notes
- text/table 분리 구조는 정상적으로 유지된다.
- text와 table 모두 2014~2024 연도 데이터를 포함한다.
- text preview와 table preview가 구조화된 문자열 형태로 저장되어 retrieval에 유리하다.
- 동일 주제의 여러 연도 문서가 함께 retrieval 후보로 올라올 수 있다.