import os
import json

# Google Sheets 설정
SPREADSHEET_NAME = "work_DB_2026"
# 스프레드시트 ID (URL에서 확인: https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit)
# 이름으로 찾을 수 없는 경우 ID를 사용합니다
SPREADSHEET_ID = "1mjQTR8FKMnbszfi0ci0w7AyF5Yc41PmQ1OQH-7aCDIw"

# Sales DB 스프레드시트 설정
SALES_SPREADSHEET_NAME = "sales_DB_2026"
SALES_SPREADSHEET_ID = "1cWRAktg_LWV4cJ0wesDDEltYo6GQ0yOlhwMSVihjY9M"
# 공지사항 폴더 ID → 드라이브 브라우저 주소 `.../folders/여기` 의 [여기] 전체(따옴표만 제외하고 그대로)
# 우선순위: 환경 변수 NOTICE_DRIVE_FOLDER_ID → 아래 문자열 따옴표 안
NOTICE_DRIVE_FOLDER_ID = (
    os.environ.get('NOTICE_DRIVE_FOLDER_ID') or '1uq1SAN_HYkqzunMlvbMXCKJYZRyhqw4P'
).strip()

# Google API 인증 정보
# 환경 변수 GOOGLE_CREDENTIALS가 있으면 사용, 없으면 파일에서 읽기
# Cloudtype 등 패널에서는 소문자 키 이름으로 넣는 경우도 있어 병렬 지원
GOOGLE_CREDENTIALS_JSON = (
    os.environ.get('GOOGLE_CREDENTIALS')
    or os.environ.get('GOOGLE_CREDENTIALS_JSON')
    or os.environ.get('google_credentials')
)
CREDENTIALS_FILE = "credentials.json"
SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']

def get_google_credentials():
    """Google 인증 정보를 딕셔너리로 반환 (환경 변수 우선, 없으면 None)"""
    if GOOGLE_CREDENTIALS_JSON:
        try:
            return json.loads(GOOGLE_CREDENTIALS_JSON)
        except json.JSONDecodeError as e:
            print(f"Error parsing GOOGLE_CREDENTIALS environment variable: {e}")
            return None
    return None

# 세션 설정
SECRET_KEY = os.environ.get('SECRET_KEY', 'your-secret-key-change-this-in-production')

# 비밀번호 설정
DEFAULT_PASSWORD = "1234"
PASSWORD_MIN_LENGTH = 4
PASSWORD_MAX_LENGTH = 4

# 월별 시트 이름
MONTHS = ['1월', '2월', '3월', '4월', '5월', '6월', 
          '7월', '8월', '9월', '10월', '11월', '12월']

# 근무 이력(/work-history): 당해 연도 기준 reference 월까지 역으로 조회할 월 수 (1~12).
# 12(기본) = 1~12월 시트 전부. 6 등으로 두면 최근 6개월치 시트만 API 호출 (속도·쿼터 절약).
WORK_HISTORY_RECENT_MONTHS = int(os.environ.get('WORK_HISTORY_RECENT_MONTHS', '12'))

# Sheets 재시도/병렬: SHEETS_READ_RETRY_ATTEMPTS, SHEETS_429_BACKOFF_CAP_SEC, SHEETS_PARALLEL_MONTH_WORKERS
# 메모리 캐시(TTL): WORK_DATA_* , SALES_* , WORK_START_* , ANNUAL_STATS_* , ACCOUNTS_* , NOTICE_CACHE_SECONDS
# /main 강제 갱신 제한: ALLOW_MAIN_FRESH_QUERY=0 또는 false / no / off
# SQLite 연간 스냅샷: YEARLY_STATS_SNAPSHOT_DB_PATH , YEARLY_STATS_SNAPSHOT_TTL_SEC
# 선택 배경 갱신: YEARLY_STATS_BG_REFRESH_ENABLED , YEARLY_STATS_BG_REFRESH_INTERVAL_SEC
# SWR 재패치: YEARLY_SWR_RECHECK_MS
# batchGet chunk: SHEETS_WORK_BATCH_CHUNK

# Sheets 읽기 429 완화: 재시도·병렬·앱측 데이터 캐시 (초)
# 재시도/sleep 합이 Gunicorn timeout(보통 30s)보다 크면 WORKER TIMEOUT 발생 → backoff 상한 필수.
SHEETS_READ_RETRY_ATTEMPTS = max(2, min(15, int(os.environ.get('SHEETS_READ_RETRY_ATTEMPTS', '5'))))
SHEETS_429_BACKOFF_CAP_SEC = max(2.0, min(60.0, float(os.environ.get('SHEETS_429_BACKOFF_CAP_SEC', '10.0'))))
SHEETS_PARALLEL_MONTH_WORKERS = max(1, min(12, int(os.environ.get('SHEETS_PARALLEL_MONTH_WORKERS', '3'))))
WORK_DATA_CACHE_SECONDS = max(30, min(3600, int(os.environ.get('WORK_DATA_CACHE_SECONDS', '180'))))
SALES_SUMMARY_CACHE_SECONDS = max(30, min(3600, int(os.environ.get('SALES_SUMMARY_CACHE_SECONDS', '300'))))
WORK_START_INFO_CACHE_SECONDS = max(30, min(3600, int(os.environ.get('WORK_START_INFO_CACHE_SECONDS', '180'))))
ANNUAL_STATS_CACHE_SECONDS = max(60, min(7200, int(os.environ.get('ANNUAL_STATS_CACHE_SECONDS', '300'))))
ACCOUNTS_CACHE_SECONDS = max(60, min(7200, int(os.environ.get('ACCOUNTS_CACHE_SECONDS', '300'))))

NOTICE_CACHE_SECONDS = max(30, min(7200, int(os.environ.get('NOTICE_CACHE_SECONDS', '120'))))

_allow_main_fresh = (os.environ.get('ALLOW_MAIN_FRESH_QUERY') or '1').strip().lower()
ALLOW_MAIN_FRESH_QUERY = _allow_main_fresh not in ('0', 'false', 'no', 'off')

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
_default_yearly_snap_db = os.path.join(_PROJECT_ROOT, 'instance', 'yearly_stats.sqlite')
YEARLY_STATS_SNAPSHOT_DB_PATH = (os.environ.get('YEARLY_STATS_SNAPSHOT_DB_PATH') or _default_yearly_snap_db).strip()
# 0 이면 스냅샷 기능 끔(항상 무거운 항목도 Sheets 재계산). 메모리(ANNUAL_STATS_CACHE_SECONDS) TTL이 여기 TTL보다
# 크면 결과가 디스크 갱신보다 오래 머물 수 있다.
YEARLY_STATS_SNAPSHOT_TTL_SEC = max(0, min(86400 * 30, int(os.environ.get('YEARLY_STATS_SNAPSHOT_TTL_SEC', '21600'))))

_bg_yearly = (os.environ.get('YEARLY_STATS_BG_REFRESH_ENABLED') or '0').strip().lower()
YEARLY_STATS_BG_REFRESH_ENABLED = _bg_yearly in ('1', 'true', 'yes', 'on')
YEARLY_STATS_BG_REFRESH_INTERVAL_SEC = max(120, min(86400, int(os.environ.get('YEARLY_STATS_BG_REFRESH_INTERVAL_SEC', '600'))))

# 연간 블록 SWR: stale 응답 후 클라이언트 재패치 간격(ms)
YEARLY_SWR_RECHECK_MS = max(500, min(60000, int(os.environ.get('YEARLY_SWR_RECHECK_MS', '2600'))))

# work/sales 각 스프레드시트 값 batchGet 한 요청당 최대 range 개수(URI·쿼터 안전)
SHEETS_WORK_BATCH_CHUNK = max(1, min(200, int(os.environ.get('SHEETS_WORK_BATCH_CHUNK', '90'))))

