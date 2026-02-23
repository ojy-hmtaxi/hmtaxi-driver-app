from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from datetime import datetime, date, timedelta, timezone
from zoneinfo import ZoneInfo
import calendar
from functools import wraps
import os
import config
import threading
import time

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

# 전역 캐시 인스턴스 (근무 데이터: 60초, 매출 데이터: 120초)
# TTL 증가로 API 호출 횟수 감소 (데이터 변경 빈도가 낮으므로 안전)
work_data_cache = SimpleCache(default_ttl=60)  # 근무 데이터는 60초 캐시
sales_data_cache = SimpleCache(default_ttl=120)  # 매출 데이터는 120초 캐시
from utils.auth import authenticate_user, change_password, check_default_password
from utils.google_sheets import (
    get_user_work_data, 
    get_all_user_work_data,
    update_work_status, 
    get_all_months_data,
    get_all_months_aggregated_data,
    get_user_by_id,
    add_sales_record,
    get_today_work_start_info,
    get_user_sales_summary,
    has_sales_record_for_date,
    get_loaner_vehicles,
    update_loaner_vehicle_on_apply,
    update_work_cell_note_report,
    get_today_replacement_display
)
import pandas as pd

app = Flask(__name__)
app.secret_key = config.SECRET_KEY

# 정적 파일 캐싱 최적화 및 동적 페이지 캐시 방지
@app.after_request
def after_request(response):
    """응답에 적절한 캐시 제어 헤더 추가"""
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
    """캐시를 사용하는 has_sales_record_for_date 래퍼 (캘린더 로딩 시 반복 호출 감소)"""
    date_norm = str(operation_date).replace('-', '/')
    cache_key = f"has_sales:{employee_id}:{month_sheet_name}:{date_norm}"
    cached = sales_data_cache.get(cache_key)
    if cached is not None:
        return bool(cached)
    result = has_sales_record_for_date(employee_id, month_sheet_name, operation_date)
    sales_data_cache.set(cache_key, result)
    return result

def get_work_start_info_with_fallback(employee_id, reference_date):
    """현재 날짜 기준으로 운행시작 정보를 찾고, 없으면 하루 전 정보를 반환"""
    month_name = config.MONTHS[reference_date.month - 1]
    day = reference_date.day
    info = get_today_work_start_info(employee_id, month_name, day)
    
    if info and info.get('work_date'):
        return info, reference_date, month_name, day
    
    previous_date = reference_date - timedelta(days=1)
    previous_month_name = config.MONTHS[previous_date.month - 1]
    previous_day = previous_date.day
    previous_info = get_today_work_start_info(employee_id, previous_month_name, previous_day)
    
    if previous_info and previous_info.get('work_date'):
        return previous_info, previous_date, previous_month_name, previous_day
    
    # 시작 정보를 찾지 못한 경우 기본값 반환
    return info, reference_date, month_name, day

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
            
            return redirect(url_for('calendar_view'))
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
            return redirect(url_for('calendar_view'))
        else:
            flash(message, 'error')
    
    return render_template('change_password.html')

@app.route('/calendar')
@require_login
def calendar_view():
    """캘린더 뷰 - 근무일정"""
    employee_id = session.get('employee_id')
    current_date = get_kst_now()
    
    # URL 파라미터에서 년/월 가져오기 (없으면 현재 월)
    year_param = request.args.get('year', type=int)
    month_param = request.args.get('month', type=int)
    
    if year_param and month_param:
        year = year_param
        month = month_param
        # 유효성 검사
        if month < 1:
            month = 12
            year -= 1
        elif month > 12:
            month = 1
            year += 1
    else:
        year = current_date.year
        month = current_date.month
    
    # 현재 월의 시트 이름
    month_name = config.MONTHS[month - 1]
    
    # 사용자의 근무 데이터 가져오기 (캐시 사용)
    all_work_data = get_all_user_work_data_cached(employee_id, month_name)
    
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
    
    # 근무일수와 결근일수 계산 (work_status에서 직접 계산하여 정확도 보장)
    # work_status에서 해당 월의 유효한 날짜 범위 내에서 직접 계산
    total_days_in_month_for_calc = calendar.monthrange(year, month)[1]
    work_days = sum(1 for day in range(1, total_days_in_month_for_calc + 1) if work_status.get(day) == 'O')  # 근무일수 (O 상태)
    absent_days = sum(1 for day in range(1, total_days_in_month_for_calc + 1) if work_status.get(day) == 'X')  # 결근일수 (X 상태)
    
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
                    yesterday_info = get_today_work_start_info(employee_id, yesterday_month_name, yesterday_day)
            else:
                # 다른 월인 경우 (월이 바뀐 경우)
                yesterday_all_work_data = get_all_user_work_data_cached(employee_id, yesterday_month_name)
                if yesterday_all_work_data:
                    yesterday_day_str = str(yesterday_day)
                    for record in yesterday_all_work_data:
                        if yesterday_day_str in record:
                            status_raw = str(record.get(yesterday_day_str, '')).strip().upper()
                            if status_raw == 'O':
                                yesterday_info = get_today_work_start_info(employee_id, yesterday_month_name, yesterday_day)
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
                    yesterday_info = get_today_work_start_info(employee_id, yesterday_month_name, yesterday_day)
            else:
                # 다른 월인 경우 (월이 바뀐 경우)
                yesterday_all_work_data = get_all_user_work_data_cached(employee_id, yesterday_month_name)
                if yesterday_all_work_data:
                    yesterday_day_str = str(yesterday_day)
                    for record in yesterday_all_work_data:
                        if yesterday_day_str in record:
                            status_raw = str(record.get(yesterday_day_str, '')).strip().upper()
                            if status_raw == 'O':
                                yesterday_info = get_today_work_start_info(employee_id, yesterday_month_name, yesterday_day)
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
    
    # 이달의 매출 합계·가해사고 수 가져오기 (캐시 사용, sales 시트 한 번만 사용)
    sales_summary = get_user_sales_summary_cached(employee_id, month_name) or {}
    total_revenue = sales_summary.get('total_revenue', 0)
    total_fuel_cost = sales_summary.get('total_fuel_cost', 0)
    accident_count = sales_summary.get('accident_count', 0)
    
    # 만근 기준 계산: 그 달의 총 일수 - 공휴일 - 일요일 <= (근무일 + 휴무일) - 결근일
    total_days_in_month = calendar.monthrange(year, month)[1]  # 그 달의 총 일수
    holiday_days_count = sum(1 for day in range(1, total_days_in_month + 1) if work_status.get(day) == '/')  # 휴무일 개수
    public_holiday_count = sum(1 for day in range(1, total_days_in_month + 1) if work_status.get(day) == 'H')  # 공휴일 개수
    sunday_count = sum(1 for day in range(1, total_days_in_month + 1) if calendar.weekday(year, month, day) == 6)  # 일요일 개수 (0=월..6=일)
    full_attendance_threshold = total_days_in_month - public_holiday_count - sunday_count  # 만근 기준
    is_full_attendance = (work_days + holiday_days_count - absent_days) >= full_attendance_threshold  # (근무일+휴무일-결근일) >= 기준
    
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
        rep = get_today_replacement_display(employee_id, month_name, current_date.day)
        if rep:
            today_replacement_vehicle, today_replacement_vehicle_type = rep
    
    return render_template('calendar.html', 
                         calendar=cal,
                         year=year,
                         month=month,
                         month_name=month_name,
                         work_status=work_status,
                         current_date=current_date_only,
                         work_data=work_data,
                         work_days=work_days,
                         absent_days=absent_days,
                         total_revenue=total_revenue,
                         total_fuel_cost=total_fuel_cost,
                         holiday_days_count=holiday_days_count,
                         accident_count=accident_count,
                         prev_year=prev_year,
                         prev_month=prev_month,
                         next_year=next_year,
                         next_month=next_month,
                         can_end_work=can_end_work,
                         can_start_work=can_start_work,
                         today_vehicle=today_vehicle,
                         today_vehicle_type=today_vehicle_type,
                         today_replacement_vehicle=today_replacement_vehicle,
                         today_replacement_vehicle_type=today_replacement_vehicle_type,
                         show_replacement_button=show_replacement_button,
                         is_full_attendance=is_full_attendance,
                         has_unread_notices=has_unread_notices)


@app.route('/vehicle-replacement-apply', methods=['GET', 'POST'])
@require_login
def vehicle_replacement_apply():
    """대차신청 - 근무 중 차량 교체 신청"""
    employee_id = session.get('employee_id')
    driver_name = session.get('name', '') or ''
    current_date = get_kst_now()
    month_name = config.MONTHS[current_date.month - 1]
    today_day = current_date.day
    
    if request.method == 'POST':
        vehicle_number = (request.form.get('vehicle_number') or '').strip()
        if not vehicle_number:
            flash('대차할 차량을 선택해주세요.', 'error')
            return redirect(url_for('vehicle_replacement_apply'))
        apply_date_str = current_date.strftime('%Y/%m/%d')
        if update_loaner_vehicle_on_apply(vehicle_number, employee_id, driver_name, apply_date_str):
            report_value = f"{vehicle_number} (대차)"
            if update_work_cell_note_report(employee_id, month_name, today_day, report_value):
                work_data_cache.clear_pattern(f"work_data:{employee_id}:*")
                flash('대차신청이 완료되었습니다.', 'success')
            else:
                flash('보고사항 반영에 실패했습니다. 관리자에게 문의하세요.', 'error')
        else:
            flash('대차 신청 처리에 실패했습니다. 다시 시도해주세요.', 'error')
        return redirect(url_for('calendar_view', year=current_date.year, month=current_date.month))
    
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
        vehicle_condition = request.form.get('vehicle_condition', '')
        special_notes = request.form.get('special_notes', '')
        
        # 날짜/시간 포맷팅 (현재 시간 포함)
        work_datetime = current_date.strftime('%Y/%m/%d %H:%M:%S')
        
        # 근무 상세 정보 구성
        work_details = {
            'vehicle_number': vehicle_number,
            'work_date': work_datetime,
            'work_type': work_type,
            'vehicle_condition': vehicle_condition,
            'special_notes': special_notes
        }
        
        # 근무 상태 업데이트 및 메모 추가 (선택한 차량번호와 근무유형 전달)
        success = update_work_status(employee_id, day, month_name, 'O', work_details=work_details, vehicle_number=vehicle_number, work_type=work_type)
        
        if success:
            # 캐시 무효화 (근무 데이터 업데이트됨)
            work_data_cache.clear_pattern(f"work_data:{employee_id}:{month_name}")
            
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
        
        # 운행시작 정보 조회 (필요 시 하루 전 데이터 사용)
        work_start_info, start_lookup_date, start_month_name, start_day = get_work_start_info_with_fallback(employee_id, current_date)
        
        # 운행일 결정: lookup_date 사용 (근무예정일, 즉 Google Sheets에 'O'가 기록된 날짜)
        # lookup_date는 get_work_start_info_with_fallback에서 반환된 날짜로,
        # 근무시작 시 selected_date로 설정한 날짜와 동일함
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
            
            # 근무종료 완료 활동 로깅
            user_name = user.get('name', '') if user else ''
            vehicle_number = step1_data.get('vehicle_number', '')
            # lookup_date는 근무준비를 시작한 날짜 (운행일과 동일)
            print(f"[ACTIVITY] user 근무종료 완료 - 사번: {employee_id}, 이름: {user_name}, 날짜: {year}/{month}/{day}, 차량: {vehicle_number}")
            
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
    
    # 모든 월별 데이터 가져오기 (같은 사번의 모든 행 합산)
    all_data = get_all_months_aggregated_data(employee_id)
    
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
            work_days_val = data.get('근무일수', 0)
            absent_days_val = data.get('결근일수', 0)
            try:
                work_days.append(int(work_days_val) if work_days_val else 0)
                absent_days.append(int(absent_days_val) if absent_days_val else 0)
            except (ValueError, TypeError):
                work_days.append(0)
                absent_days.append(0)
            
            # R(예정일)과 /(휴무일) 개수 계산
            scheduled_count = 0
            holiday_count = 0
            for day in range(1, 32):
                day_str = str(day)
                if day_str in data:
                    status_raw = str(data[day_str]).strip()
                    # R은 대문자로 변환, /는 그대로 유지
                    status = status_raw.upper() if status_raw.upper() == 'R' else status_raw
                    if status == 'R':
                        scheduled_count += 1
                    elif status == '/':
                        holiday_count += 1
            scheduled_days.append(scheduled_count)
            holiday_days.append(holiday_count)
    
    df = pd.DataFrame({
        '월': months,
        '근무일수': work_days,
        '결근일수': absent_days,
        '예정일수': scheduled_days,
        '휴무일수': holiday_days
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

if __name__ == '__main__':
    # Cloudtype.io 등 클라우드 환경에서는 PORT 환경 변수 사용
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') == 'development'
    app.run(debug=debug, host='0.0.0.0', port=port)

