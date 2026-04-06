import sys
import os
import re
from pathlib import Path

# ── Paths ──
PROCESS_DIR = Path(__file__).resolve().parent
CHROMA_DIR = PROCESS_DIR.parent
ROOT_DIR = CHROMA_DIR.parent

RAW_DIR = ROOT_DIR / "data" / "raw"
PROCESSED_DIR = ROOT_DIR / "data" / "processed"
FLATTENED_DIR = PROCESS_DIR / "flattened_data"
ENRICHED_DIR = PROCESS_DIR / "enriched_data"
SQLITE_DIR = PROCESS_DIR / "sqlite_by_year"

# ── Import Pipeline Modules ──
INGEST_SRC_DIR = ROOT_DIR / "app" / "ingest" / "src"
if str(INGEST_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(INGEST_SRC_DIR))

try:
    import pipeline
except Exception as e:
    print(f"[auto_pipeline] pipeline.py 임포트 실패: {e}")

try:
    if str(PROCESS_DIR) not in sys.path:
        sys.path.insert(0, str(PROCESS_DIR))
    import structured_flatten
    import enrich_flattened_for_rag
    import json_to_sqlite
except Exception as e:
    print(f"[auto_pipeline] 변환 모듈 임포트 실패: {e}")


def run_all(skip_if_exists: bool = True):
    print("🚀 [Auto Pipeline] 오프라인 데이터 엔지니어링 파이프라인 점검 시작...")

    # ---------------------------------------------------------
    # [검사 방식 설명 1] HTM -> Structured JSON
    # RAW_DIR의 원본 htm 파일 이름에서 연도(예: 2014)를 추출한 다음,
    # PROCESSED_DIR 에 "그 연도가 포함된 _structured.json 파일"이 1개라도 있으면 통과합니다.
    # ---------------------------------------------------------
    if not RAW_DIR.exists():
        print(f"⚠️ [Step 1] 원본 데이터 폴더가 없습니다: {RAW_DIR}")
    else:
        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        raw_files = sorted(RAW_DIR.glob("*.htm*"))
        
        for file_path in raw_files:
            match = re.search(r'(20\d{2})', file_path.name)
            year = match.group(1) if match else "unknown"
            
            existing_files = list(PROCESSED_DIR.glob(f"*_{year}_structured.json"))
            if skip_if_exists and existing_files:
                print(f"⏭️  [Step 1] HTM -> JSON 스킵 (연도: {year}). 이미 존재함: {existing_files[0].name}")
                continue
                
            try:
                print(f"🔄 [Step 1] 파싱 중: {file_path.name}")
                pipeline.parse_single_file(str(file_path), str(PROCESSED_DIR))
            except Exception as e:
                print(f"❌ [Step 1] 파싱 실패 ({file_path.name}): {e}")

    # ---------------------------------------------------------
    # [검사 방식 설명 2] Structured -> Flattened JSON
    # PROCESSED_DIR 에 있는 모든 _structured.json 파일 목록을 순회하며,
    # 파일명에서 _structured.json을 _flattened.json으로 바꿔보고, 
    # FLATTENED_DIR에 해당 파일이 정확히 존재하면 통과합니다.
    # ---------------------------------------------------------
    if not PROCESSED_DIR.exists():
        print(f"⚠️ [Step 2] 전처리된 폴더가 없습니다: {PROCESSED_DIR}")
    else:
        FLATTENED_DIR.mkdir(parents=True, exist_ok=True)
        structured_files = sorted(PROCESSED_DIR.glob("*_structured.json"))
        
        for s_file in structured_files:
            expected_out = FLATTENED_DIR / s_file.name.replace("_structured.json", "_flattened.json")
            if skip_if_exists and expected_out.exists():
                print(f"⏭️  [Step 2] Structured -> Flattened 스킵. 이미 존재함: {expected_out.name}")
                continue
                
            try:
                print(f"🔄 [Step 2] Flatten 처리 중: {s_file.name}")
                structured_flatten.process_one_file(s_file, FLATTENED_DIR)
            except Exception as e:
                print(f"❌ [Step 2] 처리 실패 ({s_file.name}): {e}")

    # ---------------------------------------------------------
    # [검사 방식 설명 3] Flattened -> Enriched JSON
    # FLATTENED_DIR의 파일명(_flattened.json)을 _enriched.json으로 바꾼 경로를 생성하고,
    # ENRICHED_DIR에 그 파일이 정확하게 존재하면 통과합니다.
    # ---------------------------------------------------------
    if not FLATTENED_DIR.exists():
        print(f"⚠️ [Step 3] Flattened 폴더가 없습니다: {FLATTENED_DIR}")
    else:
        ENRICHED_DIR.mkdir(parents=True, exist_ok=True)
        flattened_files = sorted(FLATTENED_DIR.glob("*_flattened.json"))
        
        for f_file in flattened_files:
            expected_out = enrich_flattened_for_rag.make_output_path(f_file, ENRICHED_DIR)
            if skip_if_exists and expected_out.exists():
                print(f"⏭️  [Step 3] Flattened -> Enriched 스킵. 이미 존재함: {expected_out.name}")
                continue

            try:
                print(f"🔄 [Step 3] Enrich 처리 중: {f_file.name}")
                enrich_flattened_for_rag.process_one_file(f_file, ENRICHED_DIR)
            except Exception as e:
                print(f"❌ [Step 3] 처리 실패 ({f_file.name}): {e}")

    # ---------------------------------------------------------
    # [검사 방식 설명 4] Enriched -> SQLite DB
    # _enriched.json 파일 이름에서 정규식으로 연도(2014 등)를 뽑아낸 다음,
    # SQLITE_DIR 에 그 연도를 포함하는 아무 DB(*2014*.db)가 1개라도 있으면 통과합니다.
    # ---------------------------------------------------------
    if not ENRICHED_DIR.exists():
        print(f"⚠️ [Step 4] Enriched 폴더가 없습니다: {ENRICHED_DIR}")
    else:
        SQLITE_DIR.mkdir(parents=True, exist_ok=True)
        enriched_files = sorted(ENRICHED_DIR.glob("*_enriched.json"))
        
        for e_file in enriched_files:
            year_match = re.search(r'(20\d{2})', e_file.name)
            year = year_match.group(1) if year_match else "unknown"
            
            existing_dbs = list(SQLITE_DIR.glob(f"*{year}*.db"))
            if skip_if_exists and existing_dbs:
                print(f"⏭️  [Step 4] Enriched -> SQLite 스킵 (연도: {year}). 이미 존재함: {existing_dbs[0].name}")
                continue

            try:
                print(f"🔄 [Step 4] SQLite 생성 중: {e_file.name}")
                json_to_sqlite.process_one_file(e_file)
            except Exception as e:
                print(f"❌ [Step 4] 처리 실패 ({e_file.name}): {e}")

    print("✨ [Auto Pipeline] 오프라인 데이터 파이프라인 점검 완료.")


if __name__ == "__main__":
    run_all(skip_if_exists=True)
