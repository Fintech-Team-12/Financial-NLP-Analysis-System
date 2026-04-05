import pandas as pd
import io
import re
import glob
import json
import os
from bs4 import BeautifulSoup
from pathlib import Path

# ==========================================
# 1. 헬퍼 함수 (기존 파이프라인용) - 고정
# ==========================================


# 회사명 자동 추출 함수
def extract_company_name_from_html(soup):
    full_text = soup.get_text(separator=' ', strip=True)
    # 공백 및 특수 공백 정제
    full_text = full_text.replace('\xa0', ' ').replace('\u2002', ' ').replace('\u2003', ' ')
    head_text = full_text[:2000]  # 탐색 범위를 조금 더 확장

    corp_full = r'(?:주\s*식|유\s*한|유\s*한\s*책\s*임|합\s*자|합\s*명)\s*회\s*사'
    corp_short = r'(?:주|유|합자|합명)'
    
    # 1. "회사명 : XXX" 패턴
    match = re.search(r'회\s*사\s*명\s*[:：]\s*([가-힣a-zA-Z0-9\s\(주\)]+?)(?=\s|\[|\()', head_text)
    if match:
        name = match.group(1).replace(" ", "")
        name = re.sub(r'\([주유합명자]+\)', '', name) 
        name = re.sub(r'주식회사|유한책임회사|유한회사|합자회사|합명회사', '', name)
        if name:
            return name

    # 2. "XXX 주식회사" 또는 "주식회사 XXX" 패턴 (공백 허용)
    # 삼성전자 주식회사 등
    match = re.search(rf'([가-힣a-zA-Z0-9\s]+?)\s*{corp_full}', head_text)
    if match:
        name = match.group(1).strip().replace(" ", "")
        if len(name) >= 2:
            return name
        
    match = re.search(rf'{corp_full}\s*([가-힣a-zA-Z0-9\s]+?)', head_text)
    if match:
        name = match.group(1).strip().replace(" ", "")
        if len(name) >= 2:
            return name
        
    # 3. (주)XXX 또는 XXX(주) 패턴
    match = re.search(rf'([가-힣a-zA-Z0-9\s]+?)\s*\(\s*{corp_short}\s*\)', head_text)
    if match:
        name = match.group(1).strip().replace(" ", "")
        if len(name) >= 2:
            return name
        
    match = re.search(rf'\(\s*{corp_short}\s*\)\s*([가-힣a-zA-Z0-9\s]+?)', head_text)
    if match:
        name = match.group(1).strip().replace(" ", "")
        if len(name) >= 2:
            return name

    # 4. "제 XX 기" 주변에서 찾기 (DART 표준 표지 하단 패턴)
    match = re.search(r'제\s*\d+\s*기\s*.*?([가-힣a-zA-Z0-9]+)\s*(?:주식회사|\(주\))', head_text, re.DOTALL)
    if match:
        return match.group(1).replace(" ", "")

    return "UnknownCompany"


def clean_text(text):
    if not text:
        return ""
    text = str(text).replace("\n", " ").replace("\r", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def clean_account(name):
    if pd.isna(name):
        return name
    name = str(name).replace(" ", "")
    name = re.sub(r"^[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+.", "", name)
    name = re.sub(r"^[0-9]+.", "", name)
    return name


def clean_amount(val):
    if pd.isna(val):
        return 0
    val_str = str(val).strip()
    if val_str == "-" or val_str == "":
        return 0
    val_str = val_str.replace(",", "")
    if val_str.startswith("(") and val_str.endswith(")"):
        val_str = "-" + val_str[1:-1]
    try:
        return int(float(val_str))
    except ValueError:
        return val_str


def clean_note(val):
    if pd.isna(val) or str(val).lower() == "nan":
        return []
    val_str = str(val).strip()
    numbers = re.findall(r"\d+", val_str)
    return numbers


def adjust_unit(row, col_name):
    val = row[col_name]
    account_name = str(row["과목명"])
    if isinstance(val, (int, float)):
        if "주당" in account_name or "원" in account_name:
            return val
        else:
            return int(val * 1000000)
    return val


def html_table_to_dict(table_tag, columns):
    rows = table_tag.find_all('tr')
    if not rows:
        return []
    table_data = []
    for row in rows:
        cells = row.find_all(['td', 'th'])
        row_data = [clean_text(cell.get_text(separator=" ", strip=True)) for cell in cells]
        if any(row_data):
            table_data.append(row_data)
    if not table_data:
        return []
    df = pd.DataFrame(table_data)
    
    # 👇 중첩된 내부 함수 (여기에 정규식이 제대로 들어가야 합니다!)
    def clean_cell(val):
        if pd.isna(val):
            return ""
        text = str(val).strip()
        text = re.sub(r'\s+', ' ', text)
        if text == '-':
            return '0'
        
        # 💥 내용연수 특수 기호(띄어쓰기, 쉼표, 하이픈) 모두 '~'로 완벽 복구
        text = re.sub(r'(?<!\d)(\d{1,2})[\s,~-]+(\d{1,2})\s*년', r'\1~\2년', text)
        
        return text

    df_cleaned = df.map(clean_cell) if hasattr(df, 'map') else df.applymap(clean_cell)
    raw_data_rows = df_cleaned.values.tolist()
    optimized_rows = []
    
    for r_idx, row in enumerate(raw_data_rows):
        new_row = []
        for c_idx, cell in enumerate(row):
            if not cell:
                new_row.append("")
                continue
            if c_idx > 0 and cell == row[c_idx - 1]:
                new_row.append("")
            elif r_idx > 0 and c_idx < 2 and cell == raw_data_rows[r_idx - 1][c_idx]:
                new_row.append("")
            else:
                new_row.append(cell)
        optimized_rows.append(new_row)

    return {
        "unit": "",
        "columns": columns,
        "rows": optimized_rows,
        "annotations": []
    }
    
    
def deep_clean_normalize(tbl):
    unit_text = str(tbl.get("unit", "")).replace(" ", "")
    if not any(u in unit_text for u in ["백만원", "천원", "천주"]):
        return tbl

    # 1. 컬럼명 처리 및 '재할당'
    cols = tbl.get("columns", [])
    new_cols = []
    for col in cols:
        col_name = str(col).replace(" ", "")
        if any(kw in col_name for kw in ["주식수", "수량"]) \
           and "(주)" not in col_name and "주당" not in col_name:
            new_cols.append(str(col) + "(주)")
        else:
            new_cols.append(col)
    
    # 💥 핵심: tbl의 컬럼 정보를 업데이트해야 함
    tbl["columns"] = new_cols
    cols = new_cols # 아래 데이터 루프에서 바뀐 이름을 참조하도록 업데이트
    
    new_rows = []
    skip_keywords = ["(%)", "율", "비율", "비중", "(원)", "단위:원"]

    for row in tbl.get("rows", []):
        if not row: 
            continue
        row_name = str(row[0]).replace(" ", "")
        new_row = [row[0]] 
        
        is_already_final_unit = any(kw in row_name for kw in skip_keywords)
        is_share_row = any(kw in row_name for kw in ["주식수", "수량"])
        
        # 행 이름에 (주) 부착
        if is_share_row and "(주)" not in row_name and "주당" not in row_name:
            new_row[0] = str(row[0]) + "(주)"

        for idx, cell in enumerate(row[1:], start=1):
            if isinstance(cell, (int, float)) and not is_already_final_unit:
                # 바뀐 컬럼명에서 주식수 여부 판단
                col_name = str(cols[idx]).replace(" ", "") if idx < len(cols) else ""
                is_share_col = any(kw in col_name for kw in ["주식수", "수량"])
                
                # A. 주식수 변환 (행 이름이나 컬럼명 중 하나라도 주식수 맥락이면)
                if "천주" in unit_text and (is_share_row or is_share_col):
                    new_row.append(int(cell * 1000))
                
                # B. 금액 변환
                elif "백만원" in unit_text and not (is_share_row or is_share_col):
                    new_row.append(int(cell * 1000000))
                
                else:
                    new_row.append(cell)
            else:
                new_row.append(cell)
        new_rows.append(new_row)

    # 2. 단위 라벨 업데이트
    updated_unit = unit_text.replace("백만원", "원").replace("천주", "주").replace("천원", "원")
    if "주" in updated_unit and "원" in updated_unit:
        tbl["unit"] = "(단위: 주, 원)"
    elif "주" in updated_unit:
        tbl["unit"] = "(단위: 주)"
    else:
        tbl["unit"] = "(단위: 원)"

    tbl["rows"] = new_rows
    return tbl
# ==========================================
# 주석 전용 헬퍼 함수 - 고정 (잘못 덮어씌워진 부분 복구)
# ==========================================
def html_table_to_dict_notes(table_tag):
    marker_pattern = r'(\(\s*\*+\s*\d+\s*\)|\(\s*\*+.*?\).?|\*+\s*\d+|\(주\s*\d*\)|주\s*\d+\s*[)\.]?|주\s*:)'
    annotations = []
    captured_texts = []

    for td in table_tag.find_all(['td', 'th']):
        td_text = td.get_text(separator=" ", strip=True)
        if re.search(marker_pattern, td_text):
            matches = list(re.finditer(marker_pattern, td_text))
            for idx, match in enumerate(matches):
                marker = match.group(1)
                start_idx = match.end()
                end_idx = matches[idx+1].start() if idx + 1 < len(matches) else len(td_text)
                text_part = re.sub(r'계\s*속\s*[:;]*', '', td_text[start_idx:end_idx]).strip()
                if text_part:
                    annotations.append({"type": "footnote", "marker": marker.strip(), "text": text_part})
            
            for content in td.contents:
                if isinstance(content, str):
                    new_str = re.sub(marker_pattern, '', content).strip()
                    content.replace_with(new_str)
                elif content.name == 'br':
                    pass

    try:
        html_str = str(table_tag)
        dfs = pd.read_html(io.StringIO(html_str))
        if not dfs:
            return None
        df = dfs[0]
    except Exception:
        return None

    columns = ["_".join([str(c) for c in col if 'Unnamed' not in str(c)]).strip() for col in df.columns] if isinstance(df.columns, pd.MultiIndex) else [str(c) for c in df.columns]
    
    # 👇 중첩된 내부 함수 (여기에 정규식이 제대로 들어가야 합니다!)
    def clean_cell_notes(val):
        if pd.isna(val):
            return ""
        text = str(val).strip().replace('\xa0', ' ').replace('\u2002', ' ').replace('\u2003', ' ')
        text = re.sub(r'\s+', ' ', text)
        if text == '-':
            return '0'
        
        # 💥 내용연수 특수 기호(띄어쓰기, 쉼표, 하이픈) 모두 '~'로 완벽 복구
        text = re.sub(r'(?<!\d)(\d{1,2})[\s,~-]+(\d{1,2})\s*년', r'\1~\2년', text)
        
        text = re.sub(r'\(\s*-?(\d+(?:,\d{3})*(?:\.\d+)?)\s*(%?)\s*\)', r'-\1\2', text)
        return re.sub(r'(?<!\d)-?\d+(?:,\d{3})*(?:\.\d+)?(?!\d)', lambda m: m.group(0).replace(',', ''), text)

    df_cleaned = df.map(clean_cell_notes) if hasattr(df, 'map') else df.applymap(clean_cell_notes)
    data_rows = df_cleaned.values.tolist()
    processed_rows = []
    
    for row in data_rows:
        new_row = []
        for cell in row:
            try:
                val = clean_amount(cell)
                new_row.append(val)
            except Exception:
                new_row.append(cell)
        processed_rows.append(new_row)

    curr_node = table_tag.next_sibling
    search_limit = 10
    
    while curr_node and search_limit > 0:
        if getattr(curr_node, 'name', None) == 'table':
            break
        node_text = curr_node.get_text(separator=" ", strip=True) if hasattr(curr_node, 'get_text') else str(curr_node).strip()
        if not node_text:
            curr_node = curr_node.next_sibling
            search_limit -= 1
            continue
            
        if re.search(marker_pattern, node_text):
            captured_texts.append(node_text)
            matches = list(re.finditer(marker_pattern, node_text))
            for idx, match in enumerate(matches):
                marker = match.group(1)
                start_idx = match.end()
                end_idx = matches[idx+1].start() if idx + 1 < len(matches) else len(node_text)
                text_part = re.sub(r'계\s*속\s*[:;]*', '', node_text[start_idx:end_idx]).strip()
                if text_part:
                    annotations.append({"type": "footnote", "marker": marker.strip(), "text": text_part})
            search_limit = 10 
        else:
            search_limit -= 1
        curr_node = curr_node.next_sibling

    return {"columns": columns, "rows": processed_rows, "annotations": annotations, "captured_texts": captured_texts}


def clean_tree(node):
    if isinstance(node, dict):
        # --- [기존 테이블 병합/단위 처리 로직 시작] ---
        if "tables" in node and node["tables"]:
            merged_tables = []
            current_unit = ""
            for tbl in node["tables"]:
                if not tbl: 
                    continue
                is_unit = "단위" in str(tbl.get("columns", "")) or (
                    len(tbl.get("rows", [])) == 1 and "단위" in str(tbl["rows"])
                )
                if is_unit:
                    raw_unit = str(tbl["rows"][0][0]) if tbl.get("rows") else ""
                    clean_u = re.sub(r'^[\-\s]+', '', raw_unit)
                    clean_u = re.sub(r'(주)\s+(백만원|원|천원)', r'\1, \2', clean_u)
                    clean_u = re.sub(r'(백만원|원|천원)\s+(주)', r'\1, \2', clean_u)
                    current_unit = clean_u
                    continue
                
                # 원본 방식대로 테이블 생성
                temp_tbl = {
                    "unit": current_unit,
                    "columns": tbl.get("columns", []),
                    "rows": tbl.get("rows", []),
                    "annotations": tbl.get("annotations", []),
                }
                # 💥 여기서만 100만 배 정규화 호출!
                merged_tables.append(deep_clean_normalize(temp_tbl))
                current_unit = ""
            node["tables"] = merged_tables
        # --- [기존 테이블 병합/단위 처리 로직 끝] ---

        # 🟢 원본의 안전한 재귀 구조 유지 (content, title 유실 방지)
        for k, v in list(node.items()):
            if k in ["sub_sections", "tables"] and not v:
                del node[k]
            else:
                node[k] = clean_tree(v)
                
    elif isinstance(node, str):
        return re.sub(r" {2,}", " ", node).strip()
    return node


# ==========================================
# 2. 개별 파싱 모듈 함수
# ==========================================


#  [수정] 파라미터에 company_name 추가 및 동적 복구 로직 적용
def parse_intro(soup, company_name="UnknownCompany"):
    pure_text = soup.get_text(separator="\n", strip=True)

    # DART 특유의 늘여쓰기(자간 벌림) 강제 복구 로직
    keywords = [
        "재무제표",
        "감사보고서",
        "손익계산서",
        "자본변동표",
        "현금흐름표",
        "포괄손익계산서",
        "연결",
    ]

    # 추출된 회사명이 있으면 키워드에 추가
    if company_name != "UnknownCompany":
        keywords.append(company_name)

    for kw in keywords:
        pattern = r"\s*".join(list(kw))
        pure_text = re.sub(pattern, kw, pure_text)

    end_pattern = r"\(\s*첨부\s*\)\s*재\s*무\s*제\s*표|\[\s*첨부\s*\]\s*재\s*무\s*제\s*표|재\s*무\s*상\s*태\s*표\s*제\s*\d+\s*기|연\s*결\s*재\s*무\s*상\s*태\s*표"
    split_by_end = re.split(end_pattern, pure_text)
    audit_report_only = split_by_end[0]

    headers = [
        r"재무제표에 대한 경영진과 지배기구의 책임",
        r"재무제표에 대한 경영진 등의 책임",
        r"재무제표에 대한 경영진의 책임",
        r"재무제표감사에 대한 감사인의 책임",
        r"재무제표에 대한 감사인의 책임",
        r"감사인의 책임",
        r"감사의견근거",
        r"감사의견 근거",
        r"감사의견",
        r"기타사항",
        r"강조사항",
        r"핵심감사사항",
        r"계속기업 관련 중요한 불확실성",
    ]

    headers_pattern = (
        r"(?:\n|^|(?<=\.)\s+)(?:[0-9ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+\.\s*)?("
        + "|".join(headers)
        + r")(?=\n|\s|$)"
    )
    parts = re.split(headers_pattern, audit_report_only)

    report_data = {
        "title": "감사보고서 본문",
        "content": "독립된 회계감사인의 감사보고서 본문입니다.",
        "tables": [],
        "sub_sections": {},
    }

    intro_text = parts[0].strip()
    intro_text = re.sub(r"\s+", " ", intro_text)
    if intro_text:
        report_data["sub_sections"]["도입부"] = {
            "title": "도입부",
            "content": intro_text,
            "tables": [],
            "sub_sections": {},
        }

    current_main_section = None
    for i in range(1, len(parts) - 1, 2):
        section_title = parts[i].strip()
        section_title = re.sub(r"\s+", " ", section_title)
        section_content = parts[i + 1].strip()
        section_content = re.sub(r"\s+", " ", section_content)

        if section_title not in report_data["sub_sections"]:
            report_data["sub_sections"][section_title] = {
                "title": section_title,
                "content": section_content,
                "tables": [],
                "sub_sections": {},
            }
            current_main_section = section_title
        else:
            if current_main_section:
                report_data["sub_sections"][current_main_section]["content"] += (
                    " " + section_title + " " + section_content
                )

    return {"감사보고서": report_data}


def extract_financial_statement(tables, title, keywords, exclude_keywords=None):
    if exclude_keywords is None:
        exclude_keywords = []

    for df in tables:
        df_string = df.to_string().replace(" ", "")

        if all(kw in df_string for kw in keywords) and not any(
            ex_kw in df_string for ex_kw in exclude_keywords
        ):
            target_df = df.copy()
            if isinstance(target_df.columns, pd.MultiIndex):
                target_df.columns = [str(col) for col in target_df.columns]
            else:
                target_df.columns = [str(c) for c in target_df.columns]

            cols = list(target_df.columns)
            account_col = cols[0]
            note_col = next(
                (
                    c
                    for c in cols
                    if "주석" in c.replace(" ", "") or "비고" in c.replace(" ", "")
                ),
                None,
            )
            val_cols = [c for c in cols if c != account_col and c != note_col]

            if len(val_cols) >= 2:
                if len(val_cols) >= 4:
                    target_df["당기금액"] = target_df[val_cols[0]].fillna(
                        target_df[val_cols[1]]
                    )
                    target_df["전기금액"] = target_df[val_cols[2]].fillna(
                        target_df[val_cols[3]]
                    )
                else:
                    target_df["당기금액"] = target_df[val_cols[0]]
                    target_df["전기금액"] = target_df[val_cols[1]]

                target_df = target_df.dropna(subset=["당기금액", "전기금액"], how="all")
                target_df["과목명"] = target_df[account_col].apply(clean_account)
                target_df["당기금액"] = target_df["당기금액"].apply(clean_amount)
                target_df["전기금액"] = target_df["전기금액"].apply(clean_amount)
                target_df["관련주석"] = (
                    target_df[note_col].apply(clean_note)
                    if note_col
                    else [[] for _ in range(len(target_df))]
                )

                final_df = target_df[
                    ["과목명", "관련주석", "당기금액", "전기금액"]
                ].dropna(subset=["과목명"])
                final_df["당기금액"] = final_df.apply(
                    lambda row: adjust_unit(row, "당기금액"), axis=1
                )
                final_df["전기금액"] = final_df.apply(
                    lambda row: adjust_unit(row, "전기금액"), axis=1
                )
                final_df = final_df.where(pd.notnull(final_df), None)

                return {
                    title: {
                        "title": title,
                        "content": f"회사의 {title}입니다.",
                        "tables": [
                            {
                                "unit": "(단위: 원)",
                                "columns": [
                                    "과목명",
                                    "관련주석",
                                    "당기금액",
                                    "전기금액",
                                ],
                                "rows": final_df.values.tolist(),
                                "annotations": [],
                            }
                        ],
                        "sub_sections": {},
                    }
                }
    return {}


def extract_equity_statement(tables, title="자본변동표"):
    def clean_event(name):
        if pd.isna(name):
            return name
        return str(name).strip().replace("\n", "")

    target_df = None
    for df in tables:
        df_string = df.to_string().replace(" ", "")

        if (
            "자본금" in df_string
            and "이익잉여금" in df_string
            and (
                "기말" in df_string
                or "기초" in df_string
                or "당기순" in df_string
                or "배당" in df_string
            )
            and "유동자산" not in df_string
            and "매출액" not in df_string
        ):
            target_df = df.copy()
            break

    if target_df is not None:
        if isinstance(target_df.columns, pd.MultiIndex):
            new_cols = []
            for col in target_df.columns:
                valid_names = [
                    str(c).replace(" ", "")
                    for c in col
                    if "Unnamed" not in str(c) and str(c) != "nan"
                ]
                if valid_names:
                    new_cols.append(valid_names[-1])
                else:
                    new_cols.append("항목")
            target_df.columns = new_cols
        else:
            target_df.columns = [str(c).replace(" ", "") for c in target_df.columns]

        note_col = None
        for c in target_df.columns:
            if "주석" in str(c).replace(" ", "") or "비고" in str(c).replace(" ", ""):
                note_col = c
                break

        target_df = target_df.rename(columns={target_df.columns[0]: "구분"})
        target_df = target_df.dropna(how="all")
        target_df["구분"] = target_df["구분"].apply(clean_event)
        target_df = target_df.dropna(subset=["구분"])

        if note_col:
            target_df["관련주석"] = target_df[note_col].apply(clean_note)
        else:
            target_df["관련주석"] = [[] for _ in range(len(target_df))]

        val_cols = [
            c for c in target_df.columns if c not in ["구분", note_col, "관련주석"]
        ]

        for col in val_cols:
            target_df[col] = target_df[col].apply(clean_amount)

        processed_records = []
        current_parent = "기초 및 기말 잔액"

        for _, row in target_df.iterrows():
            event_name = row["구분"]

            total_sum = sum(
                abs(row[c]) for c in val_cols if isinstance(row[c], (int, float))
            )

            if total_sum == 0:
                current_parent = event_name
            else:
                balance_keywords = [
                    "기초",
                    "기말",
                    "잔액",
                    "1월1일",
                    "12월31일",
                    "1.1",
                    "12.31",
                ]
                is_balance = any(
                    k in event_name.replace(" ", "") for k in balance_keywords
                )

                if is_balance:
                    parent_name = "기초 및 기말 잔액"
                    current_parent = "기타 변동"
                else:
                    parent_name = current_parent

                record = {
                    "상위구분": parent_name,
                    "구분": event_name,
                    "관련주석": row["관련주석"],
                }

                for c in val_cols:
                    val = row[c]
                    if pd.isna(val):
                        record[c] = 0
                    elif isinstance(val, (int, float)):
                        record[c] = int(val * 1000000)
                    else:
                        record[c] = val

                processed_records.append(record)

        final_columns = ["상위구분", "구분", "관련주석"] + val_cols

        table_rows = []
        for record in processed_records:
            row_data = [record.get(col, None) for col in final_columns]
            table_rows.append(row_data)

        return {
            title: {
                "title": title,
                "content": f"회사의 {title}입니다.",
                "tables": [
                    {
                        "unit": "(단위: 원)",
                        "columns": final_columns,
                        "rows": table_rows,
                        "annotations": [],
                    }
                ],
                "sub_sections": {},
            }
        }
    return {}


def parse_appendix(soup):
    appendix_data = {
        "title": "감사보고서 부록",
        "content": "내부회계관리제도 관련 보고서 및 외부감사 실시내용입니다.",
        "tables": [],
        "sub_sections": {},
    }

    current_section = None
    content_buffer = []
    tables_buffer = []

    for tag in soup.find_all(["p", "div", "table", "h1", "h2", "h3", "h4", "span"]):
        if tag.name != "table" and tag.find_parent("table"):
            continue

        text = tag.get_text(strip=True)
        text_clean = re.sub(r"\s+", " ", text).strip()
        if not text_clean:
            continue

        matched_section = None
        # 🚀 [업그레이드 1] 문장 중간에 언급되는 가짜 제목을 무시하고, 맨 앞(30자 이내)에 등장할 때만 진짜 제목으로 판정
        if re.search(r"^.{0,30}내부회계관리제도\s*(검토|감사)보고서", text_clean):
            matched_section = "감사인의 내부회계관리제도 보고서"
        elif re.search(r"^.{0,30}내부회계관리제도\s*운영실태\s*(평가)?보고서", text_clean) and not re.search(r"검토|감사", text_clean[:30]):
            matched_section = "경영진의 내부회계관리제도 운영실태보고서"
        elif re.search(r"^.{0,30}외부감사\s*실시내용", text_clean):
            matched_section = "외부감사 실시내용"

        # 새로운 섹션을 발견하면 기존 데이터를 '누적 저장' (덮어쓰기 증발 원천 차단)
        if matched_section and matched_section != current_section:
            if current_section:
                if current_section not in appendix_data["sub_sections"]:
                    appendix_data["sub_sections"][current_section] = {
                        "title": current_section,
                        "content": "",
                        "tables": [],
                        "sub_sections": {},
                    }
                if content_buffer:
                    appendix_data["sub_sections"][current_section]["content"] += "\n" + "\n".join(content_buffer)
                if tables_buffer:
                    appendix_data["sub_sections"][current_section]["tables"].extend(tables_buffer)
            
            current_section = matched_section
            content_buffer, tables_buffer = [], []
            
            if len(text_clean) < 50:
                continue

        # 본문 및 표 데이터 수집
        if current_section:
            if tag.name == "table":
                columns = (
                    [str(i) for i in range(len(tag.find("tr").find_all(["td", "th"])))]
                    if tag.find("tr")
                    else ["0"]
                )
                res = html_table_to_dict(tag, columns)
                if res and res["rows"]:
                    tables_buffer.append(res)
            else:
                if text_clean not in content_buffer:
                    content_buffer.append(text_clean)

    # 🚀 [업그레이드 2] 마지막으로 켜져 있던 섹션도 안전하게 '누적 저장'
    if current_section:
        if current_section not in appendix_data["sub_sections"]:
            appendix_data["sub_sections"][current_section] = {
                "title": current_section,
                "content": "",
                "tables": [],
                "sub_sections": {},
            }
        if content_buffer:
            appendix_data["sub_sections"][current_section]["content"] += "\n" + "\n".join(content_buffer)
        if tables_buffer:
            appendix_data["sub_sections"][current_section]["tables"].extend(tables_buffer)

    # 🧹 목차만 읽고 지나간 껍데기 섹션들을 깔끔하게 청소
    final_sub_sections = {}
    for k, v in appendix_data["sub_sections"].items():
        v["content"] = v["content"].strip()
        if v["content"] or v["tables"]:
            final_sub_sections[k] = v
    appendix_data["sub_sections"] = final_sub_sections

    return {"부록": appendix_data}

def parse_complex_notes(html_content):
    soup = BeautifulSoup(re.sub(r"\r?\n", "", html_content), "html.parser")
    for tag in soup.find_all(["span", "font", "b", "strong", "i", "em", "u"]):
        tag.unwrap()
    soup.smooth()

    stop_node = soup.find(id="toc_5")
    if stop_node:
        for sibling in stop_node.find_all_next():
            sibling.decompose()
        stop_node.decompose()

    table_store = {}
    all_captured_footnotes = set()
    for idx, table in enumerate(soup.find_all("table")):
        if table.find("table"):
            continue
        res = html_table_to_dict_notes(table)
        if res:
            tid = f"[[TABLE_{idx}]]"
            if "captured_texts" in res:
                all_captured_footnotes.update(res["captured_texts"])
            table_store[tid] = res
            table.replace_with(f"\n{tid}\n")

    pure_text = (
        soup.get_text(separator="\n", strip=True)
        .replace("\xa0", " ")
        .replace("\u2002", " ")
        .replace("\u2003", " ")
    )
    pure_text = re.sub(r"(\d)\s+(?=\d)", r"\1", pure_text)
    pure_text = re.sub(
        r"(\.)\s*(\d{1,2})\s*\.\s*([^:\n]+?)\s*:\s*", r"\1\n\2. \3\n", pure_text
    )

    lines = [line.strip() for line in pure_text.split("\n") if line.strip()]
    final_data = {}
    curr_L1 = curr_L2 = curr_L3 = curr_L4 = curr_L5 = None
    started = False
    kor_ord = {chr(i): i for i in range(ord("가"), ord("하") + 1)}
    curr_L3_char = ""
    kill_pattern = r"[,.]?\s*\d*[.\s]*계\s*속\s*[:;]*\s*$"

    for line in lines:
        line = line.strip()
        check_line = re.sub(kill_pattern, "", line).strip()
        if not started:
            if re.match(r"^1\.\s*(일반적\s*사항|회사의\s*개요)", check_line):
                started = True
            else:
                continue

        m1 = re.match(r"^(\d+)\s*\.\s*(.*)", check_line)
        if m1 and m1.group(1).isdigit():
            num = m1.group(1)
            if 1 <= int(num) <= 60 and num not in final_data:
                final_data[num] = {
                    "title": m1.group(2).strip(),
                    "content": "",
                    "tables": [],
                    "sub_sections": {},
                }
                curr_L1, curr_L2, curr_L3, curr_L4 = final_data[num], None, None, None
                curr_L3_char = ""
                continue
        m2 = re.match(r"^(\d+\.\d+)\.?\s+(.*)", check_line)
        if m2 and curr_L1:
            key = m2.group(1)
            curr_L1["sub_sections"][key] = {
                "title": m2.group(2).strip(),
                "content": "",
                "tables": [],
                "sub_sections": {},
            }
            curr_L2, curr_L3, curr_L4 = curr_L1["sub_sections"][key], None, None
            curr_L3_char = ""
            continue
        m3 = re.match(r"^([가-하])\s*\.\s+(.*)", check_line)
        if m3:
            new_char = m3.group(1)
            is_restart = (
                (kor_ord.get(new_char, 0) <= kor_ord.get(curr_L3_char, 0))
                if curr_L3_char
                else False
            )
            if not is_restart:
                parent = curr_L2 or curr_L1
                if parent:
                    key = new_char + "."
                    orig_key = key
                    counter = 1
                    while key in parent["sub_sections"]:
                        key = f"{orig_key}_{counter}"
                        counter += 1
                    parent["sub_sections"][key] = {
                        "title": m3.group(2).strip(),
                        "content": "",
                        "tables": [],
                        "sub_sections": {},
                    }
                    curr_L3, curr_L4, curr_L3_char = (
                        parent["sub_sections"][key],
                        None,
                        new_char,
                    )
                    continue
        m4 = re.match(r"^(\(\d+\))\s+(.*)", check_line)
        if m4:
            parent = curr_L3 or curr_L2 or curr_L1
            if parent:
                key = m4.group(1).strip()
                orig_key = key
                counter = 1
                while key in parent["sub_sections"]:
                    key = f"{orig_key}_{counter}"
                    counter += 1
                parent["sub_sections"][key] = {
                    "title": m4.group(2).strip(),
                    "content": "",
                    "tables": [],
                    "sub_sections": {},
                }
                curr_L4 = parent["sub_sections"][key]
                continue
        m5 = re.match(r"^(\d+)\)\s+(.*)", check_line)
        if m5:
            parent = curr_L4 or curr_L3 or curr_L2 or curr_L1
            if parent:
                key = m5.group(1) + ")"
                orig_key = key
                counter = 1
                while key in parent["sub_sections"]:
                    key = f"{orig_key}_{counter}"
                    counter += 1
                parent["sub_sections"][key] = {
                    "title": m5.group(2).strip(),
                    "content": "",
                    "tables": [],
                    "sub_sections": {},
                }
                curr_L5 = parent["sub_sections"][key]
                continue


        active_node = curr_L5 or curr_L4 or curr_L3 or curr_L2 or curr_L1
        if active_node:
            if line in all_captured_footnotes:
                continue
            if re.match(r"^계\s*속\s*[:;]*$", line) or re.search(kill_pattern, line):
                continue

            if "[[TABLE_" in line:
                for part in re.split(r"(\[\[TABLE_\d+\]\])", line):
                    if part in table_store:
                        active_node["tables"].append(table_store[part])
                    elif part.strip() and part not in all_captured_footnotes:
                        clean_part = re.sub(kill_pattern, "", part).strip()
                        if clean_part and clean_part != active_node.get("title", ""):
                            active_node["content"] += " " + clean_part
            else:
                if check_line and check_line != active_node.get("title", ""):
                    active_node["content"] += " " + check_line

    return {"주석": clean_tree(final_data)}


# ==========================================
# 3. 단일 파일 파싱 함수 (API 업로드용)
# ==========================================
def parse_single_file(file_path: str, processed_dir: str) -> dict:
    """
    단일 HTML 파일을 파싱하여 structured JSON으로 변환 후 저장.

    Args:
        file_path: HTML 파일 경로
        processed_dir: JSON 저장 디렉토리

    Returns:
        dict: {
            "year": str,
            "company_name": str,
            "save_path": str,
            "year_data": dict (파싱된 전체 데이터)
        }
    """
    os.makedirs(processed_dir, exist_ok=True)

    year_match = re.search(r"20\d{2}", os.path.basename(file_path))
    year = year_match.group() if year_match else "Unknown"

    try:
        with open(file_path, "r", encoding="cp949") as f:
            html_content = f.read()
    except UnicodeDecodeError:
        with open(file_path, "r", encoding="utf-8") as f:
            html_content = f.read()

    soup = BeautifulSoup(html_content, "lxml")
    try:
        tables = pd.read_html(io.StringIO(html_content), encoding="cp949")
    except ValueError:
        tables = []

    company_name = extract_company_name_from_html(soup)
    print(
        f"[{year}년] {os.path.basename(file_path)} 처리 중... (자동인식 회사명: {company_name})"
    )

    year_data = {year: {"company": company_name}}

    year_data[year].update(parse_intro(soup, company_name=company_name))

    year_data[year].update(
        extract_financial_statement(
            tables,
            "재무상태표",
            ["유동자산", "유동부채", "이익잉여금"],
            exclude_keywords=["자본변동표", "손익계산서"],
        )
    )
    year_data[year].update(
        extract_financial_statement(
            tables,
            "손익계산서",
            ["매출액", "영업이익", "당기순이익"],
            exclude_keywords=["총포괄손익", "포괄손익계산서", "자본변동표"],
        )
    )
    year_data[year].update(
        extract_financial_statement(
            tables,
            "포괄손익계산서",
            ["기타포괄", "총포괄"],
            exclude_keywords=["매출액", "자본금", "자본변동표"],
        )
    )
    year_data[year].update(extract_equity_statement(tables, "자본변동표"))
    year_data[year].update(
        extract_financial_statement(
            tables,
            "현금흐름표",
            ["영업활동현금흐름", "투자활동현금흐름"],
            exclude_keywords=[],
        )
    )
    year_data[year].update(parse_appendix(soup))
    year_data[year].update(parse_complex_notes(html_content))

    save_path = os.path.join(
        processed_dir, f"{company_name}_audit_report_{year}_structured.json"
    )
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(year_data, f, ensure_ascii=False, indent=4)

    print(f"  -> 완료! {save_path} 생성됨.")

    return {
        "year": year,
        "company_name": company_name,
        "save_path": save_path,
        "year_data": year_data,
    }


# ==========================================
# 3-1. 배치 파이프라인 함수 (기존 호환)
# ==========================================
def run_pipeline(raw_dir: str, processed_dir: str):
    file_list = glob.glob(os.path.join(raw_dir, "*.htm*"))
    file_list.sort()

    if not file_list:
        print(f"[{raw_dir}] 경로에 HTML 파일이 없습니다.")
        return

    print(
        f"총 {len(file_list)}개의 파일을 찾았습니다. 파싱을 시작합니다...\n" + "-" * 50
    )

    for file_path in file_list:
        parse_single_file(file_path, processed_dir)

    print("-" * 50 + "\n🎉 전체 파이프라인 처리가 완료되었습니다!")


# ==========================================
# 4. 진입점 (기존 뼈대 구조 유지) - 고정
# ==========================================
def main() -> None:
    BASE_DIR = Path(__file__).resolve().parents[3]

    raw_dir = BASE_DIR / "data" / "raw"
    processed_dir = BASE_DIR / "data" / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)

    print(f"raw_dir={raw_dir}")
    print(f"processed_dir={processed_dir}")
    print("ingest pipeline 파싱을 시작합니다.")

    run_pipeline(str(raw_dir), str(processed_dir))


if __name__ == "__main__":
    main()

