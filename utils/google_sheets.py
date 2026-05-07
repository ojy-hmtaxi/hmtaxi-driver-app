import re
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
import gspread
from google.oauth2.service_account import Credentials
import config
import os


def _is_sheets_read_quota_error(exc):
    """Google Sheets API 분당 읽기 한도(429 RESOURCE_EXHAUSTED) 여부."""
    msg = str(exc)
    return (
        '429' in msg
        or 'RESOURCE_EXHAUSTED' in msg
        or 'Quota exceeded' in msg
        or 'RATE_LIMIT_EXCEEDED' in msg
    )


def _sheets_quota_backoff(attempt_index):
    """429 시 지수 백오프 + 소량 지터."""
    time.sleep(min(0.45 * (2 ** attempt_index) + random.random() * 0.25, 22.0))


def _retry_sheets_operation(operation_fn, attempts=6):
    """읽기 쿼터 초과 시 짧게 재시도."""
    last_exc = None
    for attempt in range(attempts):
        try:
            return operation_fn()
        except Exception as e:
            last_exc = e
            if attempt < attempts - 1 and _is_sheets_read_quota_error(e):
                print(f"Sheets API 재시도({attempt + 1}/{attempts}): {e}")
                _sheets_quota_backoff(attempt)
                continue
            raise
    raise last_exc


ACCOUNTS_CACHE_TTL_SEC = 180
_accounts_cache_lock = threading.Lock()
_accounts_cache_records = None
_accounts_cache_ts = 0.0


def get_google_sheets_client():
    """Google Sheets API 클라이언트 생성"""
    # 환경 변수에서 인증 정보 가져오기 (Cloudtype.io 등 클라우드 배포용)
    credentials_dict = config.get_google_credentials()

    if credentials_dict:
        creds = Credentials.from_service_account_info(
            credentials_dict,
            scopes=config.SCOPES,
        )
    else:
        if not os.path.exists(config.CREDENTIALS_FILE):
            raise FileNotFoundError(
                f"credentials.json 파일을 찾을 수 없습니다.\n"
                f"로컬 개발 환경에서는 {config.CREDENTIALS_FILE} 파일이 필요합니다.\n"
                f"클라우드 배포 환경에서는 GOOGLE_CREDENTIALS 환경 변수에 서비스 계정 JSON 전체 문자열을 설정하세요."
            )
        creds = Credentials.from_service_account_file(
            config.CREDENTIALS_FILE,
            scopes=config.SCOPES,
        )

    client = gspread.authorize(creds)
    return client

def _open_work_spreadsheet_once():
    """work_DB 스프레드시트 1회 오픈 (429는 상위에서 재시도)."""
    client = get_google_sheets_client()
    
    if config.SPREADSHEET_ID:
        try:
            return client.open_by_key(config.SPREADSHEET_ID)
        except Exception as e:
            print(f"Warning: Failed to open spreadsheet by ID {config.SPREADSHEET_ID}: {e}")
    
    try:
        return client.open(config.SPREADSHEET_NAME)
    except gspread.exceptions.SpreadsheetNotFound:
        print(f"Error: Spreadsheet '{config.SPREADSHEET_NAME}' not found.")
        print("Trying to list available spreadsheets...")
        try:
            spreadsheets = client.openall()
            print(f"Available spreadsheets ({len(spreadsheets)} found):")
            for sheet in spreadsheets:
                print(f"  - {sheet.title} (ID: {sheet.id})")
        except Exception as list_err:
            print(f"  Could not list spreadsheets: {list_err}")
        
        raise Exception(
            f"스프레드시트 '{config.SPREADSHEET_NAME}'을(를) 찾을 수 없습니다.\n"
            f"다음 중 하나를 확인하세요:\n"
            f"1. 스프레드시트 이름이 정확한지 확인: {config.SPREADSHEET_NAME}\n"
            f"2. 서비스 계정이 스프레드시트에 편집자 권한으로 공유되었는지 확인\n"
            f"3. config.py의 SPREADSHEET_ID가 올바른지 확인: {config.SPREADSHEET_ID}"
        )


def get_spreadsheet():
    """스프레드시트 객체 반환 (읽기 한도 초과 시 자동 재시도)."""
    return _retry_sheets_operation(_open_work_spreadsheet_once)


def get_worksheet(sheet_name):
    """특정 워크시트 반환"""
    spreadsheet = get_spreadsheet()
    return spreadsheet.worksheet(sheet_name)

def _open_sales_spreadsheet_once():
    """sales_DB 스프레드시트 1회 오픈."""
    client = get_google_sheets_client()
    
    if config.SALES_SPREADSHEET_ID:
        try:
            return client.open_by_key(config.SALES_SPREADSHEET_ID)
        except Exception as e:
            print(f"Warning: Failed to open sales spreadsheet by ID {config.SALES_SPREADSHEET_ID}: {e}")
    
    try:
        return client.open(config.SALES_SPREADSHEET_NAME)
    except gspread.exceptions.SpreadsheetNotFound:
        print(f"Error: Sales Spreadsheet '{config.SALES_SPREADSHEET_NAME}' not found.")
        raise Exception(
            f"매출 스프레드시트 '{config.SALES_SPREADSHEET_NAME}'을(를) 찾을 수 없습니다.\n"
            f"서비스 계정이 스프레드시트에 편집자 권한으로 공유되었는지 확인하세요."
        )


def get_sales_spreadsheet():
    """sales_DB_2026 스프레드시트 객체 반환 (읽기 한도 초과 시 자동 재시도)."""
    return _retry_sheets_operation(_open_sales_spreadsheet_once)


def get_sales_worksheet(month_sheet_name):
    """sales_DB_2026의 특정 월별 워크시트 반환"""
    spreadsheet = get_sales_spreadsheet()
    return spreadsheet.worksheet(month_sheet_name)

def get_accounts_data():
    """accounts 시트에서 모든 사용자 데이터 가져오기 (단기 캐시로 읽기 호출 감소)."""
    global _accounts_cache_records, _accounts_cache_ts

    now = time.time()
    with _accounts_cache_lock:
        if _accounts_cache_records is not None and now - _accounts_cache_ts < ACCOUNTS_CACHE_TTL_SEC:
            return list(_accounts_cache_records)

    def fetch_records():
        worksheet = get_worksheet("accounts")
        return worksheet.get_all_records()
        
    try:
        records = _retry_sheets_operation(fetch_records)
        
        normalized_records = []
        for record in records:
            normalized_record = {}
            for key, value in record.items():
                normalized_key = key.strip() if key else key
                normalized_record[normalized_key] = value
            normalized_records.append(normalized_record)
        
        with _accounts_cache_lock:
            _accounts_cache_records = normalized_records
            _accounts_cache_ts = time.time()
        return list(normalized_records)
    except Exception as e:
        print(f"Error getting accounts data: {e}")
        import traceback
        traceback.print_exc()
        with _accounts_cache_lock:
            stale = _accounts_cache_records
        if stale is not None:
            print('Warning: accounts 시트 조회 실패 — 직전에 성공한 캐시 데이터를 사용합니다.')
            return list(stale)
        return []

def get_user_by_id(employee_id):
    """사번으로 사용자 정보 가져오기"""
    try:
        accounts = get_accounts_data()
        employee_id = str(employee_id).strip()
        
        for account in accounts:
            # employee_id를 여러 방법으로 비교 (문자열, 숫자 모두 지원)
            account_id = account.get('employee_id')
            if account_id is None:
                continue
                
            # 숫자인 경우와 문자열인 경우 모두 처리
            account_id_str = str(account_id).strip()
            
            # 직접 비교
            if account_id_str == employee_id:
                return account
            
            # 숫자로 변환하여 비교
            try:
                if int(account_id_str) == int(employee_id):
                    return account
            except (ValueError, TypeError):
                pass
        
        return None
    except Exception as e:
        print(f"Error getting user by id: {e}")
        import traceback
        traceback.print_exc()
        return None

def update_user_password(employee_id, password_hash):
    """사용자 비밀번호 해시 업데이트"""
    try:
        worksheet = get_worksheet("accounts")
        accounts = worksheet.get_values(ACCOUNTS_READ_RANGE)
        
        if not accounts:
            return False
        
        # 헤더 행 찾기 (공백 제거)
        header = [str(h).strip() for h in accounts[0]]
        
        try:
            employee_id_col = header.index('employee_id') + 1
            password_hash_col = header.index('password_hash') + 1
        except ValueError:
            print(f"Error: Could not find columns. Header: {header}")
            return False
        
        # 해당 사번의 행 찾기
        for i, row in enumerate(accounts[1:], start=2):
            if len(row) >= employee_id_col:
                row_employee_id = str(row[employee_id_col - 1]).strip() if row[employee_id_col - 1] else ""
                if row_employee_id == str(employee_id).strip():
                    worksheet.update_cell(i, password_hash_col, password_hash)
                    return True
        return False
    except Exception as e:
        print(f"Error updating user password: {e}")
        import traceback
        traceback.print_exc()
        return False

# 캘린더·근무 조회 시 시트 전체 대신 읽는 열 범위 (전송량·API 부담 감소)
WORK_DB_READ_RANGE = 'A:AM'  # 차량·사번·근무일·결근일·휴가·일별 상태(31일)까지
SALES_DB_READ_RANGE = 'A:N'  # 요약·운행일 판별에 필요한 열
LOANER_DB_READ_RANGE = 'A:F'  # 차량번호·차종·대차가능·신청일·사용자·사번
ACCOUNTS_READ_RANGE = 'A:Z'  # accounts 시트(아이디/해시 등) 조회 범위


def _rows_to_dict_records(raw_rows):
    """시트 2차원 배열을 get_all_records와 유사한 dict 리스트로 변환"""
    if not raw_rows:
        return []
    header = [str(h).strip() for h in raw_rows[0]]
    records = []
    for row in raw_rows[1:]:
        rec = {}
        for i, key in enumerate(header):
            if not key:
                continue
            val = row[i] if i < len(row) else ''
            rec[key] = '' if val is None or val == '' else str(val).strip()
        if rec.get('사번'):
            records.append(rec)
        return records


def get_monthly_work_data(month_sheet_name, spreadsheet=None):
    """월별 근무 데이터 가져오기 (A:AM 범위만 조회, 캘린더·근무표에 충분).
    spreadsheet가 있으면 get_spreadsheet() 재호출 없이 해당 통합문서에서 시트만 연다."""
    try:
        ss = spreadsheet if spreadsheet is not None else get_spreadsheet()
        worksheet = ss.worksheet(month_sheet_name)
        raw = worksheet.get_values(WORK_DB_READ_RANGE)
        if not raw:
            return []
        return _rows_to_dict_records(raw)
    except Exception as e:
        print(f"Error getting monthly work data: {e}")
        return []

def get_user_work_data(employee_id, month_sheet_name):
    """특정 사용자의 월별 근무 데이터 가져오기 (첫 번째 행만 반환)"""
    try:
        records = get_monthly_work_data(month_sheet_name)
        for record in records:
            if str(record.get('사번', '')).strip() == str(employee_id).strip():
                return record
        return None
    except Exception as e:
        print(f"Error getting user work data: {e}")
        return None

def get_all_user_work_data(employee_id, month_sheet_name, spreadsheet=None):
    """특정 사용자의 월별 근무 데이터 가져오기 (같은 사번의 모든 행 반환)"""
    try:
        records = get_monthly_work_data(month_sheet_name, spreadsheet)
        user_records = []
        for record in records:
            if str(record.get('사번', '')).strip() == str(employee_id).strip():
                user_records.append(record)
        return user_records if user_records else None
    except Exception as e:
        print(f"Error getting all user work data: {e}")
        return None

def update_work_status(employee_id, date, month_sheet_name, status='O', work_details=None, vehicle_number=None, work_type=None):
    """근무 상태 업데이트 (O 또는 X) 및 메모 추가
    
    Args:
        employee_id: 사번
        date: 날짜 (일)
        month_sheet_name: 월별 시트 이름
        status: 상태 ('O', 'X' 등)
        work_details: 근무 상세 정보 (딕셔너리)
        vehicle_number: 차량번호 (선택사항, 지정하면 해당 차량의 행을 찾음)
        work_type: 근무유형 (선택사항, 지정하면 해당 근무유형의 행을 찾음)
    """
    try:
        worksheet = get_worksheet(month_sheet_name)
        all_values = worksheet.get_values(WORK_DB_READ_RANGE)
        
        if not all_values:
            return False
        
        # 헤더 행 찾기
        header = [str(h).strip() for h in all_values[0]]
        
        try:
            employee_id_col = header.index('사번') + 1
        except ValueError:
            return False
        
        # 차량번호 컬럼 찾기 (vehicle_number가 제공된 경우)
        vehicle_number_col = None
        if vehicle_number:
            try:
                vehicle_number_col = header.index('차량번호') + 1
            except ValueError:
                pass
        
        # 근무유형 컬럼 찾기 (work_type이 제공된 경우)
        work_type_col = None
        if work_type:
            try:
                work_type_col = header.index('근무유형') + 1
            except ValueError:
                pass
        
        # 날짜 컬럼 찾기 (숫자로 변환하여 찾기)
        date_col = None
        date_str = str(date).strip()
        for idx, col_name in enumerate(header, start=1):
            if str(col_name).strip() == date_str:
                date_col = idx
                break
        
        if date_col is None:
            return False
        
        # 해당 사번의 행 찾기 (차량번호와 근무유형이 있으면 모두 일치하는 행 찾기)
        for i, row in enumerate(all_values[1:], start=2):
            if len(row) >= employee_id_col:
                # 사번 일치 확인
                if str(row[employee_id_col - 1]).strip() == str(employee_id).strip():
                    # 차량번호가 제공된 경우, 차량번호도 일치하는지 확인
                    if vehicle_number and vehicle_number_col:
                        if len(row) >= vehicle_number_col:
                            row_vehicle_number = str(row[vehicle_number_col - 1]).strip()
                            if row_vehicle_number != str(vehicle_number).strip():
                                # 차량번호가 일치하지 않으면 다음 행으로
                                continue
                    elif vehicle_number:
                        # 차량번호 컬럼이 없으면 첫 번째 일치하는 행 사용
                        pass
                    
                    # 근무유형이 제공된 경우, 근무유형도 일치하는지 확인
                    if work_type and work_type_col:
                        if len(row) >= work_type_col:
                            row_work_type = str(row[work_type_col - 1]).strip()
                            if row_work_type != str(work_type).strip():
                                # 근무유형이 일치하지 않으면 다음 행으로
                                continue
                    elif work_type:
                        # 근무유형 컬럼이 없으면 첫 번째 일치하는 행 사용
                        pass
                    
                    # 상태 업데이트
                    worksheet.update_cell(i, date_col, status)
                    
                    # 메모 추가 (work_details가 있는 경우)
                    if work_details:
                        note_text = format_work_details_note(work_details)
                        if note_text:  # 메모 내용이 있을 때만 추가
                            try:
                                # gspread의 셀 주소 변환 함수 사용
                                from gspread.utils import rowcol_to_a1
                                cell_address = rowcol_to_a1(i, date_col)
                                
                                # gspread의 insert_note 메서드 사용 (버전에 따라 다를 수 있음)
                                if hasattr(worksheet, 'insert_note'):
                                    worksheet.insert_note(cell_address, note_text)
                                else:
                                    # insert_note가 없으면 Google Sheets API 직접 사용
                                    add_note_via_api(worksheet, i, date_col, note_text)
                            except Exception as note_error:
                                # 모든 방법 실패 시 API 직접 사용
                                print(f"Warning: Could not insert note: {note_error}")
                                try:
                                    add_note_via_api(worksheet, i, date_col, note_text)
                                except Exception as api_error:
                                    print(f"Warning: Could not insert note via API: {api_error}")
                    
                    # 근무일수와 결근일수 업데이트
                    update_work_stats(worksheet, i, header, employee_id)
                    return True
        return False
    except Exception as e:
        print(f"Error updating work status: {e}")
        import traceback
        traceback.print_exc()
        return False

def format_work_details_note(work_details):
    """근무 상세 정보를 메모 형식으로 포맷팅"""
    note_lines = []
    
    if work_details.get('vehicle_number'):
        note_lines.append(f"운행차량: {work_details.get('vehicle_number')}")
    
    if work_details.get('work_date'):
        note_lines.append(f"운행시작일시: {work_details.get('work_date')}")
    
    if work_details.get('work_type'):
        note_lines.append(f"근무유형: {work_details.get('work_type')}")
    
    # TODO(restore): if work_details.get('vehicle_condition'):
    #     note_lines.append(f"차량상태: {work_details.get('vehicle_condition')}")
    
    # TODO(restore): if work_details.get('special_notes'):
    #     note_lines.append(f"보고사항: {work_details.get('special_notes')}")
    
    return "\n".join(note_lines) if note_lines else ""

def add_note_via_api(worksheet, row, col, note_text):
    """Google Sheets API를 사용하여 메모 추가"""
    try:
        from googleapiclient.discovery import build
        from google.oauth2.service_account import Credentials
        import config
        
        # 인증 정보 가져오기
        credentials_dict = config.get_google_credentials()
        if credentials_dict:
            creds = Credentials.from_service_account_info(
                credentials_dict,
                scopes=config.SCOPES
            )
        else:
            creds = Credentials.from_service_account_file(
                config.CREDENTIALS_FILE,
                scopes=config.SCOPES,
            )
        
        # Google Sheets API 서비스 빌드
        service = build('sheets', 'v4', credentials=creds)
        
        # 스프레드시트 ID 가져오기
        spreadsheet_id = config.SPREADSHEET_ID
        if not spreadsheet_id:
            spreadsheet = get_spreadsheet()
            spreadsheet_id = spreadsheet.id
        
        # 시트 ID 가져오기 (API를 통해 메타데이터 가져오기)
        metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        sheet_id = None
        for sheet in metadata.get('sheets', []):
            if sheet['properties']['title'] == worksheet.title:
                sheet_id = sheet['properties']['sheetId']
                break
        
        if sheet_id is None:
            print(f"Error: Could not find sheet ID for {worksheet.title}")
            return False
        
        # 메모 추가 요청
        requests = [{
            'updateCells': {
                'range': {
                    'sheetId': sheet_id,
                    'startRowIndex': row - 1,
                    'endRowIndex': row,
                    'startColumnIndex': col - 1,
                    'endColumnIndex': col
                },
                'rows': [{
                    'values': [{
                        'note': note_text
                    }]
                }],
                'fields': 'note'
            }
        }]
        
        body = {
            'requests': requests
        }
        
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body=body
        ).execute()
        
        print(f"Successfully added note to cell row {row}, col {col}")
        return True
    except Exception as e:
        print(f"Error adding note via API: {e}")
        import traceback
        traceback.print_exc()
        return False

def update_work_stats(worksheet, row_num, header, employee_id):
    """근무일/결근일 자동 계산 및 업데이트."""
    try:
        # 날짜 컬럼 찾기 (1~31)
        date_columns = []
        for col_idx, col_name in enumerate(header, start=1):
            try:
                day = int(str(col_name).strip())
                if 1 <= day <= 31:
                    date_columns.append((col_idx, day))
            except (ValueError, AttributeError):
                continue
        
        # O와 X 개수 계산
        work_count = 0
        absent_count = 0
        
        # 업데이트 후 최신 데이터 가져오기
        row_values = worksheet.row_values(row_num)
        for col_idx, day in date_columns:
            if col_idx <= len(row_values):
                value = str(row_values[col_idx - 1]).strip().upper()
                if value == 'O':
                    work_count += 1
                elif value == 'X':
                    absent_count += 1
        
        # 근무일/결근일 컬럼 찾기
        try:
            from gspread.utils import rowcol_to_a1
            work_days_col = header.index('근무일') + 1
            absent_days_col = header.index('결근일') + 1

            # 네트워크 왕복 감소: 두 셀을 batch_update 1회로 처리
            ranges = [
                {
                    'range': rowcol_to_a1(row_num, work_days_col),
                    'values': [[work_count]],
                },
                {
                    'range': rowcol_to_a1(row_num, absent_days_col),
                    'values': [[absent_count]],
                },
            ]
            try:
                worksheet.batch_update(ranges, value_input_option='USER_ENTERED')
            except Exception:
                # 배치 업데이트 실패 시 기존 방식으로 폴백 (보호 셀 메시지 유지)
                try:
                    worksheet.update_cell(row_num, work_days_col, work_count)
                except Exception as e:
                    error_msg = str(e)
                    if 'protected' in error_msg.lower() or 'permission' in error_msg.lower():
                        print("Warning: '근무일' 셀이 보호되어 있어 업데이트를 건너뜁니다.")
                    else:
                        print(f"Warning: '근무일' 업데이트 실패: {e}")

                try:
                    worksheet.update_cell(row_num, absent_days_col, absent_count)
                except Exception as e:
                    error_msg = str(e)
                    if 'protected' in error_msg.lower() or 'permission' in error_msg.lower():
                        print("Warning: '결근일' 셀이 보호되어 있어 업데이트를 건너뜁니다.")
                    else:
                        print(f"Warning: '결근일' 업데이트 실패: {e}")
        except ValueError:
            # 컬럼이 없으면 스킵
            pass
    except Exception as e:
        print(f"Error updating work stats: {e}")

def get_all_months_data(employee_id):
    """사용자의 모든 월별 데이터 가져오기 (첫 번째 행만 반환)"""
    all_data = {}
    for month in config.MONTHS:
        data = get_user_work_data(employee_id, month)
        if data:
            all_data[month] = data
    return all_data


def work_history_month_sheet_names(reference_date, recent_months):
    """근무 이력용: 당해 기준 조회할 월 시트 이름 목록.
    recent_months가 None이거나 12 이상이면 1~12월 전부.
    그 외에는 reference_date.month까지 역으로 최대 N개(연초 이후 월 수까지만)."""
    if recent_months is None or int(recent_months) >= 12:
        return list(config.MONTHS)
    n = max(1, min(12, int(recent_months)))
    m = reference_date.month
    start_idx = max(0, m - n)
    return config.MONTHS[start_idx:m]


def _aggregate_user_month_records(all_records):
    """같은 월·같은 사번의 모든 행을 근무 이력용 dict 한 개로 합산."""
    if not all_records:
        return None
    aggregated = {}
    first_record = all_records[0]
    for key, value in first_record.items():
        if key not in ['근무일', '결근일', '인정일']:
            aggregated[key] = value
    work_days_total = 0
    absent_days_total = 0
    approved_days_total = 0
    for record in all_records:
        try:
            work_days_val = record.get('근무일', 0) or 0
            work_days_total += int(work_days_val) if work_days_val else 0
        except (ValueError, TypeError):
            pass
        try:
            absent_days_val = record.get('결근일', 0) or 0
            absent_days_total += int(absent_days_val) if absent_days_val else 0
        except (ValueError, TypeError):
            pass
        try:
            approved_val = record.get('인정일', 0) or 0
            approved_days_total += int(approved_val) if approved_val else 0
        except (ValueError, TypeError):
            pass
    aggregated['근무일'] = work_days_total
    aggregated['결근일'] = absent_days_total
    aggregated['인정일'] = approved_days_total
    return aggregated


def _work_history_fetch_one_month(employee_id, month_name, spreadsheet, work_data_cache):
    """한 개월 시트 조회 → 사번 필터 → 집계. work_data_cache는 app.SimpleCache( get/set )."""
    cache_key = f"work_data:{employee_id}:{month_name}"
    if work_data_cache is not None:
        cached = work_data_cache.get(cache_key)
        if cached is not None:
            return month_name, _aggregate_user_month_records(cached)
    records = get_monthly_work_data(month_name, spreadsheet)
    user_records = []
    for record in records:
        if str(record.get('사번', '')).strip() == str(employee_id).strip():
            user_records.append(record)
    user_list = user_records if user_records else None
    if work_data_cache is not None and user_list is not None:
        work_data_cache.set(cache_key, user_list)
    return month_name, _aggregate_user_month_records(user_list)


def get_all_months_aggregated_data(
    employee_id,
    reference_date=None,
    recent_months=None,
    work_data_cache=None,
    max_workers=8,
):
    """사용자의 월별 근무 데이터 합산 (근무 이력 차트용).

    - reference_date: 기준일(당해 연도·월). 기본 오늘(서버 로컬 date; 호출부에서 KST 넘기 권장).
    - recent_months: 조회할 월 시트 개수(당해, reference 월까지 역으로). None/12 이상이면 1~12월 전부.
    - work_data_cache: 캘린더와 동일 키(work_data:사번:월)로 per-month 리스트 캐시.
    - spreadsheet는 1회만 연 뒤 워커에서 시트만 전환(get_monthly_work_data(..., spreadsheet)).
    """
    ref = reference_date or date.today()
    if recent_months is None:
        recent_months = 12
    month_names = work_history_month_sheet_names(ref, recent_months)
    if not month_names:
        return {}
    spreadsheet = get_spreadsheet()
    all_data = {}
    workers = min(max(1, int(max_workers)), len(month_names))
    if len(month_names) == 1:
        try:
            mn, agg = _work_history_fetch_one_month(
                employee_id, month_names[0], spreadsheet, work_data_cache
            )
            if agg:
                all_data[mn] = agg
        except Exception as e:
            print(f"Error in work history month fetch ({month_names[0]}): {e}")
        return all_data
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(
                _work_history_fetch_one_month, employee_id, mn, spreadsheet, work_data_cache
            )
            for mn in month_names
        ]
        for fut in as_completed(futures):
            try:
                mn, agg = fut.result()
                if agg:
                    all_data[mn] = agg
            except Exception as e:
                print(f"Error in work history month fetch: {e}")
    return all_data

def get_today_work_start_info(employee_id, month_sheet_name, day):
    """오늘 날짜의 근무 시작 정보 가져오기 (work_DB_2026의 메모에서)"""
    try:
        worksheet = get_worksheet(month_sheet_name)
        all_values = worksheet.get_values(WORK_DB_READ_RANGE)
        
        if not all_values:
            return None
        
        # 헤더 행 찾기
        header = [str(h).strip() for h in all_values[0]]
        
        try:
            employee_id_col = header.index('사번') + 1
        except ValueError:
            return None
        
        # 날짜 컬럼 찾기
        date_col = None
        date_str = str(day).strip()
        for idx, col_name in enumerate(header, start=1):
            if str(col_name).strip() == date_str:
                date_col = idx
                break
        
        if date_col is None:
            return None

        from gspread.utils import rowcol_to_a1

        vehicle_num_col = header.index('차량번호') + 1 if '차량번호' in header else None
        vehicle_type_col = header.index('차종') + 1 if '차종' in header else None
        first_info_with_note = None  # 운행시작일시 없는 경우 폴백

        # 해당 사번의 행 찾기 (운행시작일시가 있는 행 = 해당일 실제 근무 시작 행을 우선)
        for i, row in enumerate(all_values[1:], start=2):
            if len(row) < employee_id_col or str(row[employee_id_col - 1]).strip() != str(employee_id).strip():
                continue
            cell_address = rowcol_to_a1(i, date_col)
            try:
                note_text = worksheet.get_note(cell_address) if hasattr(worksheet, 'get_note') else get_note_via_api(worksheet, i, date_col)
            except Exception:
                note_text = None
            if not note_text:
                continue
            info = {}
            for line in note_text.split('\n'):
                if ':' in line:
                    key, value = line.split(':', 1)
                    key, value = key.strip(), value.strip()
                    if key == '운행차량':
                        info['vehicle_number'] = value
                    elif key == '운행시작일시':
                        info['work_date'] = value
                    elif key == '근무유형':
                        info['work_type'] = value
                    elif key == '차량상태':
                        info['vehicle_condition'] = value
                    elif key == '보고사항':
                        info['special_notes'] = value
            if vehicle_num_col and len(row) >= vehicle_num_col:
                info['vehicle_number'] = row[vehicle_num_col - 1].strip()
            if vehicle_type_col and len(row) >= vehicle_type_col:
                info['vehicle_type'] = row[vehicle_type_col - 1].strip()
            if first_info_with_note is None:
                first_info_with_note = info
            if info.get('work_date'):
                return info
        return first_info_with_note
    except Exception as e:
        print(f"Error getting today work start info: {e}")
        import traceback
        traceback.print_exc()
        return None

def get_note_via_api(worksheet, row, col):
    """Google Sheets API를 사용하여 메모 가져오기"""
    try:
        from googleapiclient.discovery import build
        from google.oauth2.service_account import Credentials
        import config
        
        # 인증 정보 가져오기
        credentials_dict = config.get_google_credentials()
        if credentials_dict:
            creds = Credentials.from_service_account_info(
                credentials_dict,
                scopes=config.SCOPES
            )
        else:
            creds = Credentials.from_service_account_file(
                config.CREDENTIALS_FILE,
                scopes=config.SCOPES,
            )
        
        # Google Sheets API 서비스 빌드
        service = build('sheets', 'v4', credentials=creds)
        
        # 스프레드시트 ID 가져오기
        spreadsheet_id = config.SPREADSHEET_ID
        if not spreadsheet_id:
            spreadsheet = get_spreadsheet()
            spreadsheet_id = spreadsheet.id
        
        # 시트 ID 가져오기
        metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        sheet_id = None
        for sheet in metadata.get('sheets', []):
            if sheet['properties']['title'] == worksheet.title:
                sheet_id = sheet['properties']['sheetId']
                break
        
        if sheet_id is None:
            return None
        
        # 메모 가져오기
        from gspread.utils import rowcol_to_a1
        cell_address = rowcol_to_a1(row, col)
        range_name = f"{worksheet.title}!{cell_address}"
        
        result = service.spreadsheets().get(
            spreadsheetId=spreadsheet_id,
            ranges=[range_name],
            includeGridData=True
        ).execute()
        
        if result.get('sheets'):
            sheet_data = result['sheets'][0]
            if sheet_data.get('data'):
                row_data = sheet_data['data'][0]
                if row_data.get('rowData'):
                    cell_data = row_data['rowData'][0]
                    if cell_data.get('values'):
                        note = cell_data['values'][0].get('note', '')
                        return note
        
        return None
    except Exception as e:
        print(f"Error getting note via API: {e}")
        return None

def add_sales_record(month_sheet_name, sales_data, note_text=None):
    """sales_DB_2026에 매출 데이터 추가
    
    Args:
        month_sheet_name: 월별 시트 이름
        sales_data: 매출 데이터 딕셔너리
        note_text: 근무시간(분) 셀에 추가할 메모 (운행시작일시, 운행종료일시, 근무시간)
        # TODO(restore): 임시 비활성화 - vehicle_condition_note
        # TODO(restore): vehicle_condition_note: 차량번호 셀에 추가할 메모 (보고사항)
    """
    try:
        worksheet = get_sales_worksheet(month_sheet_name)
        
        # 헤더 가져오기
        header = worksheet.row_values(1)
        header = [str(h).strip() for h in header]
        
        # 다음 행 번호 계산 (헤더 포함 기존 데이터 개수 + 1)
        all_values = worksheet.get_values(SALES_DB_READ_RANGE)
        next_row = len(all_values) + 1 if all_values else 2
        
        # 데이터 행 구성
        row_data = []
        for col_name in header:
            value = sales_data.get(col_name, '')
            row_data.append(value)
        
        # 새 행 추가
        worksheet.append_row(row_data)
        
        # 근무시간(분) 셀에 메모 추가 (운행시작일시, 운행종료일시, 근무시간)
        if note_text and '근무시간(분)' in header:
            try:
                from gspread.utils import rowcol_to_a1
                work_time_col = header.index('근무시간(분)') + 1
                cell_address = rowcol_to_a1(next_row, work_time_col)
                
                if hasattr(worksheet, 'insert_note'):
                    worksheet.insert_note(cell_address, note_text)
                else:
                    # gspread에서 insert_note 지원하지 않는 경우 API 사용
                    add_note_via_api(worksheet, next_row, work_time_col, note_text)
            except Exception as note_error:
                print(f"Warning: Could not insert note for sales record: {note_error}")
                try:
                    add_note_via_api(worksheet, next_row, work_time_col, note_text)
                except Exception as api_error:
                    print(f"Warning: Could not insert note via API for sales record: {api_error}")
        
        # TODO(restore): 차량번호 셀에 메모 추가 (보고사항)
        # TODO(restore): if vehicle_condition_note and '차량번호' in header:
        #    try:
        # TODO(restore):        from gspread.utils import rowcol_to_a1
        # TODO(restore):        vehicle_number_col = header.index('차량번호') + 1
        # TODO(restore):        cell_address = rowcol_to_a1(next_row, vehicle_number_col)
        #        
        # TODO(restore):        if hasattr(worksheet, 'insert_note'):
        # TODO(restore):            worksheet.insert_note(cell_address, vehicle_condition_note)
        # TODO(restore):        else:
        # TODO(restore):            # gspread에서 insert_note 지원하지 않는 경우 API 사용
        # TODO(restore):            add_note_via_api(worksheet, next_row, vehicle_number_col, vehicle_condition_note)
        
        print(f"Successfully added sales record to {month_sheet_name}")
        return True
    except Exception as e:
        print(f"Error adding sales record: {e}")
        import traceback
        traceback.print_exc()
        return False

def _normalize_sales_operation_date(operation_date):
    if not operation_date:
        return ''
    s = str(operation_date).strip()
    if '-' in s:
        return s.replace('-', '/')
    return s


def get_user_sales_summary(employee_id, month_sheet_name):
    """sales_DB_2026에서 특정 사번의 월별 매출 합계 가져오기 (A:N 범위만 조회).
    같은 스캔으로 운행일 집합(operation_dates)을 채워 has_sales_record 에서 재사용한다.
    
    Args:
        employee_id: 사번
        month_sheet_name: 월별 시트 이름 (예: '11월')
    
    Returns:
        dict: {
            'total_revenue': 총 매출 (현금운임 + 카드운임),
            'total_fuel_cost': 총 연료비,
            'accident_count': 가해사고 건수,
            'operation_dates': set of 'YYYY/MM/DD' (해당 사번 행의 운행일, 날짜별 Sheets 재조회 방지용)
        }
    """
    try:
        worksheet = get_sales_worksheet(month_sheet_name)
        all_values = worksheet.get_values(SALES_DB_READ_RANGE)
        if not all_values or len(all_values) < 2:
            return {'total_revenue': 0, 'total_fuel_cost': 0, 'accident_count': 0, 'operation_dates': set()}
        
        header = [str(h).strip() for h in all_values[0]]
        
        # 컬럼 인덱스 찾기
        try:
            employee_id_col_idx = header.index('사번')
            cash_fare_col_idx = header.index('현금운임')
            card_fare_col_idx = header.index('카드운임')
            fuel_cost_col_idx = header.index('연료비')
        except ValueError as e:
            print(f"Error: Required column not found in sales sheet: {e}")
            return {'total_revenue': 0, 'total_fuel_cost': 0, 'accident_count': 0, 'operation_dates': set()}
        
        accident_col_idx = header.index('사고유무') if '사고유무' in header else None
        operation_date_col_idx = header.index('운행일') if '운행일' in header else None
        
        total_revenue = 0
        total_fuel_cost = 0
        accident_count = 0
        operation_dates = set()
        
        # 데이터 행 처리 (헤더 제외, 인덱스 1부터)
        for row_idx, row in enumerate(all_values[1:], start=2):
            max_col = max(employee_id_col_idx, cash_fare_col_idx, card_fare_col_idx, fuel_cost_col_idx)
            if accident_col_idx is not None:
                max_col = max(max_col, accident_col_idx)
            if operation_date_col_idx is not None:
                max_col = max(max_col, operation_date_col_idx)
            if len(row) <= max_col:
                continue
            
            # 사번 확인
            row_employee_id = str(row[employee_id_col_idx]).strip()
            if row_employee_id != str(employee_id):
                continue
            
            if operation_date_col_idx is not None and len(row) > operation_date_col_idx:
                od = _normalize_sales_operation_date(row[operation_date_col_idx])
                if od:
                    operation_dates.add(od)
            
            # 현금운임
            try:
                cash_fare_str = str(row[cash_fare_col_idx]).strip().replace(',', '')
                cash_fare = int(cash_fare_str) if cash_fare_str else 0
                total_revenue += cash_fare
            except (ValueError, TypeError):
                pass
            
            # 카드운임
            try:
                card_fare_str = str(row[card_fare_col_idx]).strip().replace(',', '')
                card_fare = int(card_fare_str) if card_fare_str else 0
                total_revenue += card_fare
            except (ValueError, TypeError):
                pass
            
            # 연료비
            try:
                fuel_cost_str = str(row[fuel_cost_col_idx]).strip().replace(',', '')
                fuel_cost = int(fuel_cost_str) if fuel_cost_str else 0
                total_fuel_cost += fuel_cost
            except (ValueError, TypeError):
                pass
            
            # 가해사고 건수 (같은 시트 한 번 읽기로 함께 계산)
            if accident_col_idx is not None:
                accident_status = str(row[accident_col_idx]).strip()
                if accident_status and ('가해' in accident_status or '가해사고' in accident_status):
                    accident_count += 1
        
        return {
            'total_revenue': total_revenue,
            'total_fuel_cost': total_fuel_cost,
            'accident_count': accident_count,
            'operation_dates': operation_dates,
        }
    except Exception as e:
        print(f"Error getting user sales summary: {e}")
        import traceback
        traceback.print_exc()
        return {'total_revenue': 0, 'total_fuel_cost': 0, 'accident_count': 0, 'operation_dates': set()}

def has_sales_record_for_date(employee_id, month_sheet_name, operation_date):
    """매출 시트를 다시 읽지 않고 get_user_sales_summary와 동일 스캔 결과(운행일 집합)로 판별.
    단독 호출 시 1회 A:N 조회만 수행."""
    try:
        summary = get_user_sales_summary(employee_id, month_sheet_name)
        dates = summary.get('operation_dates') or set()
        normalized_date = _normalize_sales_operation_date(operation_date)
        return normalized_date in dates
    except Exception as e:
        print(f"Error checking sales record for date: {e}")
        return False


# ----- 대차신청 (차량 교체) -----
LOANER_SHEET_NAME = "대차차량"


def get_loaner_vehicles():
    """[대차차량] 시트에서 대차가능('O')인 차량 목록 반환"""
    try:
        worksheet = get_worksheet(LOANER_SHEET_NAME)
        all_values = worksheet.get_values(LOANER_DB_READ_RANGE)
        if not all_values or len(all_values) < 2:
            return []
        header = [str(h).strip() for h in all_values[0]]
        col_idx = {h: i for i, h in enumerate(header)}
        need = ['차량번호', '차종', '대차가능', '복귀시간(엄수)']
        if not all(k in col_idx for k in need):
            return []
        out = []
        for row in all_values[1:]:
            if len(row) <= max(col_idx.values()):
                continue
            가능 = str(row[col_idx['대차가능']]).strip().upper()
            if 가능 != 'O':
                continue
            out.append({
                '차량번호': str(row[col_idx['차량번호']]).strip(),
                '차종': str(row[col_idx['차종']]).strip(),
                '복귀시간(엄수)': str(row[col_idx['복귀시간(엄수)']]).strip() if '복귀시간(엄수)' in col_idx else ''
            })
        return out
    except Exception as e:
        print(f"Error get_loaner_vehicles: {e}")
        return []


def update_loaner_vehicle_on_apply(vehicle_number, employee_id, driver_name, apply_date_str):
    """대차 신청 시 [대차차량] 시트 해당 행 수정: 대차가능=X, 대차신청일, 대차사용자, 사번"""
    try:
        worksheet = get_worksheet(LOANER_SHEET_NAME)
        all_values = worksheet.get_values(LOANER_DB_READ_RANGE)
        if not all_values or len(all_values) < 2:
            return False
        header = [str(h).strip() for h in all_values[0]]
        col_idx = {h: i for i, h in enumerate(header)}
        num_col = col_idx.get('차량번호')
        if num_col is None:
            return False
        vn = str(vehicle_number).strip()
        from gspread.utils import rowcol_to_a1
        for i, row in enumerate(all_values[1:], start=2):
            if len(row) <= num_col:
                continue
            if str(row[num_col]).strip() == vn:
                updates = []
                if '대차가능' in col_idx:
                    updates.append({
                        'range': rowcol_to_a1(i, col_idx['대차가능'] + 1),
                        'values': [['X']],
                    })
                if '대차신청일' in col_idx:
                    updates.append({
                        'range': rowcol_to_a1(i, col_idx['대차신청일'] + 1),
                        'values': [[apply_date_str]],
                    })
                if '대차사용자' in col_idx:
                    updates.append({
                        'range': rowcol_to_a1(i, col_idx['대차사용자'] + 1),
                        'values': [[driver_name or '']],
                    })
                if '사번' in col_idx:
                    updates.append({
                        'range': rowcol_to_a1(i, col_idx['사번'] + 1),
                        'values': [[str(employee_id or '')]],
                    })
                if updates:
                    worksheet.batch_update(updates, value_input_option='USER_ENTERED')
                return True
        return False
    except Exception as e:
        print(f"Error update_loaner_vehicle_on_apply: {e}")
        return False


def reset_loaner_vehicle_on_work_end(vehicle_number, employee_id):
    """대차 차량으로 근무 종료 시 [대차차량] 시트 해당 행 초기화.
    - 대차가능(C열)=O
    - 대차신청일(D열), 대차사용자(E열), 사번(F열)=빈칸
    차량번호·사번이 대차 신청 직후 기록과 일치하고 대차가능이 'X'인 행만 갱신한다."""
    try:
        worksheet = get_worksheet(LOANER_SHEET_NAME)
        all_values = worksheet.get_values(LOANER_DB_READ_RANGE)
        if not all_values or len(all_values) < 2:
            return False
        header = [str(h).strip() for h in all_values[0]]
        col_idx = {h: i for i, h in enumerate(header)}
        num_col = col_idx.get('차량번호')
        sabun_col = col_idx.get('사번')
        avail_col = col_idx.get('대차가능')
        if num_col is None or sabun_col is None or avail_col is None:
            return False
        vn_norm = str(vehicle_number).strip().replace(' ', '')
        eid = str(employee_id or '').strip()
        if not vn_norm or not eid:
            return False
        from gspread.utils import rowcol_to_a1
        for i, row in enumerate(all_values[1:], start=2):
            if len(row) <= max(num_col, sabun_col, avail_col):
                continue
            row_vn = str(row[num_col]).strip().replace(' ', '')
            row_eid = str(row[sabun_col]).strip()
            if row_vn != vn_norm or row_eid != eid:
                continue
            cur = str(row[avail_col]).strip().upper()
            if cur != 'X':
                continue
            updates = [
                {
                    'range': rowcol_to_a1(i, avail_col + 1),
                    'values': [['O']],
                }
            ]
            if '대차신청일' in col_idx:
                updates.append({
                    'range': rowcol_to_a1(i, col_idx['대차신청일'] + 1),
                    'values': [['']],
                })
            if '대차사용자' in col_idx:
                updates.append({
                    'range': rowcol_to_a1(i, col_idx['대차사용자'] + 1),
                    'values': [['']],
                })
            if '사번' in col_idx:
                updates.append({
                    'range': rowcol_to_a1(i, col_idx['사번'] + 1),
                    'values': [['']],
                })
            worksheet.batch_update(updates, value_input_option='USER_ENTERED')
            return True
        return False
    except Exception as e:
        print(f"Error reset_loaner_vehicle_on_work_end: {e}")
        return False


def update_work_cell_note_report(employee_id, month_sheet_name, day, report_value):
    """해당 월·일의 근무 셀 메모에서 '보고사항'만 갱신 (없으면 추가).
    같은 사번이 야간/주간 등 여러 행일 수 있으므로, 해당일 메모에 '운행시작일시'가 있는 행(실제 근무 시작된 행)을 찾아 그 셀만 수정한다."""
    try:
        worksheet = get_worksheet(month_sheet_name)
        all_values = worksheet.get_values(WORK_DB_READ_RANGE)
        if not all_values:
            return False
        header = [str(h).strip() for h in all_values[0]]
        try:
            emp_col = header.index('사번') + 1
        except ValueError:
            return False
        date_str = str(day).strip()
        try:
            date_col = header.index(date_str) + 1
        except ValueError:
            return False
        from gspread.utils import rowcol_to_a1

        def do_update(i, note_text):
            """메모 내용을 보고사항만 갱신한 새 메모로 덮어쓰기 (기존 보고사항 유지하고 새 값 추가)"""
            note_text = note_text or ''
            lines = [ln.strip() for ln in note_text.split('\n') if ln.strip()]
            new_lines = []
            found = False
            existing_report_value = None
            for ln in lines:
                if ln.startswith('보고사항:'):
                    # 기존 보고사항 값 추출 (콜론 뒤의 모든 내용)
                    existing_report_value = ln.split(':', 1)[1].strip() if ':' in ln else ''
                    found = True
                    # 기존 보고사항 줄을 새 줄로 교체 (기존 값 + ", " + 새 값)
                    if existing_report_value:
                        new_lines.append(f"보고사항: {existing_report_value}, {report_value}")
                    else:
                        new_lines.append(f"보고사항: {report_value}")
                else:
                    new_lines.append(ln)
            if not found:
                # 보고사항 줄이 없으면 추가
                new_lines.append(f"보고사항: {report_value}")
            new_note = '\n'.join(new_lines)
            cell_address = rowcol_to_a1(i, date_col)
            if hasattr(worksheet, 'insert_note'):
                worksheet.insert_note(cell_address, new_note)
            else:
                add_note_via_api(worksheet, i, date_col, new_note)
            return True

        first_matching_row = None  # 운행시작일시가 없는 경우 대비 첫 번째 매칭 행
        for i, row in enumerate(all_values[1:], start=2):
            if len(row) < emp_col:
                continue
            if str(row[emp_col - 1]).strip() != str(employee_id).strip():
                continue
            if first_matching_row is None:
                first_matching_row = i
            cell_address = rowcol_to_a1(i, date_col)
            try:
                note_text = worksheet.get_note(cell_address) if hasattr(worksheet, 'get_note') else None
            except Exception:
                note_text = get_note_via_api(worksheet, i, date_col)
            note_text = note_text or ''
            # 해당일 근무가 시작된 행 = 메모에 '운행시작일시'가 있는 셀
            if '운행시작일시' in note_text or '운행시작일시:' in note_text:
                return do_update(i, note_text)

        # 해당일 '운행시작일시' 메모가 있는 행이 없으면, 사번 일치 첫 행에 반영 (폴백)
        if first_matching_row is not None:
            try:
                nt = worksheet.get_note(rowcol_to_a1(first_matching_row, date_col)) if hasattr(worksheet, 'get_note') else None
            except Exception:
                nt = get_note_via_api(worksheet, first_matching_row, date_col)
            return do_update(first_matching_row, nt or '')
        return False
    except Exception as e:
        print(f"Error update_work_cell_note_report: {e}")
        return False


def parse_replacement_vehicle_from_remark(remark):
    """보고사항 문자열에서 '(대차)' 앞의 차량번호 추출.
    예: '33바1812 (대차)', '보고사항: 33바1812 (대차)', '이상없음, 33바1813 (대차)'"""
    remark = (remark or '').strip()
    if '(대차)' not in remark:
        return None
    idx = remark.find('(대차)')
    num_part = remark[:idx].strip()
    if not num_part:
        return None
    compact = num_part.replace(' ', '')
    m = re.search(r'(\d{2}바\d{4})', compact)
    if m:
        return m.group(1)
    tail = num_part.split(',')[-1].strip().replace(' ', '')
    return tail if tail else None


def get_today_replacement_display(employee_id, month_sheet_name, day, work_start_info=None):
    """오늘(해당일) 근무 셀 메모의 보고사항에서 대차 차량이 있으면 (차량번호, 차종) 반환. 차량번호만 반환(보고사항 기타 문구 제외).
    work_start_info: 이미 조회한 근무시작 정보가 있으면 전달하여 중복 API 호출 방지."""
    try:
        info = work_start_info if work_start_info is not None else get_today_work_start_info(employee_id, month_sheet_name, day)
        if not info:
            return None
        # 대차 시 '보고사항' 줄에 기록되므로 special_notes에서 확인 (레거시는 vehicle_condition)
        remark = (info.get('special_notes') or info.get('vehicle_condition') or '').strip()
        num = parse_replacement_vehicle_from_remark(remark)
        if not num:
            return None
        ws = get_worksheet(LOANER_SHEET_NAME)
        all_values = ws.get_values(LOANER_DB_READ_RANGE)
        if not all_values or len(all_values) < 2:
            return (num, '')
        header = [str(h).strip() for h in all_values[0]]
        nc = header.index('차량번호') if '차량번호' in header else -1
        tc = header.index('차종') if '차종' in header else -1
        if nc < 0:
            return (num, '')
        for row in all_values[1:]:
            if len(row) <= max(nc, tc):
                continue
            if str(row[nc]).strip().replace(' ', '') == num:
                return (num, str(row[tc]).strip() if tc >= 0 and len(row) > tc else '')
        return (num, '')
    except Exception as e:
        print(f"Error get_today_replacement_display: {e}")
        return None


# ----- 휴가신청 (work_DB_2026 동일 스프레드시트 내 시트) -----
LEAVE_REQUEST_SHEET_NAME = '휴가신청'
LEAVE_REQUEST_READ_RANGE = 'A:I'


def _parse_sheet_date_value(val):
    """시트 날짜 셀을 date로 변환 (실패 시 None)."""
    if val is None:
        return None
    s = str(val).strip().replace('-', '/')
    if not s:
        return None
    try:
        base = s[:10] if len(s) >= 10 else s
        return datetime.strptime(base, '%Y/%m/%d').date()
    except (ValueError, TypeError):
        return None


def _format_yy_mm_dd(val):
    """표시용 YY/MM/DD."""
    d = _parse_sheet_date_value(val)
    if d:
        return f'{d.year % 100:02d}/{d.month:02d}/{d.day:02d}'
    return str(val).strip() if val is not None else ''


def _leave_status_bucket(raw):
    """승인상태 원본 → pending | approved | rejected (/·o·x 및 O·X 허용)."""
    s = str(raw).strip().lower()
    if s in ('/', '／', '', '대기'):
        return 'pending'
    if s in ('o', '〇'):
        return 'approved'
    if s in ('x',):
        return 'rejected'
    up = str(raw).strip().upper()
    if up == 'O':
        return 'approved'
    if up == 'X':
        return 'rejected'
    return 'pending'


def _safe_int_days(val):
    try:
        return max(0, int(float(str(val).strip().replace(',', ''))))
    except (ValueError, TypeError):
        return 0


def get_user_annual_leave_entitlement(user_record):
    """accounts 행(dict)에서 근속연차 일수 조회."""
    if not user_record:
        return 0
    raw = user_record.get('근속연차')
    try:
        if raw is None or str(raw).strip() == '':
            return 0
        return max(0, int(float(str(raw).strip())))
    except (ValueError, TypeError):
        return 0


def sum_approved_leave_days_for_employee(employee_id):
    """승인된 휴가(o/O) 기간 합계."""
    try:
        ws = get_worksheet(LEAVE_REQUEST_SHEET_NAME)
        rows = ws.get_values(LEAVE_REQUEST_READ_RANGE)
        if not rows or len(rows) < 2:
            return 0
        header = [str(h).strip() for h in rows[0]]
        try:
            idx_eid = header.index('사번')
            idx_duration = header.index('기간')
            idx_status = header.index('승인상태')
        except ValueError:
            return 0
        target = str(employee_id).strip()
        total = 0
        for row in rows[1:]:
            if len(row) <= max(idx_eid, idx_duration, idx_status):
                continue
            if str(row[idx_eid]).strip() != target:
                continue
            if _leave_status_bucket(row[idx_status]) != 'approved':
                continue
            total += _safe_int_days(row[idx_duration])
        return total
    except Exception as e:
        print(f'Error sum_approved_leave_days_for_employee: {e}')
        return 0


def get_leave_requests_for_display(employee_id):
    """로그인 사번 기준 휴가 신청 목록 (신청일 내림차순)."""
    try:
        ws = get_worksheet(LEAVE_REQUEST_SHEET_NAME)
        rows = ws.get_values(LEAVE_REQUEST_READ_RANGE)
        if not rows or len(rows) < 2:
            return []
        header = [str(h).strip() for h in rows[0]]
        try:
            idx_eid = header.index('사번')
            idx_apply = header.index('신청일')
            idx_start = header.index('시작일')
            idx_end = header.index('종료일')
            idx_name = header.index('이름')
            idx_duration = header.index('기간')
            idx_reason = header.index('사유')
            idx_status = header.index('승인상태')
        except ValueError:
            return []

        target = str(employee_id).strip()
        items = []
        for row in rows[1:]:
            if len(row) <= idx_eid:
                continue
            if str(row[idx_eid]).strip() != target:
                continue
            raw_apply = row[idx_apply] if len(row) > idx_apply else ''
            raw_status = row[idx_status] if len(row) > idx_status else ''
            bucket = _leave_status_bucket(raw_status)
            label = {'pending': '대기', 'approved': '승인', 'rejected': '반려'}.get(bucket, '대기')
            dur = _safe_int_days(row[idx_duration]) if len(row) > idx_duration else 0
            sort_key = _parse_sheet_date_value(raw_apply) or date.min
            items.append({
                'apply_disp': _format_yy_mm_dd(raw_apply),
                'start_disp': _format_yy_mm_dd(row[idx_start]) if len(row) > idx_start else '',
                'end_disp': _format_yy_mm_dd(row[idx_end]) if len(row) > idx_end else '',
                'duration': dur,
                'status_label': label,
                'status_kind': bucket,
                'apply_raw': str(raw_apply).strip(),
                'start_raw': str(row[idx_start]).strip() if len(row) > idx_start else '',
                'end_raw': str(row[idx_end]).strip() if len(row) > idx_end else '',
                'name': str(row[idx_name]).strip() if len(row) > idx_name else '',
                'employee_id': target,
                'reason': str(row[idx_reason]).strip() if len(row) > idx_reason else '',
                '_sort': sort_key,
            })

        items.sort(key=lambda x: x['_sort'], reverse=True)
        for it in items:
            it.pop('_sort', None)
        return items
    except Exception as e:
        print(f'Error get_leave_requests_for_display: {e}')
        return []


def append_leave_request_row(apply_date_str, employee_id, name, start_date_str, end_date_str, duration_days, reason_text):
    """휴가신청 시트에 한 행 추가. 승인상태는 '/'(대기). 구분은 빈 칸."""
    try:
        ws = get_worksheet(LEAVE_REQUEST_SHEET_NAME)
        header = [str(h).strip() for h in ws.row_values(1)]
        if not header:
            return False
        payload = {
            '신청일': apply_date_str,
            '사번': str(employee_id).strip(),
            '이름': (name or '').strip(),
            '시작일': start_date_str,
            '종료일': end_date_str,
            '기간': duration_days,
            '구분': '',
            '사유': (reason_text or '').strip(),
            '승인상태': '/',
        }
        row_out = [payload.get(h, '') for h in header]
        ws.append_row(row_out, value_input_option='USER_ENTERED')
        return True
    except Exception as e:
        print(f'Error append_leave_request_row: {e}')
        import traceback
        traceback.print_exc()
        return False


def delete_pending_leave_request_row(employee_id, name, apply_date_str, start_date_str, end_date_str):
    """휴가신청 시트에서 대기('/') 상태의 신청 1건 행 삭제."""
    try:
        ws = get_worksheet(LEAVE_REQUEST_SHEET_NAME)
        rows = ws.get_values(LEAVE_REQUEST_READ_RANGE)
        if not rows or len(rows) < 2:
            return False
        header = [str(h).strip() for h in rows[0]]
        try:
            idx_apply = header.index('신청일')
            idx_eid = header.index('사번')
            idx_name = header.index('이름')
            idx_start = header.index('시작일')
            idx_end = header.index('종료일')
            idx_status = header.index('승인상태')
        except ValueError:
            return False

        target_eid = str(employee_id).strip()
        target_name = str(name or '').strip()
        target_apply = str(apply_date_str or '').strip()
        target_start = str(start_date_str or '').strip()
        target_end = str(end_date_str or '').strip()

        for i, row in enumerate(rows[1:], start=2):
            if len(row) <= max(idx_apply, idx_eid, idx_name, idx_start, idx_end, idx_status):
                continue
            if str(row[idx_eid]).strip() != target_eid:
                continue
            if target_name and str(row[idx_name]).strip() != target_name:
                continue
            if str(row[idx_apply]).strip() != target_apply:
                continue
            if str(row[idx_start]).strip() != target_start:
                continue
            if str(row[idx_end]).strip() != target_end:
                continue
            if _leave_status_bucket(row[idx_status]) != 'pending':
                continue
            ws.delete_rows(i)
            return True
        return False
    except Exception as e:
        print(f'Error delete_pending_leave_request_row: {e}')
        import traceback
        traceback.print_exc()
        return False
