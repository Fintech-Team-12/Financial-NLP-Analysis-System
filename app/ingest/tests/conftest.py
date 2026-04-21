"""app/ingest/tests 에서 `from app.ingest.src.pipeline` 을 import 할 수 있도록
워크스페이스 루트를 sys.path 에 추가한다.

app/ingest/tests/ 에는 __init__.py 가 없어 pytest 기본 동작으로는 해당 디렉터리가
sys.path 에 prepend 되어 outer `app` 패키지를 찾지 못한다. 이 conftest 가 워크스페이스
루트를 sys.path 최상단으로 올려서 outer app 패키지를 import 할 수 있게 한다.
"""
from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_ROOT_STR = str(_PROJECT_ROOT)

if _ROOT_STR not in sys.path:
    sys.path.insert(0, _ROOT_STR)
