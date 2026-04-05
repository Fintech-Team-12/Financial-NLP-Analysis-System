"""
내부 정규화 문서 스키마.

raw JSON 의 다양한 포맷(재무제표/주석/감사보고서)을 단일 구조로 통일.
retrieval / answering 레이어는 이 타입만 다룬다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class NormalizedDocument:
    # ── 식별자 ────────────────────────────────────────────────────────────────
    doc_id: str          # 예) "재무상태표_2023_매출채권", "주석_2023_5", "감사보고서_2023_감사의견"

    # ── 분류 ──────────────────────────────────────────────────────────────────
    doc_type: str        # "financial_statement" | "note" | "audit_report" | "other"
    year: int
    section: str         # 과목명 or 주석번호 or 섹션명

    # ── 검색/LLM 용 텍스트 ───────────────────────────────────────────────────
    content: str
    company: str = "삼성전자"

    # ── 숫자형 질문용 구조화 데이터 ─────────────────────────────────────────
    # 예) {"당기금액": 27363016000000, "전기금액": 20503223000000}
    numeric_value: Optional[dict[str, int]] = None

    # ── 주석 연결 ─────────────────────────────────────────────────────────────
    # 재무제표 row 의 관련주석 번호 리스트 — 예) ["4", "5", "7", "28"]
    related_notes: list[str] = field(default_factory=list)

    # ── 계층 정보 (현금흐름표/자본변동표 등 상위 구분 보존) ─────────────────
    parent_section: Optional[str] = None
