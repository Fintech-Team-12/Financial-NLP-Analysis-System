"""POST /files/upload — 실제 파일 업로드 및 RAG 파이프라인 연동."""
import os
import shutil
import sys
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException

from app.core.config import settings
from app.core.auth_deps import get_current_user
from app.services import indexing

# ── pipeline.py 임포트를 위한 경로 설정 ──────────────────────────────────
# app/ingest/src 디렉토리를 sys.path에 추가하여 pipeline 모듈을 불러옵니다.
INGEST_SRC_DIR = str(Path(settings._project_root) / "app" / "ingest" / "src")
if INGEST_SRC_DIR not in sys.path:
    sys.path.append(INGEST_SRC_DIR)

try:
    import pipeline
except ImportError:
    # 로컬 경로 문제 대응용
    pipeline = None

router = APIRouter()

@router.post("/files/upload")
async def upload_file(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """
    1. HTML 파일을 수신하여 임시 저장합니다.
    2. pipeline.py를 사용하여 structured JSON으로 변환합니다.
    3. indexing 서비스로 해당 연도의 데이터를 인메모리에 로드합니다.
    """
    if not pipeline:
        raise HTTPException(status_code=500, detail="Parsing pipeline module not found.")

    # 1. 확장자 검증
    if not (file.filename.endswith(".htm") or file.filename.endswith(".html")):
        raise HTTPException(status_code=400, detail="Only .htm or .html files are allowed.")

    # 2. 임시 디렉토리 준비
    os.makedirs(settings.upload_temp_dir, exist_ok=True)
    temp_path = os.path.join(settings.upload_temp_dir, file.filename)

    try:
        # 3. 업로드 파일 임시 저장
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # 4. 파이핑 (HTML -> JSON)
        # pipeline.parse_single_file은 JSON을 생성하여 settings.processed_dir에 저장합니다.
        result = pipeline.parse_single_file(temp_path, settings.processed_dir)
        
        year_str = result.get("year", "Unknown")
        if not year_str.isdigit():
            raise HTTPException(status_code=422, detail=f"Could not extract year from file: {year_str}")
        
        year = int(year_str)
        company = result.get("company_name", "Unknown")

        # 5. 인덱싱 (방금 생성된 특정 파일만 타겟으로 인덱싱)
        # force=True를 사용하여 기존에 동일한 파일이 이미 인덱싱되어 있다면 덮어씌웁니다.
        indexed_count = indexing.ingest_single_file(Path(result["save_path"]), force=True)

        return {
            "success": True,
            "filename": file.filename,
            "company": company,
            "year": year,
            "indexed_count": indexed_count,
            "message": f"Successfully processed and indexed {indexed_count} documents."
        }

    except Exception as e:
        # 실제 운영 환경에서는 stacktrace를 로깅해야 합니다.
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")
    
    finally:
        # 6. 임시 파일 삭제
        if os.path.exists(temp_path):
            os.remove(temp_path)
