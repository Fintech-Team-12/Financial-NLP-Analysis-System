import pandas as pd
import io
import re
import os
import glob
import json
from bs4 import BeautifulSoup
from pathlib import Path

# ==========================================
# 1. 헬퍼 함수 (기존 파이프라인용)
# ==========================================
def clean_text(text):
    if not text: return ""
    text = str(text).replace('\n', ' ').replace('\r', ' ')
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def clean_account(name):
    if pd.isna(name): return name
    name = str(name).replace(" ", "")
    name = re.sub(r'^[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+.', '', name)
    name = re.sub(r'^[0-9]+.', '', name)
    return name

def clean_amount(val):
    if pd.isna(val): return 0
    val_str = str(val).strip()
    if val_str == '-' or val_str == '': return 0
    val_str = val_str.replace(',', '')
    if val_str.startswith('(') and val_str.endswith(')'):
        val_str = '-' + val_str[1:-1]
    try:
        return int(float(val_str))
    except ValueError:
        return val_str

def clean_note(val):
    if pd.isna(val) or str(val).lower() == 'nan': 
        return [] 
    val_str = str(val).strip()
    numbers = re.findall(r'\d+', val_str)
    return numbers

def adjust_unit(row, col_name):
    val = row[col_name]
    account_name = str(row['과목명'])
    if isinstance(val, (int, float)):
        if '주당' in account_name or '원' in account_name:
            return val
        else:
            return int(val * 1000000)
    return val

def html_table_to_dict(table_tag, columns):
    rows = table_tag.find_all('tr')
    if not rows: return []
    table_data = []
    for row in rows:
        cells = row.find_all(['td', 'th'])
        row_data = [clean_text(cell.get_text(separator=" ", strip=True)) for cell in cells]
        if any(row_data):
            table_data.append(row_data)
    if not table_data: return []
    df = pd.DataFrame(table_data)
    
    def clean_cell(val):
        if pd.isna(val): return ""
        text = str(val).strip()
        text = re.sub(r'\s+', ' ', text)
        if text == '-': return '0'
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

# ==========================================
# 💥 [추가됨] 은정님의 주석 전용 헬퍼 함수
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
                marker = match.group(1); start_idx = match.end()
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
        if not dfs: return None
        df = dfs[0]
    except: return None

    columns = ["_".join([str(c) for c in col if 'Unnamed' not in str(c)]).strip() for col in df.columns] if isinstance(df.columns, pd.MultiIndex) else [str(c) for c in df.columns]
    
    def clean_cell_notes(val):
        if pd.isna(val): return ""
        text = str(val).strip().replace('\xa0', ' ').replace('\u2002', ' ').replace('\u2003', ' ')
        text = re.sub(r'\s+', ' ', text)
        if text == '-': return '0'
        text = re.sub(r'\(\s*-?(\d+(?:,\d{3})*(?:\.\d+)?)\s*(%?)\s*\)', r'-\1\2', text)
        return re.sub(r'(?<!\d)-?\d+(?:,\d{3})*(?:\.\d+)?(?!\d)', lambda m: m.group(0).replace(',', ''), text)

    df_cleaned = df.map(clean_cell_notes) if hasattr(df, 'map') else df.applymap(clean_cell_notes)
    data_rows = df_cleaned.values.tolist()

    curr_node = table_tag.next_sibling
    search_limit = 10
    while curr_node and search_limit > 0:
        if getattr(curr_node, 'name', None) == 'table': break
        node_text = curr_node.get_text(separator=" ", strip=True) if hasattr(curr_node, 'get_text') else str(curr_node).strip()
        if not node_text:
            curr_node = curr_node.next_sibling
            search_limit -= 1; continue
            
        if re.search(marker_pattern, node_text):
            captured_texts.append(node_text)
            matches = list(re.finditer(marker_pattern, node_text))
            for idx, match in enumerate(matches):
                marker = match.group(1); start_idx = match.end()
                end_idx = matches[idx+1].start() if idx + 1 < len(matches) else len(node_text)
                text_part = re.sub(r'계\s*속\s*[:;]*', '', node_text[start_idx:end_idx]).strip()
                if text_part:
                    annotations.append({"type": "footnote", "marker": marker.strip(), "text": text_part})
            search_limit = 10 
        else:
            search_limit -= 1
        curr_node = curr_node.next_sibling

    return {"columns": columns, "rows": data_rows, "annotations": annotations, "captured_texts": captured_texts}

def clean_tree(node):
    if isinstance(node, dict):
        if "tables" in node and node["tables"]:
            merged_tables = []; current_unit = ""
            for tbl in node["tables"]:
                if not tbl: continue
                is_unit = "단위" in str(tbl.get("columns", "")) or (len(tbl.get("rows", [])) == 1 and "단위" in str(tbl["rows"]))
                if is_unit:
                    current_unit = str(tbl["rows"][0][0]) if tbl.get("rows") else ""
                    continue
                merged_tables.append({"unit": current_unit, "columns": tbl.get("columns", []), "rows": tbl.get("rows", []), "annotations": tbl.get("annotations", [])})
                current_unit = ""
            node["tables"] = merged_tables
        for k, v in list(node.items()):
            if k in ["sub_sections", "tables"] and not v: del node[k]
            else: node[k] = clean_tree(v)
    elif isinstance(node, str):
        return re.sub(r' {2,}', ' ', node).strip()
    return node

# ==========================================
# 2. 개별 파싱 모듈 함수
# ==========================================
def parse_intro(soup):
    intro_data = {}
    audit_report = soup.find(string=re.compile(r'독립된\s*감사인의\s*감사보고서'))
    if audit_report:
        container = audit_report.find_parent(['p', 'div'])
        content_parts = []
        if container:
            for sibling in container.find_next_siblings(['p', 'div', 'table']):
                if re.search(r'회사의\s*개요', sibling.get_text()): break
                content_parts.append(clean_text(sibling.get_text(separator=" ", strip=True)))
        intro_data["감사보고서"] = {
            "title": "독립된 감사인의 감사보고서",
            "content": " ".join(content_parts) if content_parts else "",
            "tables": [],
            "sub_sections": {}
        }
        
    company_overview = soup.find(string=re.compile(r'1\.\s*회사의\s*개요'))
    if company_overview:
        container = company_overview.find_parent(['p', 'div'])
        content_parts = []
        if container:
            for sibling in container.find_next_siblings(['p', 'div', 'table']):
                if re.search(r'2\.\s*재무제표\s*작성기준', sibling.get_text()): break
                content_parts.append(clean_text(sibling.get_text(separator=" ", strip=True)))
        intro_data["회사의개요"] = {
            "title": "회사의 개요",
            "content": " ".join(content_parts) if content_parts else "",
            "tables": [],
            "sub_sections": {}
        }
    return intro_data

def extract_financial_statement(tables, title, keywords):
    for df in tables:
        df_string = df.to_string().replace(" ", "")
        if all(kw in df_string for kw in keywords):
            target_df = df.copy()
            if isinstance(target_df.columns, pd.MultiIndex):
                target_df.columns = [str(col) for col in target_df.columns]
            else:
                target_df.columns = [str(c) for c in target_df.columns]

            cols = list(target_df.columns)
            account_col = cols[0] 
            note_col = next((c for c in cols if '주석' in c.replace(" ", "") or '비고' in c.replace(" ", "")), None)
            val_cols = [c for c in cols if c != account_col and c != note_col]

            if len(val_cols) >= 2:
                if len(val_cols) >= 4:
                    target_df['당기금액'] = target_df[val_cols[0]].fillna(target_df[val_cols[1]])
                    target_df['전기금액'] = target_df[val_cols[2]].fillna(target_df[val_cols[3]])
                else:
                    target_df['당기금액'] = target_df[val_cols[0]]
                    target_df['전기금액'] = target_df[val_cols[1]]

                target_df = target_df.dropna(subset=['당기금액', '전기금액'], how='all')
                target_df['과목명'] = target_df[account_col].apply(clean_account)
                target_df['당기금액'] = target_df['당기금액'].apply(clean_amount)
                target_df['전기금액'] = target_df['전기금액'].apply(clean_amount)
                target_df['관련주석'] = target_df[note_col].apply(clean_note) if note_col else [[] for _ in range(len(target_df))]
                
                final_df = target_df[['과목명', '관련주석', '당기금액', '전기금액']].dropna(subset=['과목명'])
                final_df['당기금액'] = final_df.apply(lambda row: adjust_unit(row, '당기금액'), axis=1)
                final_df['전기금액'] = final_df.apply(lambda row: adjust_unit(row, '전기금액'), axis=1)
                final_df = final_df.where(pd.notnull(final_df), None)
                
                return {
                    title: {
                        "title": title,
                        "content": f"회사의 {title}입니다.",
                        "tables": [{
                            "unit": "(단위: 원)",
                            "columns": ["과목명", "관련주석", "당기금액", "전기금액"],
                            "rows": final_df.values.tolist(),
                            "annotations": []
                        }],
                        "sub_sections": {}
                    }
                }
    return {}

def parse_appendix(soup):
    appendix_data = {
        "title": "감사보고서 부록",
        "content": "내부회계관리제도 관련 보고서 및 외부감사 실시내용입니다.",
        "tables": [],
        "sub_sections": {}
    }
    
    target_tags_1 = soup.find_all(string=re.compile(r'내부회계관리제도\s*검토보고서|내부회계관리제도\s*감사보고서'))
    if target_tags_1:
        start_tag = target_tags_1[0].find_parent(['p', 'div', 'h1', 'h2', 'h3'])
        if start_tag:
            content = []
            tables = []
            for sibling in start_tag.find_next_siblings(['p', 'div', 'table', 'h1', 'h2', 'h3']):
                text = sibling.get_text(strip=True)
                if re.search(r'운영실태\s*평가보고서|운영실태보고서|운영실태\s*보고서', text) and not re.search(r'검토보고서|감사보고서', text):
                    break
                if sibling.name == 'table':
                    columns = [str(i) for i in range(len(sibling.find('tr').find_all(['td', 'th'])))] if sibling.find('tr') else ["0"]
                    tables.append(html_table_to_dict(sibling, columns))
                else:
                    content.append(clean_text(text))
            appendix_data["sub_sections"]["감사인의 내부회계관리제도 보고서"] = {
                "title": "감사인의 내부회계관리제도 보고서",
                "content": "\n".join([c for c in content if c]),
                "tables": tables,
                "sub_sections": {}
            }

    target_tags_2 = soup.find_all(string=re.compile(r'내부회계관리제도\s*운영실태\s*평가보고서|내부회계관리제도\s*운영실태보고서|내부회계관리제도\s*운영실태\s*보고서'))
    if target_tags_2:
        start_tag = target_tags_2[-1].find_parent(['p', 'div', 'h1', 'h2', 'h3'])
        if start_tag:
            content = []
            tables = []
            for sibling in start_tag.find_next_siblings(['p', 'div', 'table', 'h1', 'h2', 'h3']):
                text = sibling.get_text(strip=True)
                if re.search(r'외부감사\s*실시내용', text): break
                if sibling.name == 'table':
                    columns = [str(i) for i in range(len(sibling.find('tr').find_all(['td', 'th'])))] if sibling.find('tr') else ["0"]
                    tables.append(html_table_to_dict(sibling, columns))
                else:
                    content.append(clean_text(text))
            appendix_data["sub_sections"]["경영진의 내부회계관리제도 운영실태보고서"] = {
                "title": "경영진의 내부회계관리제도 운영실태보고서",
                "content": "\n".join([c for c in content if c]),
                "tables": tables,
                "sub_sections": {}
            }

    target_tags_3 = soup.find_all(string=re.compile(r'외부감사\s*실시내용'))
    if target_tags_3:
        start_tag = target_tags_3[-1].find_parent(['p', 'div', 'h1', 'h2', 'h3'])
        if start_tag:
            content = []
            tables = []
            for sibling in start_tag.find_next_siblings(['p', 'div', 'table']):
                if sibling.name == 'table':
                    columns = [str(i) for i in range(len(sibling.find('tr').find_all(['td', 'th'])))] if sibling.find('tr') else ["0"]
                    tables.append(html_table_to_dict(sibling, columns))
                else:
                    content.append(clean_text(sibling.get_text(strip=True)))
            appendix_data["sub_sections"]["외부감사 실시내용"] = {
                "title": "외부감사 실시내용",
                "content": " ".join([c for c in content if c]),
                "tables": tables,
                "sub_sections": {}
            }
            
    return {"부록": appendix_data}

# ==========================================
# 💥 [추가됨] 주석 파싱 모듈 
# (원본 로직을 안전하게 감싸서 각 파일마다 실행되도록 처리)
# ==========================================
def parse_complex_notes(html_content):
    # 원본 soup 객체가 파괴되지 않도록 이 함수 안에서만 새로 파싱합니다.
    soup = BeautifulSoup(re.sub(r'\r?\n', '', html_content), 'html.parser')
    for tag in soup.find_all(['span', 'font', 'b', 'strong', 'i', 'em', 'u']): tag.unwrap()
    soup.smooth()
    
    # --- 🚀 [수정] id="toc_5" 발견 시 그 뒤를 물리적으로 삭제 ---
    stop_node = soup.find(id="toc_5")
    if stop_node:
        for sibling in stop_node.find_all_next():
            sibling.decompose()
        stop_node.decompose()

    table_store = {}; all_captured_footnotes = set()
    for idx, table in enumerate(soup.find_all('table')):
        if table.find('table'): continue
        res = html_table_to_dict_notes(table)
        if res:
            tid = f"[[TABLE_{idx}]]"
            if "captured_texts" in res:
                all_captured_footnotes.update(res["captured_texts"])
            table_store[tid] = res
            table.replace_with(f"\n{tid}\n")

    pure_text = soup.get_text(separator='\n', strip=True).replace('\xa0', ' ').replace('\u2002', ' ').replace('\u2003', ' ')
    pure_text = re.sub(r'(\d)\s+(?=\d)', r'\1', pure_text)
    pure_text = re.sub(r'(\.)\s*(\d{1,2})\s*\.\s*([^:\n]+?)\s*:\s*', r'\1\n\2. \3\n', pure_text)

    lines = [l.strip() for l in pure_text.split('\n') if l.strip()]
    final_data = {}; curr_L1 = curr_L2 = curr_L3 = curr_L4 = None; started = False
    kor_ord = {chr(i): i for i in range(ord('가'), ord('하')+1)}; curr_L3_char = ""
    kill_pattern = r'[,.]?\s*\d*[.\s]*계\s*속\s*[:;]*\s*$'

    for line in lines:
        line = line.strip()
        check_line = re.sub(kill_pattern, '', line).strip()
        if not started:
            if re.match(r'^1\.\s*(일반적\s*사항|회사의\s*개요)', check_line): started = True
            else: continue

        m1 = re.match(r'^(\d+)\s*\.\s*(.*)', check_line)
        if m1 and m1.group(1).isdigit():
            num = m1.group(1)
            if 1 <= int(num) <= 60 and num not in final_data:
                final_data[num] = {"title": m1.group(2).strip(), "content": "", "tables": [], "sub_sections": {}}
                curr_L1, curr_L2, curr_L3, curr_L4 = final_data[num], None, None, None
                curr_L3_char = ""; continue
        m2 = re.match(r'^(\d+\.\d+)\.?\s+(.*)', check_line)
        if m2 and curr_L1:
            key = m2.group(1) 
            curr_L1["sub_sections"][key] = {"title": m2.group(2).strip(), "content": "", "tables": [], "sub_sections": {}}
            curr_L2, curr_L3, curr_L4 = curr_L1["sub_sections"][key], None, None
            curr_L3_char = ""; continue
        m3 = re.match(r'^([가-하])\s*\.\s+(.*)', check_line)
        if m3:
            new_char = m3.group(1)
            is_restart = (kor_ord.get(new_char, 0) <= kor_ord.get(curr_L3_char, 0)) if curr_L3_char else False
            if not is_restart:
                parent = curr_L2 or curr_L1
                if parent:
                    key = new_char + "."; orig_key = key; counter = 1
                    while key in parent["sub_sections"]: key = f"{orig_key}_{counter}"; counter += 1
                    parent["sub_sections"][key] = {"title": m3.group(2).strip(), "content": "", "tables": [], "sub_sections": {}}
                    curr_L3, curr_L4, curr_L3_char = parent["sub_sections"][key], None, new_char
                    continue
        m4 = re.match(r'^(\(\d+\))\s+(.*)', check_line)
        if m4:
            parent = curr_L3 or curr_L2 or curr_L1
            if parent:
                key = m4.group(1).strip(); orig_key = key; counter = 1
                while key in parent["sub_sections"]: key = f"{orig_key}_{counter}"; counter += 1
                parent["sub_sections"][key] = {"title": m4.group(2).strip(), "content": "", "tables": [], "sub_sections": {}}
                curr_L4 = parent["sub_sections"][key]; continue

        active_node = curr_L4 or curr_L3 or curr_L2 or curr_L1
        if active_node:
            if line in all_captured_footnotes: continue
            if re.match(r'^계\s*속\s*[:;]*$', line) or re.search(kill_pattern, line): continue
            
            if '[[TABLE_' in line:
                for part in re.split(r'(\[\[TABLE_\d+\]\])', line):
                    if part in table_store: active_node["tables"].append(table_store[part])
                    elif part.strip() and part not in all_captured_footnotes: 
                        clean_part = re.sub(kill_pattern, '', part).strip()
                        if clean_part and clean_part != active_node.get("title", ""):
                            active_node["content"] += " " + clean_part
            else:
                if check_line and check_line != active_node.get("title", ""):
                    active_node["content"] += " " + check_line

    return {"주석": clean_tree(final_data)}

# ==========================================
# 3. 메인 파이프라인 함수
# ==========================================
def run_pipeline(raw_dir: str, processed_dir: str):
    file_list = glob.glob(os.path.join(raw_dir, '*.htm*'))
    file_list.sort()
    
    if not file_list:
        print(f"[{raw_dir}] 경로에 HTML 파일이 없습니다.")
        return

    print(f"총 {len(file_list)}개의 파일을 찾았습니다. 파싱을 시작합니다...\n" + "-"*50)

    for file_path in file_list:
        year_match = re.search(r'20\d{2}', os.path.basename(file_path))
        year = year_match.group() if year_match else "Unknown"
        print(f"[{year}년] {os.path.basename(file_path)} 처리 중...")
        
        try:
            with open(file_path, 'r', encoding='cp949') as f: html_content = f.read()
        except UnicodeDecodeError:
            with open(file_path, 'r', encoding='utf-8') as f: html_content = f.read()

        soup = BeautifulSoup(html_content, 'lxml')
        try:
            tables = pd.read_html(io.StringIO(html_content), encoding='cp949')
        except ValueError:
            tables = []

        year_data = {year: {}}

        # 기존 파싱 로직들
        year_data[year].update(parse_intro(soup))
        year_data[year].update(extract_financial_statement(tables, "재무상태표", ['유동자산', '유동부채', '이익잉여금']))
        year_data[year].update(extract_financial_statement(tables, "손익계산서", ['매출액', '영업이익', '당기순이익']))
        year_data[year].update(extract_financial_statement(tables, "포괄손익계산서", ['당기순이익', '총포괄손익']))
        year_data[year].update(extract_financial_statement(tables, "자본변동표", ['자본금', '이익잉여금', '자본총계']))
        year_data[year].update(extract_financial_statement(tables, "현금흐름표", ['영업활동현금흐름', '투자활동현금흐름']))
        year_data[year].update(parse_appendix(soup))
        
        # 💥 [추가됨] 주석 로직 파이프라인 결합
        # (원본을 건드리지 않기 위해 html_content 문자열을 통째로 넘김)
        year_data[year].update(parse_complex_notes(html_content))

        save_path = os.path.join(processed_dir, f'audit_report_{year}_structured.json')
        with open(save_path, 'w', encoding='utf-8') as f:
            json.dump(year_data, f, ensure_ascii=False, indent=4)
            
        print(f"  -> 완료! {save_path} 생성됨.")

    print("-" * 50 + "\n🎉 전체 파이프라인 처리가 완료되었습니다!")

# ==========================================
# 4. 진입점 (기존 뼈대 구조 유지)
# ==========================================
def main() -> None:
    raw_dir = Path("./data/raw")
    processed_dir = Path("./data/processed")
    processed_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"raw_dir={raw_dir}")
    print(f"processed_dir={processed_dir}")
    print("ingest pipeline 파싱을 시작합니다.")
    
    run_pipeline(str(raw_dir), str(processed_dir))

if __name__ == "__main__":
    main()