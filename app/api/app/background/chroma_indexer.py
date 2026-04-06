"""
ChromaDB 백그라운드 색인 작업.

FastAPI BackgroundTasks 에서 호출된다.
요청 세션과 완전히 분리 — 내부에서 자체 DB 세션을 생성한다.

주의: 이 함수에 request-scoped db session 을 절대 전달하지 말 것.
요청이 끝나면 세션이 닫히므로 백그라운드 작업에서 사용하면 에러가 발생한다.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from app.db.models import IngestionJob
from app.db.session import get_session
from app.services import indexing, vector_store

_log = logging.getLogger(__name__)


def run_chroma_indexing(job_id: int, json_path_str: str) -> None:
    """
    structured JSON 파일을 디스크에서 직접 읽어
    text 컬렉션과 table 컬렉션 모두에 upsert.

    흐름:
      1. job status = running 으로 업데이트
      2a. 텍스트 색인: load_documents_from_file() → index_normalized_documents()
      2b. 테이블 색인: load_table_chunks_from_file() → index_uploaded_table_chunks()
          (텍스트 색인 성공·실패와 무관하게 독립적으로 시도)
      3. job status = done / failed 로 업데이트

    실패 시맨틱:
      텍스트 실패       → status="failed",  error_message 에 원인 기록
      텍스트 성공·테이블 실패 → status="done", error_message 에 경고 기록
      둘 다 실패         → status="failed",  error_message 에 두 원인 기록

    각 DB 조작은 독립적인 get_session() 블록으로 처리한다.
    get_session() 은 블록 종료 시 자동 commit 하므로 db.commit() 을 호출하지 않는다.
    """
    # ── 1. 시작 마킹 ─────────────────────────────────────────────────────────
    with get_session() as db:
        job = db.get(IngestionJob, job_id)
        if not job:
            _log.error("IngestionJob %d 를 찾을 수 없음", job_id)
            return
        job.status = "running"
        job.started_at = datetime.now(timezone.utc)

    # ── 2. 색인 실행 ──────────────────────────────────────────────────────────
    text_count = 0
    table_count = 0
    error_parts: list[str] = []
    final_status = "done"

    json_path = Path(json_path_str)

    # ── 2a. 텍스트 색인 ───────────────────────────────────────────────────────
    try:
        docs = indexing.load_documents_from_file(json_path)
        if not docs:
            raise ValueError(
                f"파싱된 문서가 없습니다: {json_path_str}. "
                "파일이 올바른 structured JSON 형식인지 확인하세요."
            )
        result = vector_store.index_normalized_documents(docs, force=True)
        text_count = result.get("indexed", 0)
        _log.info("job_id=%d: 텍스트 색인 완료 — %d건", job_id, text_count)
    except Exception as exc:
        _log.error("job_id=%d 텍스트 색인 실패: %s", job_id, exc)
        final_status = "failed"
        error_parts.append(f"텍스트 색인 실패: {str(exc)[:400]}")

    # ── 2b. 테이블 색인 (텍스트 결과와 무관하게 독립 시도) ───────────────────
    try:
        table_chunks = indexing.load_table_chunks_from_file(json_path)
        if table_chunks:
            result = vector_store.index_uploaded_table_chunks(table_chunks, force=True)
            table_count = result.get("indexed", 0)
            _log.info("job_id=%d: 테이블 색인 완료 — %d건", job_id, table_count)
        else:
            _log.info("job_id=%d: 테이블 청크 없음 — 스킵", job_id)
    except Exception as exc:
        _log.error("job_id=%d 테이블 색인 실패: %s", job_id, exc)
        # 텍스트가 성공했으면 status 는 "done" 유지, 경고만 error_message 에 기록
        error_parts.append(f"테이블 색인 실패: {str(exc)[:400]}")

    # ── 3. 완료 마킹 ─────────────────────────────────────────────────────────
    error_msg = "; ".join(error_parts)[:1000] if error_parts else None
    total_indexed = text_count + table_count

    with get_session() as db:
        job = db.get(IngestionJob, job_id)
        if job:
            job.status = final_status
            job.indexed_count = total_indexed
            job.finished_at = datetime.now(timezone.utc)
            if error_msg:
                job.error_message = error_msg
