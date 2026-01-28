import gspread
from google.oauth2.service_account import Credentials
import config
import os

def get_google_sheets_client():
    """Google Sheets API 클라이언트 생성"""
    # 환경 변수에서 인증 정보 가져오기 (Cloudtype.io 등 클라우드 배포용)
    credentials_dict = config.get_google_credentials()
    
    if credentials_dict:
        # 환경 변수에서 가져온 JSON 사용
        creds = Credentials.from_service_account_info(
            credentials_dict,
            scopes=config.SCOPES
        )
    else:
        # 로컬 파일에서 읽기 (개발 환경)
        if not os.path.exists(config.CREDENTIALS_FILE):
            raise FileNotFoundError(
                f"credentials.json 파일을 찾을 수 없습니다.\n"
                f"로컬 개발 환경에서는 {config.CREDENTIALS_FILE} 파일이 필요합니다.\n"
                f"클라우드 배포 환경에서는 GOOGLE_CREDENTIALS 환경 변수를 설정하세요."
            )
        creds = Credentials.from_service_account_file(
            config.CREDENTIALS_FILE,
            scopes=config.SCOPES
        )
    
    client = gspread.authorize(creds)
    return client

def get_spreadsheet():
    """스프레드시트 객체 반환"""
    client = get_google_sheets_client()
    
    # 스프레드시트 ID가 있으면 ID로 열기 (우선순위)
    if config.SPREADSHEET_ID:
        try:
            spreadsheet = client.open_by_key(config.SPREADSHEET_ID)
            return spreadsheet
        except Exception as e:
            print(f"Warning: Failed to open spreadsheet by ID {config.SPREADSHEET_ID}: {e}")
            # ID로 열기 실패 시 이름으로 시도
    
    # 이름으로 찾기 시도
    try:
        return client.open(config.SPREADSHEET_NAME)
    except gspread.exceptions.SpreadsheetNotFound:
        print(f"Error: Spreadsheet '{config.SPREADSHEET_NAME}' not found.")
        print("Trying to list available spreadsheets...")
        try:
            # 접근 가능한 스프레드시트 목록 출력
            spreadsheets = client.openall()
            print(f"Available spreadsheets ({len(spreadsheets)} found):")
            for sheet in spreadsheets:
                print(f"  - {sheet.title} (ID: {sheet.id})")
        except Exception as e:
            print(f"  Could not list spreadsheets: {e}")
        
        raise Exception(
            f"스프레드시트 '{config.SPREADSHEET_NAME}'을(를) 찾을 수 없습니다.\n"
            f"다음 중 하나를 확인하세요:\n"
            f"1. 스프레드시트 이름이 정확한지 확인: {config.SPREADSHEET_NAME}\n"
            f"2. 서비스 계정이 스프레드시트에 편집자 권한으로 공유되었는지 확인\n"
            f"3. config.py의 SPREADSHEET_ID가 올바른지 확인: {config.SPREADSHEET_ID}"
        )

def get_worksheet(sheet_name):
    """특정 워크시트 반환"""
    spreadsheet = get_spreadsheet()
    return spreadsheet.worksheet(sheet_name)

def get_sales_spreadsheet():
    """sales_DB_2026 스프레드시트 객체 반환"""
    client = get_google_sheets_client()
    
    # 스프레드시트 ID가 있으면 ID로 열기 (우선순위)
    if config.SALES_SPREADSHEET_ID:
        try:
            spreadsheet = client.open_by_key(config.SALES_SPREADSHEET_ID)
            return spreadsheet
        except Exception as e:
            print(f"Warning: Failed to open sales spreadsheet by ID {config.SALES_SPREADSHEET_ID}: {e}")
            # ID로 열기 실패 시 이름으로 시도
    
    # 이름으로 찾기 시도
    try:
        return client.open(config.SALES_SPREADSHEET_NAME)
    except gspread.exceptions.SpreadsheetNotFound:
        print(f"Error: Sales Spreadsheet '{config.SALES_SPREADSHEET_NAME}' not found.")
        raise Exception(
            f"매출 스프레드시트 '{config.SALES_SPREADSHEET_NAME}'을(를) 찾을 수 없습니다.\n"
            f"서비스 계정이 스프레드시트에 편집자 권한으로 공유되었는지 확인하세요."
        )

def get_sales_worksheet(month_sheet_name):
    """sales_DB_2026의 특정 월별 워크시트 반환"""
    spreadsheet = get_sales_spreadsheet()
    return spreadsheet.worksheet(month_sheet_name)

def get_accounts_data():
    """accounts 시트에서 모든 사용자 데이터 가져오기"""
    try:
        worksheet = get_worksheet("accounts")
        
        # get_all_records()는 헤더를 키로 사용하는 딕셔너리 리스트를 반환
        records = worksheet.get_all_records()
        
        # 키의 공백을 제거하여 정규화 (Google Sheets의 헤더에 공백이 있을 수 있음)
        normalized_records = []
        for record in records:
            normalized_record = {}
            for key, value in record.items():
                # 키에서 앞뒤 공백 제거
                normalized_key = key.strip() if key else key
                normalized_record[normalized_key] = value
            normalized_records.append(normalized_record)
        
        return normalized_records
    except Exception as e:
        print(f"Error getting accounts data: {e}")
        import traceback
        traceback.print_exc()
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
        accounts = worksheet.get_all_values()
        
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

def get_monthly_work_data(month_sheet_name):
    """월별 근무 데이터 가져오기"""
    try:
        worksheet = get_worksheet(month_sheet_name)
        records = worksheet.get_all_records()
        return records
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

def get_all_user_work_data(employee_id, month_sheet_name):
    """특정 사용자의 월별 근무 데이터 가져오기 (같은 사번의 모든 행 반환)"""
    try:
        records = get_monthly_work_data(month_sheet_name)
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
        all_values = worksheet.get_all_values()
        
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
    
    if work_details.get('vehicle_condition'):
        note_lines.append(f"보고사항: {work_details.get('vehicle_condition')}")
    
    if work_details.get('special_notes'):
        note_lines.append(f"특기사항: {work_details.get('special_notes')}")
    
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
                scopes=config.SCOPES
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
    """근무일수와 결근일수 자동 계산 및 업데이트"""
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
        
        # 근무일수와 결근일수 컬럼 찾기
        try:
            work_days_col = header.index('근무일수') + 1
            absent_days_col = header.index('결근일수') + 1
            
            # 업데이트 (보호된 셀인 경우 오류 무시)
            try:
                worksheet.update_cell(row_num, work_days_col, work_count)
            except Exception as e:
                # 보호된 셀이거나 권한이 없는 경우 무시
                error_msg = str(e)
                if 'protected' in error_msg.lower() or 'permission' in error_msg.lower():
                    print(f"Warning: '근무일수' 셀이 보호되어 있어 업데이트를 건너뜁니다.")
                else:
                    print(f"Warning: '근무일수' 업데이트 실패: {e}")
            
            try:
                worksheet.update_cell(row_num, absent_days_col, absent_count)
            except Exception as e:
                # 보호된 셀이거나 권한이 없는 경우 무시
                error_msg = str(e)
                if 'protected' in error_msg.lower() or 'permission' in error_msg.lower():
                    print(f"Warning: '결근일수' 셀이 보호되어 있어 업데이트를 건너뜁니다.")
                else:
                    print(f"Warning: '결근일수' 업데이트 실패: {e}")
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

def get_all_months_aggregated_data(employee_id):
    """사용자의 모든 월별 데이터 가져오기 (같은 사번의 모든 행 합산)"""
    all_data = {}
    for month in config.MONTHS:
        all_records = get_all_user_work_data(employee_id, month)
        if all_records:
            # 근무일수와 결근일수 합산
            aggregated = {}
            work_days_total = 0
            absent_days_total = 0
            
            # 첫 번째 행의 데이터를 기본으로 사용
            first_record = all_records[0]
            for key, value in first_record.items():
                # 근무일수, 결근일수, 인정일수는 별도로 계산/처리하므로 제외
                if key not in ['근무일수', '결근일수', '인정일수']:
                    aggregated[key] = value
            
            # 근무일수와 결근일수 합산
            for record in all_records:
                try:
                    work_days_val = record.get('근무일수', 0) or 0
                    work_days_total += int(work_days_val) if work_days_val else 0
                except (ValueError, TypeError):
                    pass
                try:
                    absent_days_val = record.get('결근일수', 0) or 0
                    absent_days_total += int(absent_days_val) if absent_days_val else 0
                except (ValueError, TypeError):
                    pass
            
            aggregated['근무일수'] = work_days_total
            aggregated['결근일수'] = absent_days_total
            all_data[month] = aggregated
    
    return all_data

def get_today_work_start_info(employee_id, month_sheet_name, day):
    """오늘 날짜의 근무 시작 정보 가져오기 (work_DB_2026의 메모에서)"""
    try:
        worksheet = get_worksheet(month_sheet_name)
        all_values = worksheet.get_all_values()
        
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
        
        # 해당 사번의 행 찾기
        for i, row in enumerate(all_values[1:], start=2):
            if len(row) >= employee_id_col:
                if str(row[employee_id_col - 1]).strip() == str(employee_id).strip():
                    # 셀의 메모 가져오기
                    from gspread.utils import rowcol_to_a1
                    cell_address = rowcol_to_a1(i, date_col)
                    
                    try:
                        # gspread의 get_note 메서드 사용
                        if hasattr(worksheet, 'get_note'):
                            note_text = worksheet.get_note(cell_address)
                        else:
                            # API를 통해 메모 가져오기
                            note_text = get_note_via_api(worksheet, i, date_col)
                        
                        if note_text:
                            # 메모에서 정보 파싱
                            info = {}
                            for line in note_text.split('\n'):
                                if ':' in line:
                                    key, value = line.split(':', 1)
                                    key = key.strip()
                                    value = value.strip()
                                    if key == '운행차량':
                                        info['vehicle_number'] = value
                                    elif key == '운행시작일시':
                                        info['work_date'] = value
                                    elif key == '근무유형':
                                        info['work_type'] = value
                                    elif key == '보고사항':
                                        info['vehicle_condition'] = value
                                    elif key == '특기사항':
                                        info['special_notes'] = value
                            
                            # 차량번호와 차종도 행에서 가져오기
                            vehicle_num_col = header.index('차량번호') + 1 if '차량번호' in header else None
                            vehicle_type_col = header.index('차종') + 1 if '차종' in header else None
                            
                            if vehicle_num_col and len(row) >= vehicle_num_col:
                                info['vehicle_number'] = row[vehicle_num_col - 1].strip()
                            if vehicle_type_col and len(row) >= vehicle_type_col:
                                info['vehicle_type'] = row[vehicle_type_col - 1].strip()
                            
                            return info
                    except Exception as e:
                        print(f"Warning: Could not get note: {e}")
                        # 메모가 없어도 행에서 기본 정보 가져오기
                        info = {}
                        vehicle_num_col = header.index('차량번호') + 1 if '차량번호' in header else None
                        vehicle_type_col = header.index('차종') + 1 if '차종' in header else None
                        work_type_col = header.index('근무유형') + 1 if '근무유형' in header else None
                        
                        if vehicle_num_col and len(row) >= vehicle_num_col:
                            info['vehicle_number'] = row[vehicle_num_col - 1].strip()
                        if vehicle_type_col and len(row) >= vehicle_type_col:
                            info['vehicle_type'] = row[vehicle_type_col - 1].strip()
                        if work_type_col and len(row) >= work_type_col:
                            info['work_type'] = row[work_type_col - 1].strip()
                        
                        return info if info else None
        return None
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
                scopes=config.SCOPES
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

def add_sales_record(month_sheet_name, sales_data, note_text=None, vehicle_condition_note=None):
    """sales_DB_2026에 매출 데이터 추가
    
    Args:
        month_sheet_name: 월별 시트 이름
        sales_data: 매출 데이터 딕셔너리
        note_text: 근무시간(분) 셀에 추가할 메모 (운행시작일시, 운행종료일시, 근무시간)
        vehicle_condition_note: 차량번호 셀에 추가할 메모 (보고사항)
    """
    try:
        worksheet = get_sales_worksheet(month_sheet_name)
        
        # 헤더 가져오기
        header = worksheet.row_values(1)
        header = [str(h).strip() for h in header]
        
        # 다음 행 번호 계산 (헤더 포함 기존 데이터 개수 + 1)
        all_values = worksheet.get_all_values()
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
        
        # 차량번호 셀에 메모 추가 (보고사항)
        if vehicle_condition_note and '차량번호' in header:
            try:
                from gspread.utils import rowcol_to_a1
                vehicle_number_col = header.index('차량번호') + 1
                cell_address = rowcol_to_a1(next_row, vehicle_number_col)
                
                if hasattr(worksheet, 'insert_note'):
                    worksheet.insert_note(cell_address, vehicle_condition_note)
                else:
                    # gspread에서 insert_note 지원하지 않는 경우 API 사용
                    add_note_via_api(worksheet, next_row, vehicle_number_col, vehicle_condition_note)
            except Exception as note_error:
                print(f"Warning: Could not insert vehicle condition note for sales record: {note_error}")
                try:
                    add_note_via_api(worksheet, next_row, vehicle_number_col, vehicle_condition_note)
                except Exception as api_error:
                    print(f"Warning: Could not insert vehicle condition note via API for sales record: {api_error}")
        
        print(f"Successfully added sales record to {month_sheet_name}")
        return True
    except Exception as e:
        print(f"Error adding sales record: {e}")
        import traceback
        traceback.print_exc()
        return False

def get_user_sales_summary(employee_id, month_sheet_name):
    """sales_DB_2026에서 특정 사번의 월별 매출 합계 가져오기
    
    Args:
        employee_id: 사번
        month_sheet_name: 월별 시트 이름 (예: '11월')
    
    Returns:
        dict: {
            'total_revenue': 총 매출 (현금운임 + 카드운임),
            'total_fuel_cost': 총 연료비
        }
    """
    try:
        worksheet = get_sales_worksheet(month_sheet_name)
        
        # 헤더 가져오기
        header = worksheet.row_values(1)
        header = [str(h).strip() for h in header]
        
        # 모든 데이터 가져오기
        all_values = worksheet.get_all_values()
        
        if len(all_values) < 2:  # 헤더만 있거나 데이터가 없음
            return {'total_revenue': 0, 'total_fuel_cost': 0}
        
        # 컬럼 인덱스 찾기
        try:
            employee_id_col_idx = header.index('사번')
            cash_fare_col_idx = header.index('현금운임')
            card_fare_col_idx = header.index('카드운임')
            fuel_cost_col_idx = header.index('연료비')
        except ValueError as e:
            print(f"Error: Required column not found in sales sheet: {e}")
            return {'total_revenue': 0, 'total_fuel_cost': 0}
        
        total_revenue = 0
        total_fuel_cost = 0
        
        # 데이터 행 처리 (헤더 제외, 인덱스 1부터)
        for row_idx, row in enumerate(all_values[1:], start=2):
            if len(row) <= max(employee_id_col_idx, cash_fare_col_idx, card_fare_col_idx, fuel_cost_col_idx):
                continue
            
            # 사번 확인
            row_employee_id = str(row[employee_id_col_idx]).strip()
            if row_employee_id != str(employee_id):
                continue
            
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
        
        return {
            'total_revenue': total_revenue,
            'total_fuel_cost': total_fuel_cost
        }
    except Exception as e:
        print(f"Error getting user sales summary: {e}")
        import traceback
        traceback.print_exc()
        return {'total_revenue': 0, 'total_fuel_cost': 0}

def has_sales_record_for_date(employee_id, month_sheet_name, operation_date):
    """sales_DB_2026에서 특정 날짜에 해당 사번의 매출 기록이 있는지 확인
    
    Args:
        employee_id: 사번
        month_sheet_name: 월별 시트 이름 (예: '11월')
        operation_date: 운행일 (형식: 'YYYY/MM/DD' 또는 'YYYY-MM-DD')
    
    Returns:
        bool: 기록이 있으면 True, 없으면 False
    """
    try:
        worksheet = get_sales_worksheet(month_sheet_name)
        
        # 헤더 가져오기
        header = worksheet.row_values(1)
        header = [str(h).strip() for h in header]
        
        # 모든 데이터 가져오기
        all_values = worksheet.get_all_values()
        
        if len(all_values) < 2:  # 헤더만 있거나 데이터가 없음
            return False
        
        # 컬럼 인덱스 찾기
        try:
            employee_id_col_idx = header.index('사번')
            operation_date_col_idx = header.index('운행일')
        except ValueError:
            return False
        
        # operation_date 형식 정규화 (YYYY/MM/DD 또는 YYYY-MM-DD)
        if '/' in operation_date:
            normalized_date = operation_date
        elif '-' in operation_date:
            normalized_date = operation_date.replace('-', '/')
        else:
            normalized_date = operation_date
        
        # 데이터 행 확인 (헤더 제외, 인덱스 1부터)
        for row in all_values[1:]:
            if len(row) <= max(employee_id_col_idx, operation_date_col_idx):
                continue
            
            # 사번 확인
            row_employee_id = str(row[employee_id_col_idx]).strip()
            if row_employee_id != str(employee_id):
                continue
            
            # 운행일 확인
            row_operation_date = str(row[operation_date_col_idx]).strip()
            if row_operation_date == normalized_date:
                return True
        
        return False
    except Exception as e:
        print(f"Error checking sales record for date: {e}")
        return False


# ----- 대차신청 (차량 교체) -----
LOANER_SHEET_NAME = "대차차량"


def get_loaner_vehicles():
    """[대차차량] 시트에서 대차가능('O')인 차량 목록 반환"""
    try:
        worksheet = get_worksheet(LOANER_SHEET_NAME)
        all_values = worksheet.get_all_values()
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
        all_values = worksheet.get_all_values()
        if not all_values or len(all_values) < 2:
            return False
        header = [str(h).strip() for h in all_values[0]]
        col_idx = {h: i for i, h in enumerate(header)}
        num_col = col_idx.get('차량번호')
        if num_col is None:
            return False
        vn = str(vehicle_number).strip()
        for i, row in enumerate(all_values[1:], start=2):
            if len(row) <= num_col:
                continue
            if str(row[num_col]).strip() == vn:
                if '대차가능' in col_idx:
                    worksheet.update_cell(i, col_idx['대차가능'] + 1, 'X')
                if '대차신청일' in col_idx:
                    worksheet.update_cell(i, col_idx['대차신청일'] + 1, apply_date_str)
                if '대차사용자' in col_idx:
                    worksheet.update_cell(i, col_idx['대차사용자'] + 1, driver_name or '')
                if '사번' in col_idx:
                    worksheet.update_cell(i, col_idx['사번'] + 1, str(employee_id or ''))
                return True
        return False
    except Exception as e:
        print(f"Error update_loaner_vehicle_on_apply: {e}")
        return False


def update_work_cell_note_report(employee_id, month_sheet_name, day, report_value):
    """해당 월·일의 근무 셀 메모에서 '보고사항'만 갱신 (없으면 추가).
    같은 사번이 야간/주간 등 여러 행일 수 있으므로, 해당일 메모에 '운행시작일시'가 있는 행(실제 근무 시작된 행)을 찾아 그 셀만 수정한다."""
    try:
        worksheet = get_worksheet(month_sheet_name)
        all_values = worksheet.get_all_values()
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
            """메모 내용을 보고사항만 갱신한 새 메모로 덮어쓰기"""
            note_text = note_text or ''
            lines = [ln.strip() for ln in note_text.split('\n') if ln.strip()]
            new_lines = []
            found = False
            for ln in lines:
                if ln.startswith('보고사항:'):
                    new_lines.append(f"보고사항: {report_value}")
                    found = True
                else:
                    new_lines.append(ln)
            if not found:
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


def get_today_replacement_display(employee_id, month_sheet_name, day):
    """오늘(해당일) 근무 셀 메모의 보고사항에서 대차 차량이 있으면 (차량번호, 차종) 반환"""
    try:
        info = get_today_work_start_info(employee_id, month_sheet_name, day)
        if not info:
            return None
        remark = (info.get('vehicle_condition') or '').strip()
        if '(대차)' not in remark:
            return None
        # "33바1810 (대차)" 형태에서 번호 추출
        num = remark.replace('(대차)', '').strip()
        if not num:
            return None
        ws = get_worksheet(LOANER_SHEET_NAME)
        all_values = ws.get_all_values()
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
            if str(row[nc]).strip() == num:
                return (num, str(row[tc]).strip() if tc >= 0 and len(row) > tc else '')
        return (num, '')
    except Exception as e:
        print(f"Error get_today_replacement_display: {e}")
        return None
