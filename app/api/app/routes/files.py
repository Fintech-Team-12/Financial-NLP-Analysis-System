"""GET /api/files/{report_id}/status — 업로드 파일 ChromaDB 색인 상태 조회."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth_deps import get_current_user, get_db
from app.db.models import IngestionJob, UploadedReport, User

router = APIRouter()


@router.get("/files/{report_id}/status")
def get_file_status(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    업로드된 파일의 ChromaDB 색인 작업 상태를 반환한다.

    status 값:
      pending  — 색인 대기 중
      running  — 색인 진행 중
      done     — 색인 완료 (indexed_count 확인 가능)
      failed   — 색인 실패 (error_message 확인 가능)
      no_job   — 색인 작업 레코드 없음 (mock_mode 업로드 등)
    """
    report = db.get(UploadedReport, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="해당 report 를 찾을 수 없습니다.")

    # 업로더 본인만 조회 가능 (uploaded_by=None 은 레거시 허용)
    if report.uploaded_by is not None and report.uploaded_by != current_user.id:
        raise HTTPException(status_code=403, detail="접근 권한이 없습니다.")

    # 가장 최근 job 조회
    job = (
        db.query(IngestionJob)
        .filter(IngestionJob.report_id == report_id)
        .order_by(IngestionJob.id.desc())
        .first()
    )

    return {
        "report_id": report_id,
        "filename": report.filename,
        "company": report.company,
        "year": report.year,
        "job_id": job.id if job else None,
        "status": job.status if job else "no_job",
        "indexed_count": job.indexed_count if job else 0,
        "error_message": job.error_message if job else None,
        "started_at": job.started_at.isoformat() if job and job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job and job.finished_at else None,
    }
