"""POST /files/upload — 프론트엔드 호환용 더미 업로드 라우터."""
from fastapi import APIRouter, UploadFile, File

router = APIRouter()

@router.post("/files/upload")
async def upload_file(file: UploadFile = File(...)):
    """
    프론트엔드에서 파일 업로드 모달을 사용할 때 에러가 나지 않도록 방어하는 엔드포인트입니다.
    새로운 RAG 백엔드는 /reports/ingest 를 통해 미리 정제된 JSON을 인덱싱하므로,
    여기서는 파일 수신 처리만 하고 무시합니다.
    """
    return {
        "filename": file.filename,
        "message": f"Successfully uploaded {file.filename} (Ignored by advanced backend)"
    }
