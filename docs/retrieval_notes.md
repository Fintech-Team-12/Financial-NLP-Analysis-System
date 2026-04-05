# 노트
text 컬렉션 이름: audit_reports_10years_text_minilm
table 컬렉션 이름: audit_reports_10years_table_minilm
Chroma 경로: ./chroma_store

두 컬렉션 모두 같은 임베딩 모델 sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2를 사용 
SQLite의 audit_chunks에서 embedding_text를 document로 넣습니다.

metadata에는 chunk_id, doc_id, year, company, report_type, top_section, note_number, section_path, section_level, section_title, section_type, content_type, order_index가 들어갑니다.

# 이전단계 진행 사항
text/table 컬렉션 분리 적재 완료
metadata key는 두 컬렉션에서 동일
text는 2014~2024, table은 2014~2023
2024 table 질의 시 fallback 필요
text 컬렉션은 설명형 질의, table 컬렉션은 수치/표 질의에 우선 사용 가능


# retriever 구조
collection 라우팅 + 공통 filter 구조