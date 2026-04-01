import pandas as pd
import io
import re
import os
import glob
import json
from bs4 import BeautifulSoup
from pathlib import Path

# ==========================================
# 1. 헬퍼 함수
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

    df_cleaned = df.applymap(clean_cell)
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

# ------------------------------------------
# [추가됨] 주석 파싱 로직 (parsing (1).ipynb 통합)
# ------------------------------------------
def parse_notes(soup):
    notes_data = {
        "title": "재무제표에 대한 주석",
        "content": "",
        "tables": [],
        "sub_sections": {}
    }
    
    note_tag = soup.find(string=re.compile(r'재무제표에\s*대한\s*주석|주\s*석\s*사항'))
    if note_tag:
        parent = note_tag.find_parent(['p', 'div', 'h1', 'h2', 'h3'])
        if parent:
            content = []
            tables = []
            for sibling in parent.find_next_siblings(['p', 'div', 'table']):
                if sibling.get_text(strip=True) and re.search(r'독립된\s*감사인의\s*감사보고서|내부회계관리제도', sibling.get_text()):
                    break
                if sibling.name == 'table':
                    columns = [str(i) for i in range(len(sibling.find('tr').find_all(['td', 'th'])))] if sibling.find('tr') else ["0"]
                    tables.append(html_table_to_dict(sibling, columns))
                else:
                    content.append(clean_text(sibling.get_text(strip=True)))
            notes_data['content'] = "\n".join([c for c in content if c])
            notes_data['tables'] = tables
            
    return {"주석": notes_data}

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

        year_data[year].update(parse_intro(soup))
        year_data[year].update(extract_financial_statement(tables, "재무상태표", ['유동자산', '유동부채', '이익잉여금']))
        year_data[year].update(extract_financial_statement(tables, "손익계산서", ['매출액', '영업이익', '당기순이익']))
        year_data[year].update(extract_financial_statement(tables, "포괄손익계산서", ['당기순이익', '총포괄손익']))
        year_data[year].update(extract_financial_statement(tables, "자본변동표", ['자본금', '이익잉여금', '자본총계']))
        year_data[year].update(extract_financial_statement(tables, "현금흐름표", ['영업활동현금흐름', '투자활동현금흐름']))
        year_data[year].update(parse_appendix(soup))
        
        # 💥 [추가됨] 주석 로직 파이프라인 결합
        year_data[year].update(parse_notes(soup))

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
    
    # Path 객체를 문자열로 변환하여 파이프라인 함수에 전달합니다.
    run_pipeline(str(raw_dir), str(processed_dir))

if __name__ == "__main__":
    main()