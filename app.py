from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, Response, abort
from datetime import datetime, date, timedelta, timezone
from zoneinfo import ZoneInfo
import calendar
from functools import wraps
import os
import config
import threading
import time
import io
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2.service_account import Credentials
from itsdangerous import URLSafeTimedSerializer

# 한국 시간대 설정
KST = ZoneInfo("Asia/Seoul")

def get_kst_now():
    """한국 시간대(Asia/Seoul)의 현재 시간 반환"""
    return datetime.now(KST)

# 간단한 메모리 캐시 클래스 (TTL 지원)
class SimpleCache:
    """TTL(Time To Live)을 지원하는 간단한 메모리 캐시"""
    def __init__(self, default_ttl=60):  # 기본 60초
        self._cache = {}
        self._timestamps = {}
        self._lock = threading.Lock()
        self.default_ttl = default_ttl
    
    def get(self, key):
        """캐시에서 값 가져오기 (만료된 경우 None 반환)"""
        with self._lock:
            if key not in self._cache:
                return None
            
            # TTL 확인
            if time.time() - self._timestamps[key] > self.default_ttl:
                del self._cache[key]
                del self._timestamps[key]
                return None
            
            return self._cache[key]
    
    def set(self, key, value, ttl=None):
        """캐시에 값 저장"""
        with self._lock:
            self._cache[key] = value
            self._timestamps[key] = time.time()
            if ttl:
                # TTL이 지정된 경우 별도 저장 (현재는 default_ttl 사용)
                pass
    
    def clear(self, key=None):
        """캐시 삭제 (key가 None이면 전체 삭제)"""
        with self._lock:
            if key is None:
                self._cache.clear()
                self._timestamps.clear()
            else:
                self._cache.pop(key, None)
                self._timestamps.pop(key, None)
    
    def clear_pattern(self, pattern):
        """패턴에 맞는 키들 삭제 (예: 'work_data:6000:*')"""
        with self._lock:
            keys_to_delete = [k for k in self._cache.keys() if pattern in k]
            for key in keys_to_delete:
                del self._cache[key]
                del self._timestamps[key]

# 전역 캐시 (TTL은 config 환경 변수로 조절 가능 — Sheets 분당 읽기 한도 완화)
work_data_cache = SimpleCache(default_ttl=config.WORK_DATA_CACHE_SECONDS)
sales_data_cache = SimpleCache(default_ttl=config.SALES_SUMMARY_CACHE_SECONDS)
work_start_info_cache = SimpleCache(default_ttl=config.WORK_START_INFO_CACHE_SECONDS)
annual_stats_cache = SimpleCache(default_ttl=config.ANNUAL_STATS_CACHE_SECONDS)
notice_cache = SimpleCache(default_ttl=config.NOTICE_CACHE_SECONDS)
from utils.auth import authenticate_user, change_password, check_default_password
from utils import yearly_stats_snapshot


def invalidate_main_dashboard_stats_caches(employee_id):
    """메인 통계용 메모리 캐시(work/sales/연간) 및 연간 무거운 필드 SQLite 스냅샷 무효화.

    매 요청마다 호출하면 Sheets 읽기가 폭증해 분당 한도(429)에 걸리기 쉽다.
    기본 진입에서는 호출하지 않는다. `ALLOW_MAIN_FRESH_QUERY`(기본 허용)가 켜져 있을 때만
    `/main?fresh=1` 에서 실행된다."""
    if employee_id is None:
        return
    eid = str(employee_id).strip()
    if not eid:
        return
    work_data_cache.clear_pattern(f'work_data:{eid}:')
    sales_data_cache.clear_pattern(f'sales_summary:{eid}:')
    annual_stats_cache.clear_pattern(f'main_yearly:{eid}:')
    yearly_stats_snapshot.invalidate_employee(eid, config.YEARLY_STATS_SNAPSHOT_DB_PATH)


def get_google_api_credentials():
    """Google API 공통 인증 객체."""
    credentials_dict = config.get_google_credentials()
    if credentials_dict:
        return Credentials.from_service_account_info(credentials_dict, scopes=config.SCOPES)
    if not os.path.exists(config.CREDENTIALS_FILE):
        raise FileNotFoundError(
            f"credentials.json 파일을 찾을 수 없습니다. ({config.CREDENTIALS_FILE})"
        )
    return Credentials.from_service_account_file(config.CREDENTIALS_FILE, scopes=config.SCOPES)


def get_drive_service():
    creds = get_google_api_credentials()
    return build('drive', 'v3', credentials=creds, cache_discovery=False)


def parse_notice_filename(raw_name):
    """파일명 형식: 번호_제목_날짜(.pdf).

    제목에 '_' 문자가 포함될 수 있으므로, 첫 토큰=번호·마지막 토큰=날짜(YYYY-MM-DD)·중간 연결=제목.
    """
    base = (raw_name or '').strip()
    if base.lower().endswith('.pdf'):
        base = base[:-4]
    parts = [p.strip() for p in base.split('_') if str(p).strip() != '']
    if len(parts) < 3:
        return None
    date_token = parts[-1]
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', date_token):
        return None
    num_raw = parts[0]
    if not str(num_raw).strip().isdigit():
        return None
    title = '_'.join(parts[1:-1]).strip()
    if not title:
        return None
    try:
        n = int(str(num_raw).strip())
        nr = str(num_raw).strip()
        return {
            'number': n,
            'number_disp': nr.zfill(2) if nr.isdigit() else nr,
            'title': title,
            'posted_date': date_token,
        }
    except Exception:
        return None


def notice_title_for_list(title, max_len=24):
    """목록용 제목 표시 문자열 (max_len 문자 초과 시 말줄임)."""
    t = (title or '').strip()
    if len(t) <= max_len:
        return t
    return t[:max_len] + '...'


def notice_date_yy_mm_dd(iso_yyyy_mm_dd):
    """yyyy-mm-dd → yy-mm-dd (목록용)."""
    d = (iso_yyyy_mm_dd or '').strip()
    if len(d) == 10 and d[4] == '-' and d[7] == '-' and re.match(r'^\d{4}-\d{2}-\d{2}$', d):
        return d[2:]
    return d


def list_notice_pdfs():
    """공지사항 폴더의 PDF 리스트 반환 (번호 내림차순)."""
    folder_id = (config.NOTICE_DRIVE_FOLDER_ID or '').strip()
    if not folder_id:
        return []
    cache_key = f'notice_list:v2:{folder_id}'
    cached = notice_cache.get(cache_key)
    if cached is not None:
        return cached

    svc = get_drive_service()
    query = (
        f"'{folder_id}' in parents and mimeType='application/pdf' and trashed=false"
    )
    # orderBy 불일치로 API가 실패하면 목록 전체가 비는 경우가 있어,
    # 정렬은 Python에서 처리한다.
    resp = svc.files().list(
        q=query,
        fields='files(id,name,mimeType,parents,modifiedTime)',
        pageSize=200,
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute()
    out = []
    for f in resp.get('files', []):
        parsed = parse_notice_filename(f.get('name', ''))
        if not parsed:
            continue
        iso_date = parsed['posted_date']
        full_title = parsed['title']
        out.append({
            'file_id': f['id'],
            'file_name': f.get('name', ''),
            'number': parsed['number'],
            'number_disp': parsed['number_disp'],
            'title': full_title,
            'posted_date': iso_date,
            'title_disp': notice_title_for_list(full_title),
            'posted_date_short': notice_date_yy_mm_dd(iso_date),
        })
    out.sort(key=lambda x: x['number'], reverse=True)
    notice_cache.set(cache_key, out)
    return out


def get_notice_file_meta(file_id):
    """공지 폴더 소속 단일 파일 메타 조회."""
    folder_id = (config.NOTICE_DRIVE_FOLDER_ID or '').strip()
    if not folder_id:
        return None
    svc = get_drive_service()
    meta = svc.files().get(
        fileId=file_id,
        fields='id,name,mimeType,parents,driveId',
        supportsAllDrives=True,
    ).execute()
    if meta.get('mimeType') != 'application/pdf':
        return None
    parents = meta.get('parents') or []
    if folder_id not in parents:
        return None
    parsed = parse_notice_filename(meta.get('name', ''))
    if not parsed:
        return None
    return {
        'file_id': meta['id'],
        'file_name': meta.get('name', ''),
        'number': parsed['number'],
        'number_disp': parsed['number_disp'],
        'title': parsed['title'],
        'posted_date': parsed['posted_date'],
    }
from utils.google_sheets import (
    get_accounts_data,
    get_user_work_data,
    get_all_user_work_data,
    update_work_status,
    get_all_months_data,
    get_all_months_aggregated_data,
    get_user_by_id,
    add_sales_record,
    get_today_work_start_info,
    get_user_sales_summary,
    get_loaner_vehicles,
    update_loaner_vehicle_on_apply,
    reset_loaner_vehicle_on_work_end,
    update_work_cell_note_report,
    get_today_replacement_display,
    parse_replacement_vehicle_from_remark,
    get_user_annual_leave_entitlement,
    sum_approved_leave_days_for_employee,
    get_leave_requests_for_display,
    append_leave_request_row,
    delete_pending_leave_request_row,
)
import pandas as pd

app = Flask(__name__)
app.secret_key = config.SECRET_KEY

_notice_pdf_signer = URLSafeTimedSerializer(app.secret_key, salt='notice-pdf-v1')


def make_notice_pdf_token(file_id):
    """모바일 iframe에서 세션 쿠키가 빠지는 경우 대비, 짧게 유효한 PDF URL용 토큰."""
    return _notice_pdf_signer.dumps({'fid': file_id})


def verify_notice_pdf_token(file_id, token):
    if not token or not file_id:
        return False
    try:
        data = _notice_pdf_signer.loads(token, max_age=60 * 45)
        return isinstance(data, dict) and data.get('fid') == file_id
    except Exception:
        return False

# 정적 파일 캐싱 최적화 및 동적 페이지 캐시 방지
@app.after_request
def after_request(response):
    """응답에 적절한 캐시 제어 헤더 추가"""
    if response.mimetype == 'application/pdf' or request.endpoint == 'notice_file_proxy':
        return response
    # 정적 파일(이미지, CSS, JS)은 캐싱 허용
    if request.endpoint and 'static' in request.endpoint:
        response.headers["Cache-Control"] = "public, max-age=3600"  # 1시간 캐싱
    else:
        # 동적 페이지는 캐시 방지
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

def require_login(f):
    """로그인 필수 데코레이터"""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'employee_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrapper

# 캐싱 래퍼 함수들
def get_all_user_work_data_cached(employee_id, month_sheet_name):
    """캐시를 사용하는 get_all_user_work_data 래퍼"""
    cache_key = f"work_data:{employee_id}:{month_sheet_name}"
    cached_data = work_data_cache.get(cache_key)
    if cached_data is not None:
        return cached_data
    
    # 캐시에 없으면 실제 데이터 가져오기
    data = get_all_user_work_data(employee_id, month_sheet_name)
    if data is not None:
        work_data_cache.set(cache_key, data)
    return data

def get_user_sales_summary_cached(employee_id, month_sheet_name):
    """캐시를 사용하는 get_user_sales_summary 래퍼"""
    cache_key = f"sales_summary:{employee_id}:{month_sheet_name}"
    cached_data = sales_data_cache.get(cache_key)
    if cached_data is not None:
        return cached_data
    
    # 캐시에 없으면 실제 데이터 가져오기
    data = get_user_sales_summary(employee_id, month_sheet_name)
    if data is not None:
        sales_data_cache.set(cache_key, data)
    return data

def has_sales_record_for_date_cached(employee_id, month_sheet_name, operation_date):
    """월 단위 매출 요약 캐시의 operation_dates만 사용 (날짜별 Sheets 재조회 없음)"""
    date_norm = str(operation_date).replace('-', '/')
    bundle = get_user_sales_summary_cached(employee_id, month_sheet_name) or {}
    dates = bundle.get('operation_dates') or set()
    return date_norm in dates

def get_today_work_start_info_cached(employee_id, month_sheet_name, day):
    """캐시를 사용하는 get_today_work_start_info 래퍼 (캘린더 로딩 시 메모/API 반복 호출 감소)"""
    cache_key = f"work_start_info:{employee_id}:{month_sheet_name}:{day}"
    cached = work_start_info_cache.get(cache_key)
    if cached is not None:
        return cached
    data = get_today_work_start_info(employee_id, month_sheet_name, day)
    if data is not None:
        work_start_info_cache.set(cache_key, data)
    return data

def get_work_start_info_with_fallback(employee_id, reference_date):
    """현재 날짜 기준으로 운행시작 정보를 찾고, 없으면 하루 전 정보를 반환"""
    month_name = config.MONTHS[reference_date.month - 1]
    day = reference_date.day
    info = get_today_work_start_info_cached(employee_id, month_name, day)
    
    if info and info.get('work_date'):
        return info, reference_date, month_name, day
    
    previous_date = reference_date - timedelta(days=1)
    previous_month_name = config.MONTHS[previous_date.month - 1]
    previous_day = previous_date.day
    previous_info = get_today_work_start_info_cached(employee_id, previous_month_name, previous_day)
    
    if previous_info and previous_info.get('work_date'):
        return previous_info, previous_date, previous_month_name, previous_day
    
    # 시작 정보를 찾지 못한 경우 기본값 반환
    return info, reference_date, month_name, day


def get_active_work_reference(employee_id, reference_date):
    """진행 중인 운행 기준일(오늘/어제)을 반환.
    - 근무시작 메모(운행시작일시)가 있고
    - 해당 운행일의 매출 기록이 아직 없는
    날짜를 우선 선택한다.
    지각으로 익일 새벽에 시작한 경우에도, 실제 운행일(전날)을 찾기 위해 사용한다.
    """
    candidates = [reference_date, reference_date - timedelta(days=1)]
    for target_date in candidates:
        target_month_name = config.MONTHS[target_date.month - 1]
        target_day = target_date.day
        info = get_today_work_start_info_cached(employee_id, target_month_name, target_day)
        if not (info and info.get('work_date')):
            continue
        operation_date = target_date.strftime('%Y/%m/%d')
        if not has_sales_record_for_date_cached(employee_id, target_month_name, operation_date):
            return info, target_date, target_month_name, target_day

    # 조건에 맞는 진행 중 운행이 없으면 기존 폴백 사용
    return get_work_start_info_with_fallback(employee_id, reference_date)

@app.route('/')
def index():
    """메인 페이지 - 로그인 페이지로 리다이렉트"""
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    """로그인 페이지"""
    if request.method == 'POST':
        employee_id = request.form.get('employee_id', '').strip()
        password = request.form.get('password', '').strip()
        
        if not employee_id or not password:
            flash('사번과 비밀번호를 입력해주세요.', 'error')
            return render_template('login.html')
        
        user, error = authenticate_user(employee_id, password)
        
        if user:
            session['employee_id'] = employee_id
            session['name'] = user.get('name', '')
            
            # 로그인 활동 로깅
            user_name = user.get('name', '')
            print(f"[ACTIVITY] user 로그인 - 사번: {employee_id}, 이름: {user_name}")
            
            # 기본 비밀번호인 경우 비밀번호 변경 페이지로
            if error == "password_change_required":
                return redirect(url_for('change_password_route'))
            
            return redirect(url_for('main_dashboard'))
        else:
            flash(error or '로그인에 실패했습니다.', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """로그아웃"""
    employee_id = session.get('employee_id', '')
    user_name = session.get('name', '')
    
    # 로그아웃 활동 로깅
    if employee_id:
        print(f"[ACTIVITY] user 로그아웃 - 사번: {employee_id}, 이름: {user_name}")
    
    session.clear()
    flash('로그아웃되었습니다.', 'info')
    return redirect(url_for('login'))

@app.route('/change-password', methods=['GET', 'POST'])
@require_login
def change_password_route():
    """비밀번호 변경 페이지"""
    if request.method == 'POST':
        new_password = request.form.get('new_password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()
        
        if not new_password or not confirm_password:
            flash('모든 필드를 입력해주세요.', 'error')
            return render_template('change_password.html')
        
        if new_password != confirm_password:
            flash('비밀번호가 일치하지 않습니다.', 'error')
            return render_template('change_password.html')
        
        employee_id = session.get('employee_id')
        success, message = change_password(employee_id, new_password)
        
        if success:
            flash(message, 'success')
            return redirect(url_for('main_dashboard'))
        else:
            flash(message, 'error')
    
    return render_template('change_password.html')


def _to_int_safe(val):
    try:
        return int(str(val).strip())
    except (ValueError, TypeError):
        return 0


def _get_sheet_metric(record, key):
    """시트 숫자 컬럼 안전 파싱."""
    if not record:
        return 0
    return _to_int_safe(record.get(key, 0))


def _compute_heavy_yearly_totals(employee_id, reference_date):
    """Sheets 호출 부담이 큰 두 지표만 계산해 (결근합, 가해사고 합)."""
    aggregated = get_all_months_aggregated_data(
        employee_id,
        reference_date=reference_date,
        recent_months=12,
        work_data_cache=work_data_cache,
    ) or {}
    annual_absent_days = sum(_get_sheet_metric((v or {}), '결근일') for v in aggregated.values())
    annual_accident_count = 0
    for mn in config.MONTHS:
        annual_accident_count += _to_int_safe(
            (get_user_sales_summary_cached(employee_id, mn) or {}).get('accident_count', 0)
        )
    return annual_absent_days, annual_accident_count


def get_main_yearly_stats(employee_id, reference_date):
    """메인 연간 통계(결근·연차·가해사고) 계산.
    - 무거운 합계는 선택 시 SQLite 스냅샷 TTL 동안 재사용
    - 연차 총액/잔여는 매 요청 시 시트 로직 반영
    - 메모리 캐시(ANNUAL_STATS_CACHE_SECONDS)로 재진입 비용 최소화"""
    cache_key = f'main_yearly:{employee_id}:{reference_date.year}'
    cached = annual_stats_cache.get(cache_key)
    user_rec = get_user_by_id(employee_id)
    entitlement = get_user_annual_leave_entitlement(user_rec)
    used_approved = sum_approved_leave_days_for_employee(employee_id)
    remaining_leave_days = max(0, entitlement - used_approved)
    refresh_leave = {
        'annual_leave_entitlement': entitlement,
        'annual_leave_remaining': remaining_leave_days,
    }
    if cached is not None:
        out = dict(cached)
        out.update(refresh_leave)
        return out

    heavy = None
    if config.YEARLY_STATS_SNAPSHOT_TTL_SEC > 0:
        heavy = yearly_stats_snapshot.get_heavy(
            employee_id,
            reference_date.year,
            config.YEARLY_STATS_SNAPSHOT_TTL_SEC,
            config.YEARLY_STATS_SNAPSHOT_DB_PATH,
        )
    if heavy:
        result = dict(heavy)
        result.update(refresh_leave)
        annual_stats_cache.set(cache_key, result)
        return result

    absent, accidents = _compute_heavy_yearly_totals(employee_id, reference_date)
    if config.YEARLY_STATS_SNAPSHOT_TTL_SEC > 0:
        yearly_stats_snapshot.put_heavy(
            employee_id,
            reference_date.year,
            absent,
            accidents,
            config.YEARLY_STATS_SNAPSHOT_DB_PATH,
        )

    result = {
        'annual_absent_days': absent,
        'annual_accident_count': accidents,
        **refresh_leave,
    }
    annual_stats_cache.set(cache_key, result)
    return result


def refresh_yearly_heavy_snapshot_background(employee_id, reference_date):
    """배경 스레드 등에서 무거운 연간 두 지표만 재계산·스냅샷 저장. 실패만 로깅."""
    eid = str(employee_id or '').strip()
    if not eid:
        return
    try:
        absent, accidents = _compute_heavy_yearly_totals(eid, reference_date)
        if config.YEARLY_STATS_SNAPSHOT_TTL_SEC > 0:
            yearly_stats_snapshot.put_heavy(
                eid,
                reference_date.year,
                absent,
                accidents,
                config.YEARLY_STATS_SNAPSHOT_DB_PATH,
            )
        annual_stats_cache.clear_pattern(f'main_yearly:{eid}:')
    except Exception as ex:
        print(f'refresh_yearly_heavy_snapshot_background({eid}): {ex}')


yearly_bg_rotate_index = 0


def _yearly_stats_background_tick(app_instance):
    global yearly_bg_rotate_index
    try:
        with app_instance.app_context():
            rows = get_accounts_data()
            eids = []
            for r in rows or []:
                eid = str(r.get('employee_id') or '').strip()
                if eid:
                    eids.append(eid)
            if not eids:
                return
            idx = yearly_bg_rotate_index % len(eids)
            yearly_bg_rotate_index = idx + 1
            refresh_yearly_heavy_snapshot_background(eids[idx], get_kst_now().date())
    except Exception as ex:
        print(f'_yearly_stats_background_tick: {ex}')


def start_yearly_stats_background_if_enabled(app_instance):
    if not getattr(config, 'YEARLY_STATS_BG_REFRESH_ENABLED', False):
        return
    if not getattr(config, 'YEARLY_STATS_SNAPSHOT_TTL_SEC', 0):
        print('YEARLY_STATS_BG_REFRESH_ENABLED 무시됨 — YEARLY_STATS_SNAPSHOT_TTL_SEC 가 0 입니다.')
        return

    def loop():
        while True:
            time.sleep(config.YEARLY_STATS_BG_REFRESH_INTERVAL_SEC)
            _yearly_stats_background_tick(app_instance)

    threading.Thread(target=loop, daemon=True, name='yearly-heavy-snapshot-bg').start()

def build_calendar_template_context(employee_id, year, month, include_yearly_stats=False):
    """캘린더 뷰와 메인 대시보드에서 공통으로 사용하는 템플릿 컨텍스트."""
    current_date = get_kst_now()
    month_name = config.MONTHS[month - 1]
    
    # 근무·매출 순차 로딩: 병렬 2동시 호출보다 분당 읽기 스파이크 감소(429 완화)
    all_work_data = get_all_user_work_data_cached(employee_id, month_name)
    sales_summary = get_user_sales_summary_cached(employee_id, month_name) or {}
    
    # 첫 번째 행을 기본 데이터로 사용 (기타 정보 표시용)
    work_data = all_work_data[0] if all_work_data and len(all_work_data) > 0 else None
    
    # 캘린더 생성 (일요일을 첫 번째 요일로 설정)
    calendar.setfirstweekday(calendar.SUNDAY)
    cal = calendar.monthcalendar(year, month)
    
    # 날짜별 근무 상태 매핑 (같은 사번의 모든 행 통합)
    work_status = {}
    record_for_day = {}
    if all_work_data:
        # 상태 우선순위: O(근무) > X(결근) > R(예정일) > H(공휴일) > /(휴무일)
        status_priority = {'O': 5, 'X': 4, 'R': 3, 'H': 2, '/': 1}
        
        for day in range(1, 32):
            day_str = str(day)
            best_status = None
            best_priority = 0
            best_record = None
            
            # 모든 행에서 해당 날짜의 상태 확인
            for record in all_work_data:
                if day_str in record:
                    status_raw = str(record[day_str]).strip()
                    if not status_raw:  # 빈 값은 스킵
                        continue
                    
                    # 대소문자 구분 없이 처리 (O, X, R, H는 대문자로, /는 그대로)
                    status = status_raw.upper() if status_raw.upper() in ['O', 'X', 'R', 'H'] else status_raw
                    
                    # 유효한 상태인 경우 우선순위 확인
                    if status in ['O', 'X', 'R', 'H', '/']:
                        priority = status_priority.get(status, 0)
                        if priority > best_priority:
                            best_priority = priority
                            best_status = status
                            best_record = record
            
            # 가장 높은 우선순위의 상태를 저장
            if best_status:
                work_status[day] = best_status
                record_for_day[day] = best_record
    
    # 근무일·결근일·인정일: 같은 사번 모든 행 합산 (신규 시트명 우선)
    work_days = 0
    absent_days = 0
    approved_days = 0
    if all_work_data:
        for rec in all_work_data:
            work_days += _get_sheet_metric(rec, '근무일')
            absent_days += _get_sheet_metric(rec, '결근일')
            approved_days += _get_sheet_metric(rec, '인정일')
    
    # 오늘 날짜에 배정받은 차량번호와 차종 찾기
    today_vehicle = None
    today_vehicle_type = None
    can_end_work = False
    can_start_work = True
    if year == current_date.year and month == current_date.month:
        today_day = current_date.day
        today_day_str = str(today_day)
        
        # 근무종료 버튼 활성화 조건:
        # 1. 오늘 날짜에 O가 있고, sales_DB_2026에 기록이 없는 경우
        # 2. 어제 날짜에 O가 있고, 어제 날짜에 근무시작 정보가 있으며, sales_DB_2026에 기록이 없는 경우
        #    (지각으로 어제 근무를 시작했지만 아직 종료하지 않은 경우)
        can_end_work = False
        if work_status.get(today_day) == 'O':
            # 오늘 날짜에 O가 있으면 sales_DB_2026에 기록이 있는지 확인
            operation_date = current_date.strftime('%Y/%m/%d')
            if not has_sales_record_for_date_cached(employee_id, month_name, operation_date):
                can_end_work = True
        
        # 어제 날짜 확인
        if not can_end_work:
            yesterday_date = current_date - timedelta(days=1)
            yesterday_month_name = config.MONTHS[yesterday_date.month - 1]
            yesterday_day = yesterday_date.day
            
            # 어제 날짜의 근무 데이터 확인 (같은 월이거나 다른 월)
            yesterday_info = None
            if yesterday_date.year == year and yesterday_date.month == month:
                # 같은 월인 경우
                if work_status.get(yesterday_day) == 'O':
                    yesterday_info = get_today_work_start_info_cached(employee_id, yesterday_month_name, yesterday_day)
            else:
                # 다른 월인 경우 (월이 바뀐 경우)
                yesterday_all_work_data = get_all_user_work_data_cached(employee_id, yesterday_month_name)
                if yesterday_all_work_data:
                    yesterday_day_str = str(yesterday_day)
                    for record in yesterday_all_work_data:
                        if yesterday_day_str in record:
                            status_raw = str(record.get(yesterday_day_str, '')).strip().upper()
                            if status_raw == 'O':
                                yesterday_info = get_today_work_start_info_cached(employee_id, yesterday_month_name, yesterday_day)
                                break
            
            # 어제 날짜에 근무시작 정보가 있고, sales_DB_2026에 기록이 없으면 근무종료 버튼 활성화
            if yesterday_info and yesterday_info.get('work_date'):
                # 운행일은 어제 날짜(근무예정일)를 사용
                operation_date = yesterday_date.strftime('%Y/%m/%d')
                # sales_DB_2026에 해당 날짜의 기록이 없는 경우에만 활성화
                if not has_sales_record_for_date_cached(employee_id, yesterday_month_name, operation_date):
                    can_end_work = True
        
        # 근무시작 버튼 활성화 조건:
        # 1. 오늘 날짜에 O가 없는 경우
        # 2. 오늘 날짜에 O가 있어도 sales_DB_2026에 기록이 있으면 활성화 (오늘 근무가 이미 종료된 경우)
        # 3. 어제 날짜에 진행 중인 근무가 있으면 비활성화 (지각으로 어제 근무를 시작했지만 아직 종료하지 않은 경우)
        if work_status.get(today_day) == 'O':
            # 오늘 날짜에 O가 있으면 sales_DB_2026에 기록이 있는지 확인
            operation_date = current_date.strftime('%Y/%m/%d')
            if has_sales_record_for_date_cached(employee_id, month_name, operation_date):
                # sales_DB_2026에 기록이 있으면 오늘 근무가 종료된 것이므로 근무시작 버튼 활성화
                can_start_work = True
            else:
                # sales_DB_2026에 기록이 없으면 오늘 근무가 진행 중이므로 근무시작 버튼 비활성화
                can_start_work = False
        else:
            # 오늘 날짜에 O가 없으면 근무시작 버튼 활성화
            can_start_work = True
        
        # 어제 날짜에 진행 중인 근무가 있는지 확인
        if can_start_work:
            yesterday_date = current_date - timedelta(days=1)
            yesterday_month_name = config.MONTHS[yesterday_date.month - 1]
            yesterday_day = yesterday_date.day
            
            # 어제 날짜에 근무시작 정보가 있는지 확인
            yesterday_info = None
            if yesterday_date.year == year and yesterday_date.month == month:
                # 같은 월인 경우
                if work_status.get(yesterday_day) == 'O':
                    yesterday_info = get_today_work_start_info_cached(employee_id, yesterday_month_name, yesterday_day)
            else:
                # 다른 월인 경우 (월이 바뀐 경우)
                yesterday_all_work_data = get_all_user_work_data_cached(employee_id, yesterday_month_name)
                if yesterday_all_work_data:
                    yesterday_day_str = str(yesterday_day)
                    for record in yesterday_all_work_data:
                        if yesterday_day_str in record:
                            status_raw = str(record.get(yesterday_day_str, '')).strip().upper()
                            if status_raw == 'O':
                                yesterday_info = get_today_work_start_info_cached(employee_id, yesterday_month_name, yesterday_day)
                                break
            
            # 어제 날짜에 근무시작 정보가 있고, sales_DB_2026에 기록이 없으면 근무시작 버튼 비활성화
            if yesterday_info and yesterday_info.get('work_date'):
                # 운행일은 어제 날짜(근무예정일)를 사용 (실제 시작 시간이 아닌)
                # 어제 날짜에 Google Sheets에 'O'가 기록된 날짜가 운행일이므로
                operation_date = yesterday_date.strftime('%Y/%m/%d')
                # sales_DB_2026에 해당 날짜의 기록이 있는지 확인
                if not has_sales_record_for_date_cached(employee_id, yesterday_month_name, operation_date):
                    can_start_work = False
        
        # 오늘 날짜에 배정된 차량번호와 차종 찾기 (근무 준비 완료 여부와 무관하게)
        day_record = record_for_day.get(today_day)
        if day_record:
            vehicle_num = day_record.get('차량번호', '').strip()
            if vehicle_num:
                today_vehicle = vehicle_num
                today_vehicle_type = day_record.get('차종', '').strip()
        else:
            # 우선순위 기록이 없으면 기존 방식으로 첫 번째 차량번호 사용
            if all_work_data:
                for record in all_work_data:
                    if today_day_str in record:
                        vehicle_num = record.get('차량번호', '').strip()
                        if vehicle_num:
                            today_vehicle = vehicle_num
                            today_vehicle_type = record.get('차종', '').strip()
                            break

    # 이전 달/다음 달 계산
    prev_month = month - 1
    prev_year = year
    if prev_month < 1:
        prev_month = 12
        prev_year -= 1
    
    next_month = month + 1
    next_year = year
    if next_month > 12:
        next_month = 1
        next_year += 1
    
    current_date_only = current_date.date()
    
    # sales_summary는 이미 병렬 로딩에서 조회됨
    total_revenue = sales_summary.get('total_revenue', 0)
    total_fuel_cost = sales_summary.get('total_fuel_cost', 0)
    accident_count = sales_summary.get('accident_count', 0)
    
    # 휴가일: 신규 '휴가' 컬럼(I열) 우선, 없으면 일별 '/' 카운트 폴백
    total_days_in_month = calendar.monthrange(year, month)[1]  # 그 달의 총 일수
    vacation_days = 0
    if all_work_data:
        for rec in all_work_data:
            vacation_days += _to_int_safe(rec.get('휴가', 0))
    if vacation_days == 0:
        vacation_days = sum(1 for day in range(1, total_days_in_month + 1) if work_status.get(day) == '/')

    # 만근 기준: 인정일 기준 (일반월 26일 이상, 2월 24일 이상, 윤년 2월 25일 이상)
    if month == 2:
        full_attendance_threshold = 25 if calendar.isleap(year) else 24
    else:
        full_attendance_threshold = 26
    is_full_attendance = approved_days >= full_attendance_threshold
    
    # 디버깅: 실제 값 출력 (프로덕션에서는 주석 처리)
    # absent_days_count = sum(1 for day in range(1, total_days_in_month + 1) if work_status.get(day) == 'X')  # 결근일 개수 (디버깅용)
    # print(f"DEBUG - 만근 계산: 총일수={total_days_in_month}, 결근일={absent_days_count}, 휴무일={holiday_days_count}, 만근기준={full_attendance_threshold}, 근무일수={work_days}, 만근여부={is_full_attendance}")
    # print(f"DEBUG - work_status에서 X인 날짜: {[day for day in range(1, total_days_in_month + 1) if work_status.get(day) == 'X']}")
    # print(f"DEBUG - work_status에서 /인 날짜: {[day for day in range(1, total_days_in_month + 1) if work_status.get(day) == '/']}")

    # 공지사항 읽지 않은 개수 확인 (아직 구현 전이므로 임시로 False)
    has_unread_notices = False  # TODO: 공지사항 기능 구현 시 실제 값으로 변경
    
    # 근무 중일 때 대차신청 버튼 표시 및 대차 후 차량 표시
    show_replacement_button = not can_start_work  # 근무 중이면 대차신청 버튼
    today_replacement_vehicle = None
    today_replacement_vehicle_type = None
    if year == current_date.year and month == current_date.month and not can_start_work:
        active_info, active_date, active_month_name, active_day = get_active_work_reference(employee_id, current_date)
        rep = get_today_replacement_display(employee_id, active_month_name, active_day, work_start_info=active_info)
        if rep:
            today_replacement_vehicle, today_replacement_vehicle_type = rep
    
    ctx = {
        'calendar': cal,
        'year': year,
        'month': month,
        'month_name': month_name,
        'work_status': work_status,
        'current_date': current_date_only,
        'work_data': work_data,
        'work_days': work_days,
        'absent_days': absent_days,
        'total_revenue': total_revenue,
        'total_fuel_cost': total_fuel_cost,
        'holiday_days_count': vacation_days,
        'accident_count': accident_count,
        'approved_days': approved_days,
        'prev_year': prev_year,
        'prev_month': prev_month,
        'next_year': next_year,
        'next_month': next_month,
        'can_end_work': can_end_work,
        'can_start_work': can_start_work,
        'today_vehicle': today_vehicle,
        'today_vehicle_type': today_vehicle_type,
        'today_replacement_vehicle': today_replacement_vehicle,
        'today_replacement_vehicle_type': today_replacement_vehicle_type,
        'show_replacement_button': show_replacement_button,
        'is_full_attendance': is_full_attendance,
        'has_unread_notices': has_unread_notices,
    }

    if include_yearly_stats:
        yearly = get_main_yearly_stats(employee_id, current_date.date())
        ctx.update(yearly)

    return ctx


@app.route('/calendar')
@require_login
def calendar_view():
    """캘린더 뷰 - 근무일정"""
    employee_id = session.get('employee_id')
    current_date = get_kst_now()
    year_param = request.args.get('year', type=int)
    month_param = request.args.get('month', type=int)
    if year_param and month_param:
        year = year_param
        month = month_param
        if month < 1:
            month = 12
            year -= 1
        elif month > 12:
            month = 1
            year += 1
    else:
        year = current_date.year
        month = current_date.month
    ctx = build_calendar_template_context(employee_id, year, month)
    return render_template('calendar.html', **ctx)


@app.route('/main')
@require_login
def main_dashboard():
    """메인 대시보드 (로그인 후 진입 화면)"""
    employee_id = session.get('employee_id')
    # 시트 수정 직후: /main?fresh=1 (Sheets 재조회·429 증가) — 필요할 때만, 운영에서 막으면 ALLOW_MAIN_FRESH_QUERY=0
    if request.args.get('fresh') == '1':
        if getattr(config, 'ALLOW_MAIN_FRESH_QUERY', True):
            invalidate_main_dashboard_stats_caches(employee_id)
        else:
            flash(
                '`/main?fresh=1`(캐시 강제 갱신)은 비활성화되어 있습니다. '
                'ALLOW_MAIN_FRESH_QUERY=1(또는 환경 변수 제거) 후 재시작하세요.',
                'warning',
            )
    cd = get_kst_now()
    # 연간 통계는 별도 API로 지연 로드 → 로그인 직후 분당 Sheets 읽기 폭증·429 완화
    ctx = build_calendar_template_context(employee_id, cd.year, cd.month, include_yearly_stats=False)
    ctx['yearly_stats_deferred'] = True
    return render_template('main.html', **ctx)


@app.route('/api/main-yearly-stats')
@require_login
def api_main_yearly_stats():
    """메인 '연간 근태 현황' 블록용 JSON (첫 화면 이후 로드)."""
    employee_id = session.get('employee_id')
    if not employee_id:
        return jsonify({'ok': False, 'error': 'no_session'}), 401
    try:
        data = get_main_yearly_stats(employee_id, get_kst_now().date())
        payload = {
            'ok': True,
            'annual_absent_days': data.get('annual_absent_days', 0),
            'annual_accident_count': data.get('annual_accident_count', 0),
            'annual_leave_entitlement': data.get('annual_leave_entitlement', 0),
            'annual_leave_remaining': data.get('annual_leave_remaining', 0),
        }
        return jsonify(payload)
    except Exception as e:
        print(f'api_main_yearly_stats: {e}')
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/notice')
@require_login
def notice_list():
    """공지사항 PDF 목록."""
    if request.args.get('fresh') == '1':
        notice_cache.clear_pattern('notice_list:')
    listed_ok = False
    try:
        notices = list_notice_pdfs()
        listed_ok = True
    except HttpError as e:
        notices = []
        body = getattr(e, 'content', None) or b''
        print(
            'Error list_notice_pdfs HttpError %s: %s'
            % (
                getattr(e.resp, 'status', ''),
                body.decode('utf-8', errors='replace')[:1200],
            )
        )
        import traceback

        traceback.print_exc()
        if getattr(e.resp, 'status', None) == 404:
            flash(
                '공지 폴더를 Drive에서 찾지 못했습니다. '
                '`NOTICE_DRIVE_FOLDER_ID`(또는 환경 변수)가 해당 [공지사항] 폴더 브라우저 주소의 '
                '`/folders/` 뒤 ID와 문자 하나까지 동일하게 맞았는지 확인해 주세요. '
                '(Sheets는 되는데 공지만 안 되면 ID 오타 가능성이 큽니다.)',
                'error',
            )
        else:
            flash(
                'Drive에서 공지 목록을 불러오지 못했습니다. credentials·Drive API 활성화·쿼터를 확인해 주세요.',
                'error',
            )
    except Exception as e:
        notices = []
        print(f'Error list_notice_pdfs: {e}')
        import traceback

        traceback.print_exc()
        flash(
            'Drive에서 공지 목록을 불러오지 못했습니다. credentials·쿼터·폴더 권한을 확인해 주세요.',
            'error',
        )

    # 목록이 비었을 때만 안내 (API 오류로 이미 error 플래시를 띄운 경우는 제외)
    if not notices and listed_ok:
        flash(
            '공지 PDF가 표시되지 않으면 다음을 확인해 주세요. '
            '① 폴더 ID(NOTICE_DRIVE_FOLDER_ID). '
            '② 서비스 계정 이메일에 해당 [공지사항] 폴더 편집자 공유. '
            '③ 파일명 형식: 번호_제목_YYYY-MM-DD.pdf',
            'info',
        )

    return render_template('notice.html', notices=notices)


@app.route('/notice/<file_id>')
@require_login
def notice_view(file_id):
    """공지사항 상세 (PDF 뷰어)."""
    try:
        notice = get_notice_file_meta(file_id)
    except Exception:
        notice = None
    if not notice:
        flash('공지 파일을 찾을 수 없습니다.', 'error')
        return redirect(url_for('notice_list'))
    pdf_token = make_notice_pdf_token(file_id)
    return render_template(
        'notice_view.html',
        notice=notice,
        pdf_token=pdf_token,
    )


@app.route('/notice/file/<file_id>')
def notice_file_proxy(file_id):
    """Google Drive PDF를 스트리밍. iframe용 ?t 토큰 또는 로그인 세션 필요."""
    if not verify_notice_pdf_token(file_id, request.args.get('t')) and (
        'employee_id' not in session
    ):
        return redirect(url_for('login'))
    try:
        notice = get_notice_file_meta(file_id)
        if not notice:
            abort(404)
        svc = get_drive_service()
        req = svc.files().get_media(fileId=file_id, supportsAllDrives=True)
        stream = io.BytesIO()
        downloader = MediaIoBaseDownload(stream, req)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        pdf_bytes = stream.getvalue()
        raw_fn = (notice.get('file_name') or 'notice.pdf').replace('"', '_')
        # 헤더는 latin-1 제한으로 filename="..." 는 ASCII 고정 (원본 이름은 RFC 5987 filename* 에만 인코딩).
        pct_name = quote(raw_fn, safe='')
        cd = 'inline; filename="notice.pdf"; filename*=UTF-8\'\'%s' % pct_name
        ln = len(pdf_bytes)
        return Response(
            pdf_bytes,
            mimetype='application/pdf',
            headers={
                'Content-Disposition': cd,
                'Content-Length': str(ln),
                'Cache-Control': 'private, max-age=60',
            },
        )
    except Exception:
        abort(404)


@app.route('/leave-request')
@require_login
def leave_request():
    """휴가신청 목록 및 잔여 연차 표시."""
    employee_id = session.get('employee_id')
    user_rec = get_user_by_id(employee_id)
    entitlement = get_user_annual_leave_entitlement(user_rec)
    used_approved = sum_approved_leave_days_for_employee(employee_id)
    remaining = max(0, entitlement - used_approved)
    leave_rows = get_leave_requests_for_display(employee_id)
    return render_template(
        'leave_request.html',
        entitlement=entitlement,
        remaining_leave_days=remaining,
        used_approved_days=used_approved,
        leave_rows=leave_rows,
    )


@app.route('/leave-request/new', methods=['GET', 'POST'])
@require_login
def leave_request_new():
    """휴가신청 작성 폼."""
    employee_id = session.get('employee_id')
    name = (session.get('name') or '').strip()
    current_date = get_kst_now()
    today_slash = current_date.strftime('%Y/%m/%d')
    today_iso = current_date.strftime('%Y-%m-%d')
    user_rec = get_user_by_id(employee_id)

    if request.method == 'POST':
        start_iso = (request.form.get('start_date') or '').strip()
        end_iso = (request.form.get('end_date') or '').strip()
        reason = (request.form.get('reason') or '').strip()
        if not start_iso or not end_iso:
            flash('휴가 시작일과 종료일을 선택해주세요.', 'error')
            return redirect(url_for('leave_request_new'))
        if not reason:
            flash('사유를 입력해주세요.', 'error')
            return redirect(url_for('leave_request_new'))
        try:
            start_dt = datetime.strptime(start_iso[:10], '%Y-%m-%d').date()
            end_dt = datetime.strptime(end_iso[:10], '%Y-%m-%d').date()
        except ValueError:
            flash('날짜 형식이 올바르지 않습니다.', 'error')
            return redirect(url_for('leave_request_new'))
        if end_dt < start_dt:
            flash('종료일은 시작일 이후여야 합니다.', 'error')
            return redirect(url_for('leave_request_new'))
        duration_days = (end_dt - start_dt).days + 1
        start_slash = start_dt.strftime('%Y/%m/%d')
        end_slash = end_dt.strftime('%Y/%m/%d')
        account_name = (user_rec.get('name') or '').strip() if user_rec else ''
        if account_name and name and account_name != name:
            flash('로그인 정보와 계정 이름이 일치하지 않습니다.', 'error')
            return redirect(url_for('leave_request_new'))
        display_name = account_name or name
        if append_leave_request_row(
            today_slash,
            employee_id,
            display_name,
            start_slash,
            end_slash,
            duration_days,
            reason,
        ):
            flash('휴가 신청이 접수되었습니다.', 'success')
            return redirect(url_for('leave_request'))
        flash('휴가 신청 저장에 실패했습니다. 잠시 후 다시 시도해주세요.', 'error')
        return redirect(url_for('leave_request_new'))

    return render_template(
        'leave_request_form.html',
        apply_date_display=today_slash,
        apply_date_iso=today_iso,
        user_name=(user_rec.get('name') or '').strip() or name,
        employee_id=employee_id,
        default_start_iso=today_iso,
        default_end_iso=today_iso,
    )


@app.route('/leave-request/cancel', methods=['POST'])
@require_login
def leave_request_cancel():
    """대기 상태 휴가신청 1건 취소(행 삭제)."""
    employee_id = str(session.get('employee_id') or '').strip()
    session_name = (session.get('name') or '').strip()

    apply_date = (request.form.get('apply_date') or '').strip()
    start_date = (request.form.get('start_date') or '').strip()
    end_date = (request.form.get('end_date') or '').strip()
    row_name = (request.form.get('name') or '').strip()

    if not apply_date or not start_date or not end_date:
        flash('취소할 휴가 정보가 올바르지 않습니다.', 'error')
        return redirect(url_for('leave_request'))

    if session_name and row_name and session_name != row_name:
        flash('본인 신청건만 취소할 수 있습니다.', 'error')
        return redirect(url_for('leave_request'))

    if delete_pending_leave_request_row(employee_id, row_name or session_name, apply_date, start_date, end_date):
        flash('휴가 신청이 취소되었습니다.', 'success')
    else:
        flash('대기 상태의 신청건을 찾지 못했습니다.', 'error')
    return redirect(url_for('leave_request'))


@app.route('/vehicle-replacement-apply', methods=['GET', 'POST'])
@require_login
def vehicle_replacement_apply():
    """대차신청 - 근무 중 차량 교체 신청"""
    employee_id = session.get('employee_id')
    driver_name = session.get('name', '') or ''
    current_date = get_kst_now()
    month_name = config.MONTHS[current_date.month - 1]
    
    if request.method == 'POST':
        vehicle_number = (request.form.get('vehicle_number') or '').strip()
        if not vehicle_number:
            flash('대차할 차량을 선택해주세요.', 'error')
            return redirect(url_for('vehicle_replacement_apply'))
        apply_date_str = current_date.strftime('%Y/%m/%d')
        if update_loaner_vehicle_on_apply(vehicle_number, employee_id, driver_name, apply_date_str):
            report_value = f"{vehicle_number} (대차)"
            active_info, active_date, active_month_name, active_day = get_active_work_reference(employee_id, current_date)
            if update_work_cell_note_report(employee_id, active_month_name, active_day, report_value):
                work_data_cache.clear_pattern(f"work_data:{employee_id}:*")
                work_start_info_cache.clear_pattern(f"work_start_info:{employee_id}:")
                flash('대차신청이 완료되었습니다.', 'success')
            else:
                flash('보고사항 반영에 실패했습니다. 관리자에게 문의하세요.', 'error')
        else:
            flash('대차 신청 처리에 실패했습니다. 다시 시도해주세요.', 'error')
        return redirect(url_for('main_dashboard'))
    
    vehicles = get_loaner_vehicles()
    return render_template('vehicle_replacement_apply.html',
                          vehicles=vehicles,
                          year=current_date.year,
                          month=current_date.month)


@app.route('/work-start', methods=['GET', 'POST'])
@require_login
def work_start():
    """근무준비 페이지"""
    employee_id = session.get('employee_id')
    current_date = get_kst_now()
    year = current_date.year
    month = current_date.month
    day = current_date.day
    
    month_name = config.MONTHS[month - 1]
    
    if request.method == 'POST':
        selected_date = request.form.get('selected_date')
        if selected_date:
            year, month, day = map(int, selected_date.split('-'))
            month_name = config.MONTHS[month - 1]
        else:
            # selected_date가 없으면 현재 날짜 사용
            year = current_date.year
            month = current_date.month
            day = current_date.day
            month_name = config.MONTHS[month - 1]
        
        # 폼 데이터 가져오기
        vehicle_number = request.form.get('vehicle_number', '')  # hidden input에서 가져옴
        work_type = request.form.get('work_type', '')
        # TODO(restore): 임시 비활성화 - work_start 폼에서 차량상태/보고사항 입력 미사용
        # vehicle_condition = request.form.get('vehicle_condition', '')
        # special_notes = request.form.get('special_notes', '')
        
        # 날짜/시간 포맷팅 (현재 시간 포함)
        work_datetime = current_date.strftime('%Y/%m/%d %H:%M:%S')
        
        # 근무 상세 정보 구성
        work_details = {
            'vehicle_number': vehicle_number,
            'work_date': work_datetime,
            'work_type': work_type,
            # TODO(restore): 임시 비활성화 - 메모 항목 전달 중단
            # 'vehicle_condition': vehicle_condition,
            # 'special_notes': special_notes
        }
        
        # 근무 상태 업데이트 및 메모 추가 (선택한 차량번호와 근무유형 전달)
        success = update_work_status(employee_id, day, month_name, 'O', work_details=work_details, vehicle_number=vehicle_number, work_type=work_type)
        
        if success:
            # 캐시 무효화 (근무 데이터 업데이트됨)
            work_data_cache.clear_pattern(f"work_data:{employee_id}:{month_name}")
            work_start_info_cache.clear_pattern(f"work_start_info:{employee_id}:")
            
            # 근무준비 완료 활동 로깅
            user_info = get_user_by_id(employee_id)
            user_name = user_info.get('name', '') if user_info else ''
            print(f"[ACTIVITY] user 근무준비 완료 - 사번: {employee_id}, 이름: {user_name}, 날짜: {year}/{month}/{day}, 차량: {vehicle_number}")
            
            # 근무응원 페이지로 리다이렉트
            return redirect(url_for('work_thanks'))
        else:
            flash('근무시작 기록에 실패했습니다.', 'error')
    
    # 사용자 정보 가져오기
    user = get_user_by_id(employee_id)
    
    # 같은 사번의 모든 행에서 데이터 가져오기 (캐시 사용)
    all_work_data = get_all_user_work_data_cached(employee_id, month_name)
    
    # 선택된 날짜에 배정된 차량번호와 차종 찾기
    assigned_vehicle = None
    assigned_vehicle_type = None
    day_str = str(day)
    if all_work_data:
        # 상태 우선순위: O(근무) > X(결근) > R(예정일) > H(공휴일) > /(휴무일)
        status_priority = {'O': 5, 'X': 4, 'R': 3, 'H': 2, '/': 1}
        best_priority = 0
        best_record = None
        
        for record in all_work_data:
            if day_str in record:
                status_raw = str(record.get(day_str, '')).strip()
                if not status_raw:  # 빈 값은 스킵
                    continue
                
                # 대소문자 구분 없이 처리 (O, X, R, H는 대문자로, /는 그대로)
                status = status_raw.upper() if status_raw.upper() in ['O', 'X', 'R', 'H'] else status_raw
                
                # 유효한 상태인 경우 우선순위 확인
                if status in ['O', 'X', 'R', 'H', '/']:
                    priority = status_priority.get(status, 0)
                    if priority > best_priority:
                        best_priority = priority
                        best_record = record
        
        # 가장 높은 우선순위의 상태를 가진 행에서 차량번호와 근무유형 가져오기
        if best_record:
            vehicle_num = best_record.get('차량번호', '').strip()
            if vehicle_num:
                assigned_vehicle = vehicle_num
                assigned_vehicle_type = best_record.get('차종', '').strip()
    
    # 첫 번째 행을 기본 데이터로 사용 (기타 정보 표시용)
    work_data = all_work_data[0] if all_work_data and len(all_work_data) > 0 else None
    
    # 해당 날짜에 배정된 차량의 근무유형 가져오기 (기본값: 주간)
    work_type_from_sheet = '주간'  # 기본값
    if best_record and best_record.get('근무유형'):
        work_type_from_sheet = str(best_record.get('근무유형', '주간')).strip()
        # 근무유형이 '일차'인 경우 '일차'로 설정
        if work_type_from_sheet not in ['주간', '야간', '일차', '교대', '리스']:
            work_type_from_sheet = '주간'  # 유효하지 않은 값이면 기본값 사용
    elif work_data and work_data.get('근무유형'):
        # best_record가 없으면 첫 번째 행에서 가져오기
        work_type_from_sheet = str(work_data.get('근무유형', '주간')).strip()
        if work_type_from_sheet not in ['주간', '야간', '일차', '교대', '리스']:
            work_type_from_sheet = '주간'  # 유효하지 않은 값이면 기본값 사용
    
    # 현재 날짜/시간 포맷팅 (운행시작일시 표시용)
    work_datetime_display = current_date.strftime('%Y / %m / %d %H:%M:%S')
    
    return render_template('work_start.html',
                         employee_id=employee_id,
                         user=user,
                         year=year,
                         month=month,
                         day=day,
                         current_date=current_date.date(),
                         work_data=work_data,
                         assigned_vehicle=assigned_vehicle,
                         assigned_vehicle_type=assigned_vehicle_type,
                         work_type_from_sheet=work_type_from_sheet,
                         work_datetime_display=work_datetime_display)

@app.route('/work-thanks')
@require_login
def work_thanks():
    """근무응원 페이지"""
    now = get_kst_now()
    return render_template('work_thanks.html', year=now.year, month=now.month)

@app.route('/work-end', methods=['GET', 'POST'])
@require_login
def work_end():
    """근무종료 1단계 페이지"""
    employee_id = session.get('employee_id')
    current_date = get_kst_now()
    year = current_date.year
    month = current_date.month
    day = current_date.day
    month_name = config.MONTHS[month - 1]
    
    if request.method == 'POST':
        # 1단계 폼 데이터 가져오기
        vehicle_number = request.form.get('vehicle_number', '')
        work_type = request.form.get('work_type', '')
        accident_status = request.form.get('accident_status', '')
        special_notes = request.form.get('special_notes', '')
        
        # 사고유무 필수 검증
        if not accident_status:
            flash('사고유무를 선택해주세요.', 'error')
            return redirect(url_for('work_end'))
        
        # 세션에 1단계 데이터 저장
        session['work_end_step1'] = {
            'vehicle_number': vehicle_number,
            'work_type': work_type,
            'accident_status': accident_status,
            'special_notes': special_notes
        }
        
        # 2단계로 이동
        return redirect(url_for('work_end_step2'))
    
    # 오늘 날짜의 근무 시작 정보 가져오기 (필요 시 하루 전 데이터 사용)
    today_info, lookup_date, lookup_month_name, lookup_day = get_work_start_info_with_fallback(employee_id, current_date)
    
    # 사용자 정보 가져오기
    user = get_user_by_id(employee_id)
    
    # 같은 사번의 모든 행에서 데이터 가져오기 (캐시 사용)
    all_work_data = get_all_user_work_data_cached(employee_id, lookup_month_name)
    
    # 선택된 날짜에 배정된 차량번호와 차종 찾기
    assigned_vehicle = None
    assigned_vehicle_type = None
    day_str = str(lookup_day)
    if all_work_data:
        # 상태 우선순위: O(근무) > X(결근) > R(예정일) > H(공휴일) > /(휴무일)
        status_priority = {'O': 5, 'X': 4, 'R': 3, 'H': 2, '/': 1}
        best_priority = 0
        best_record = None
        
        for record in all_work_data:
            if day_str in record:
                status_raw = str(record.get(day_str, '')).strip()
                if not status_raw:  # 빈 값은 스킵
                    continue
                
                # 대소문자 구분 없이 처리 (O, X, R, H는 대문자로, /는 그대로)
                status = status_raw.upper() if status_raw.upper() in ['O', 'X', 'R', 'H'] else status_raw
                
                # 유효한 상태인 경우 우선순위 확인
                if status in ['O', 'X', 'R', 'H', '/']:
                    priority = status_priority.get(status, 0)
                    if priority > best_priority:
                        best_priority = priority
                        best_record = record
        
        # 가장 높은 우선순위의 상태를 가진 행에서 차량번호와 근무유형 가져오기
        if best_record:
            vehicle_num = best_record.get('차량번호', '').strip()
            if vehicle_num:
                assigned_vehicle = vehicle_num
                assigned_vehicle_type = best_record.get('차종', '').strip()
    
    # 첫 번째 행을 기본 데이터로 사용 (기타 정보 표시용)
    work_data = all_work_data[0] if all_work_data and len(all_work_data) > 0 else None
    
    # 해당 날짜에 배정된 차량의 근무유형 가져오기 (기본값: 주간)
    work_type_from_sheet = '주간'  # 기본값
    if best_record and best_record.get('근무유형'):
        work_type_from_sheet = str(best_record.get('근무유형', '주간')).strip()
        # 근무유형이 '일차'인 경우 '일차'로 설정
        if work_type_from_sheet not in ['주간', '야간', '일차', '교대', '리스']:
            work_type_from_sheet = '주간'  # 유효하지 않은 값이면 기본값 사용
    elif work_data and work_data.get('근무유형'):
        # best_record가 없으면 첫 번째 행에서 가져오기
        work_type_from_sheet = str(work_data.get('근무유형', '주간')).strip()
        if work_type_from_sheet not in ['주간', '야간', '일차', '교대', '리스']:
            work_type_from_sheet = '주간'  # 유효하지 않은 값이면 기본값 사용
    
    # 오늘 날짜 표시
    work_date_display = lookup_date.strftime('%Y / %m / %d')
    
    # 기본값 설정
    default_work_type = work_type_from_sheet
    # 해당일 근무 메모의 보고사항(대차 등)을 텍스트 박스 기본값으로 연결
    default_special_notes = (today_info.get('special_notes') or '').strip() if today_info else ''
    
    return render_template('work_end_step1.html',
                         employee_id=employee_id,
                         user=user,
                         year=year,
                         month=month,
                         day=day,
                         work_date_display=work_date_display,
                         assigned_vehicle=assigned_vehicle,
                         assigned_vehicle_type=assigned_vehicle_type,
                         work_type_from_sheet=work_type_from_sheet,
                         default_special_notes=default_special_notes)

@app.route('/work-end-step2', methods=['GET', 'POST'])
@require_login
def work_end_step2():
    """근무종료 2단계 페이지"""
    employee_id = session.get('employee_id')
    current_date = get_kst_now()
    month_name = config.MONTHS[current_date.month - 1]
    
    # 1단계 데이터 확인
    step1_data = session.get('work_end_step1')
    if not step1_data:
        flash('먼저 1단계를 완료해주세요.', 'error')
        return redirect(url_for('work_end'))
    
    # 운행시작 정보 조회 (필요 시 하루 전 데이터 사용) - 운행일 표시용
    work_start_info, lookup_date, lookup_month_name, lookup_day = get_work_start_info_with_fallback(employee_id, current_date)
    
    # 운행일은 lookup_date 사용 (근무준비를 시작한 날짜)
    year = lookup_date.year
    month = lookup_date.month
    day = lookup_date.day
    
    if request.method == 'POST':
        # 2단계 폼 데이터 가져오기
        cash_fare = request.form.get('cash_fare', '0')
        card_fare = request.form.get('card_fare', '0')
        toll_fee = request.form.get('toll_fee', '0')
        fuel_usage = request.form.get('fuel_usage', '0')
        fuel_cost = request.form.get('fuel_cost', '0')
        
        # 숫자 변환 (쉼표 제거)
        try:
            cash_fare = int(str(cash_fare).replace(',', '')) if cash_fare else 0
            card_fare = int(str(card_fare).replace(',', '')) if card_fare else 0
            toll_fee = int(str(toll_fee).replace(',', '')) if toll_fee else 0
            fuel_usage = int(str(fuel_usage).replace(',', '')) if fuel_usage else 0
            fuel_cost = int(str(fuel_cost).replace(',', '')) if fuel_cost else 0
        except (ValueError, TypeError):
            cash_fare = 0
            card_fare = 0
            toll_fee = 0
            fuel_usage = 0
            fuel_cost = 0
        
        # 사용자 정보 가져오기 및 운행종료일시 기록
        user = get_user_by_id(employee_id)
        work_end_datetime = current_date.strftime('%Y/%m/%d %H:%M:%S')
        
        # GET 단계에서 조회한 운행시작 정보를 재사용하여 중복 API 호출 제거
        start_lookup_date = lookup_date
        start_month_name = lookup_month_name
        start_day = lookup_day
        
        # 운행일 결정: lookup_date 사용 (근무예정일, 즉 Google Sheets에 'O'가 기록된 날짜)
        operation_date = start_lookup_date.strftime('%Y/%m/%d')
        
        # 운행시작일시는 work_start_info에서 가져오기 (근무시간 계산용)
        work_start_datetime = None
        if work_start_info and work_start_info.get('work_date'):
            work_start_datetime = work_start_info.get('work_date')
        
        # sales_DB_2026에 저장할 데이터 구성
        sales_data = {
            '운행일': operation_date,  # 운행시작일시의 날짜 사용
            '근무유형': step1_data.get('work_type', ''),
            '사번': str(employee_id),
            '운전기사': user.get('name', '') if user else '',
            '차량번호': step1_data.get('vehicle_number', ''),
            '차종': '',  # 차량번호에서 차종 찾기
            '사고유무': step1_data.get('accident_status', ''),  # 사고유무 필드 추가
            '현금운임': cash_fare,
            '카드운임': card_fare,
            '통행료': toll_fee,
            '연료비': fuel_cost,
            '연료충전량': fuel_usage,
            '보고사항': step1_data.get('special_notes', '')
        }
        
        # 근무시간(분) 추가 (나중에 계산된 값으로 업데이트됨)
        work_duration_minutes = None
        
        # 차종 찾기 (근무 시작 정보가 있는 월 기준, 캐시 사용)
        all_work_data = get_all_user_work_data_cached(employee_id, start_month_name)
        if all_work_data:
            for record in all_work_data:
                if record.get('차량번호', '').strip() == step1_data.get('vehicle_number', ''):
                    sales_data['차종'] = record.get('차종', '').strip()
                    break
        
        work_duration = None
        
        if work_start_datetime:
            
            # 근무 시간 계산 (운행시작일시 ~ 운행종료일시)
            try:
                # 운행시작일시 파싱 (형식: "2025/11/12 15:07:02")
                start_str = work_start_datetime
                end_str = work_end_datetime
                
                # datetime 객체로 변환
                start_dt = datetime.strptime(start_str, '%Y/%m/%d %H:%M:%S')
                end_dt = datetime.strptime(end_str, '%Y/%m/%d %H:%M:%S')
                
                # 시간 차이 계산
                duration = end_dt - start_dt
                total_seconds = int(duration.total_seconds())
                total_minutes = total_seconds // 60  # 분 단위로 계산
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                
                work_duration = f"{hours}시간 {minutes}분"
                work_duration_minutes = total_minutes  # 분 단위 값
                # sales_data에 근무시간(분) 추가
                sales_data['근무시간(분)'] = work_duration_minutes
            except Exception as e:
                print(f"Error calculating work duration: {e}")
                work_duration = None
                work_duration_minutes = None
        
        # sales_DB_2026에 데이터 추가 (운행시작일시와 근무시간 포함)
        note_lines = []
        if work_start_datetime:
            note_lines.append(f"운행시작일시: {work_start_datetime}")
        note_lines.append(f"운행종료일시: {work_end_datetime}")
        if work_duration:
            note_lines.append(f"근무시간: {work_duration}")
        
        note_text = "\n".join(note_lines)
        
        # 사고유무는 sales_data에 포함되어 있으므로 별도 메모 불필요
        success = add_sales_record(month_name, sales_data, note_text=note_text)
        
        if success:
            # 캐시 무효화 (매출 데이터 업데이트됨)
            sales_data_cache.clear_pattern(f"sales_summary:{employee_id}:{month_name}")
            
            # 대차 차량으로 근무 종료 시 [대차차량] 시트는 '대차' 보고가 있는 차량번호 행을 초기화해야 함
            # (배정 차량 번호는 본인 행 33바1800 등이므로, 대차 시트 행 33바1812와 불일치하면 반납이 누락됨)
            assigned_vn = (step1_data.get('vehicle_number') or '').strip()
            notes_text = (step1_data.get('special_notes') or '').strip()
            loaner_vn = parse_replacement_vehicle_from_remark(notes_text)
            if not loaner_vn and work_start_info:
                loaner_vn = parse_replacement_vehicle_from_remark(
                    (work_start_info.get('special_notes') or work_start_info.get('vehicle_condition') or '')
                )
            vehicle_for_loaner_reset = (loaner_vn or assigned_vn).strip()
            if vehicle_for_loaner_reset:
                reset_loaner_vehicle_on_work_end(vehicle_for_loaner_reset, employee_id)
            
            # 근무종료 완료 활동 로깅
            user_name = user.get('name', '') if user else ''
            log_loaner = f", 대차반납차량: {loaner_vn}" if loaner_vn else ""
            print(f"[ACTIVITY] user 근무종료 완료 - 사번: {employee_id}, 이름: {user_name}, 날짜: {year}/{month}/{day}, 차량: {assigned_vn}{log_loaner}")
            
            # 세션에서 1단계 데이터 제거
            session.pop('work_end_step1', None)
            # 감사 페이지로 이동
            return redirect(url_for('work_end_thanks'))
        else:
            flash('근무종료 기록에 실패했습니다.', 'error')
    
    # 사용자 정보 가져오기
    user = get_user_by_id(employee_id)
    
    return render_template('work_end_step2.html',
                         employee_id=employee_id,
                         user=user,
                         year=year,
                         month=month,
                         day=day,
                         step1_data=step1_data)

@app.route('/work-end-thanks')
@require_login
def work_end_thanks():
    """근무종료 감사 페이지"""
    now = get_kst_now()
    return render_template('work_end_thanks.html', year=now.year, month=now.month)

@app.route('/work-history')
@require_login
def work_history():
    """월별 근무이력 시각화"""
    employee_id = session.get('employee_id')
    
    # 월별 근무 합산: 스프레드시트 1회 열기 + 월 병렬 조회 + work_data 캐시 연동 + 조회 월 수 제한(설정)
    all_data = get_all_months_aggregated_data(
        employee_id,
        reference_date=get_kst_now().date(),
        recent_months=config.WORK_HISTORY_RECENT_MONTHS,
        work_data_cache=work_data_cache,
    )
    
    if not all_data:
        flash('근무 이력 데이터가 없습니다.', 'info')
        return render_template('work_history.html', chart_data=None)
    
    # 데이터프레임 생성
    months = []
    work_days = []
    absent_days = []
    scheduled_days = []
    holiday_days = []
    
    for month in config.MONTHS:
        if month in all_data:
            data = all_data[month]
            months.append(month)
            # 숫자로 변환 (문자열일 수 있음)
            work_days_val = _get_sheet_metric(data, '근무일')
            absent_days_val = _get_sheet_metric(data, '결근일')
            try:
                work_days.append(int(work_days_val) if work_days_val else 0)
                absent_days.append(int(absent_days_val) if absent_days_val else 0)
            except (ValueError, TypeError):
                work_days.append(0)
                absent_days.append(0)
            
            # R(예정일)과 휴가 개수 계산
            scheduled_count = 0
            holiday_count = _to_int_safe(data.get('휴가', 0))
            for day in range(1, 32):
                day_str = str(day)
                if day_str in data:
                    status_raw = str(data[day_str]).strip()
                    # R은 대문자로 변환, /는 그대로 유지
                    status = status_raw.upper() if status_raw.upper() == 'R' else status_raw
                    if status == 'R':
                        scheduled_count += 1
            scheduled_days.append(scheduled_count)
            holiday_days.append(holiday_count)
    
    df = pd.DataFrame({
        '월': months,
        '근무일': work_days,
        '결근일': absent_days,
        '예정일수': scheduled_days,
        '휴가': holiday_days
    })
    
    # 차트 데이터 생성
    chart_data = {
        'months': months,
        'work_days': work_days,
        'absent_days': absent_days,
        'scheduled_days': scheduled_days,
        'holiday_days': holiday_days
    }
    
    return render_template('work_history.html', 
                         chart_data=chart_data,
                         df=df)

@app.route('/api/work-status/<int:day>', methods=['POST'])
@require_login
def api_update_work_status(day):
    """근무 상태 업데이트 API"""
    employee_id = session.get('employee_id')
    current_date = get_kst_now()
    month = current_date.month
    month_name = config.MONTHS[month - 1]
    
    success = update_work_status(employee_id, day, month_name, 'O')
    
    if success:
        # 캐시 무효화
        work_data_cache.clear_pattern(f"work_data:{employee_id}:{month_name}")
        return jsonify({'success': True, 'message': '근무시작이 기록되었습니다.'})
    else:
        return jsonify({'success': False, 'message': '근무시작 기록에 실패했습니다.'}), 400

start_yearly_stats_background_if_enabled(app)

if __name__ == '__main__':
    # Cloudtype.io 등 클라우드 환경에서는 PORT 환경 변수 사용
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') == 'development'
    app.run(debug=debug, host='0.0.0.0', port=port)

