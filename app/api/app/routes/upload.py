"""POST /files/upload — HTML 감사보고서 업로드, 파싱, ChromaDB 색인."""
from __future__ import annotations

import logging
import os
import shutil
import sys
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.background.chroma_indexer import run_chroma_indexing
from app.core.auth_deps import get_current_user, get_db
from app.core.config import settings
from app.db.models import IngestionJob, UploadedReport, User
from app.services import indexing

_log = logging.getLogger(__name__)

# ── pipeline.py 임포트 ────────────────────────────────────────────────────────
INGEST_SRC_DIR = str(Path(settings._project_root) / "app" / "ingest" / "src")
if INGEST_SRC_DIR not in sys.path:
    sys.path.append(INGEST_SRC_DIR)

try:
    import pipeline
except ImportError:
    pipeline = None  # type: ignore[assignment]

router = APIRouter()


@router.post("/files/upload")
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    HTML 감사보고서를 업로드하여:
      1. 임시 파일 저장
      2. pipeline 으로 structured JSON 파싱  ← 기존 동작 유지
      3. in-memory _store 에 인덱싱          ← 기존 동작 유지
      4. UploadedReport / IngestionJob SQLite 레코드 생성  ← 신규
      5. BackgroundTasks 로 ChromaDB 색인 예약             ← 신규

    ChromaDB 색인이 실패해도 업로드 응답은 success=True 를 반환한다.
    색인 결과는 GET /api/files/{report_id}/status 로 확인 가능.
    """
    if not pipeline:
        raise HTTPException(status_code=500, detail="파싱 파이프라인 모듈을 찾을 수 없습니다.")

    # ── 1. 확장자 검증 ────────────────────────────────────────────────────────
    if not (file.filename.endswith(".htm") or file.filename.endswith(".html")):
        raise HTTPException(status_code=400, detail=".htm 또는 .html 파일만 허용됩니다.")

    # ── 2. 임시 디렉토리 준비 ─────────────────────────────────────────────────
    os.makedirs(settings.upload_temp_dir, exist_ok=True)
    temp_path = os.path.join(settings.upload_temp_dir, file.filename)

    try:
        # ── 3. 업로드 파일 임시 저장 ─────────────────────────────────────────
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # ── 4. HTML → structured JSON 파싱 (기존 동작 유지) ──────────────────
        result = pipeline.parse_single_file(temp_path, settings.processed_dir)

        year_str = result.get("year", "Unknown")
        if not str(year_str).isdigit():
            raise HTTPException(
                status_code=422,
                detail=f"파일에서 연도를 추출할 수 없습니다: {year_str}",
            )

        year = int(year_str)
        company = result.get("company_name", "Unknown")
        save_path: str = result.get("save_path", "")

        # ── 5. in-memory 인덱싱 (기존 동작 유지) ─────────────────────────────
        in_memory_count = indexing.ingest_single_file(Path(save_path), force=True)

        # ── 6. SQLite 레코드 생성 (신규) ─────────────────────────────────────
        report = UploadedReport(
            filename=file.filename,
            company=company,
            year=year,
            structured_json_path=save_path,
            uploaded_by=current_user.id,
        )
        db.add(report)
        db.flush()  # report.id 확보 (commit 전)

        job = IngestionJob(report_id=report.id, status="pending")
        db.add(job)
        db.commit()
        db.refresh(job)

        # ── 7. ChromaDB 백그라운드 색인 예약 (신규) ──────────────────────────
        # mock_mode 에서는 ChromaDB 미사용이므로 skip
        # 중요: db 세션을 절대 넘기지 않는다 — background 함수가 자체 세션을 연다
        chroma_status = "skipped_mock_mode"
        if not settings.mock_mode:
            background_tasks.add_task(run_chroma_indexing, job.id, save_path)
            chroma_status = "queued"

        _log.info(
            "업로드 완료: %s (year=%d, in_memory=%d, report_id=%d, job_id=%d, chroma=%s)",
            file.filename, year, in_memory_count, report.id, job.id, chroma_status,
        )

        return {
            "success": True,
            "report_id": report.id,
            "job_id": job.id,
            "filename": file.filename,
            "company": company,
            "year": year,
            "in_memory_indexed": in_memory_count,
            "chroma_status": chroma_status,
            "message": (
                f"파싱 완료 ({in_memory_count}건 in-memory 인덱싱). "
                f"ChromaDB 색인 상태 확인: GET /api/files/{report.id}/status"
            ),
        }

    except HTTPException:
        raise
    except Exception as exc:
        _log.exception("업로드 처리 실패: %s", exc)
        raise HTTPException(status_code=500, detail=f"처리 실패: {exc}") from exc

    finally:
        # ── 8. 임시 파일 삭제 ─────────────────────────────────────────────────
        if os.path.exists(temp_path):
            os.remove(temp_path)
