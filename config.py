import os

# Google Sheets 설정
SPREADSHEET_NAME = "work_DB_2026"
# 스프레드시트 ID (URL에서 확인: https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit)
# 이름으로 찾을 수 없는 경우 ID를 사용합니다
SPREADSHEET_ID = "1mjQTR8FKMnbszfi0ci0w7AyF5Yc41PmQ1OQH-7aCDIw"

# Sales DB 스프레드시트 설정
SALES_SPREADSHEET_NAME = "sales_DB_2026"
SALES_SPREADSHEET_ID = "1cWRAktg_LWV4cJ0wesDDEltYo6GQ0yOlhwMSVihjY9M"

CREDENTIALS_FILE = "credentials.json"
SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']

# 세션 설정
SECRET_KEY = os.environ.get('SECRET_KEY', 'your-secret-key-change-this-in-production')

# 비밀번호 설정
DEFAULT_PASSWORD = "1234"
PASSWORD_MIN_LENGTH = 4
PASSWORD_MAX_LENGTH = 4

# 월별 시트 이름
MONTHS = ['1월', '2월', '3월', '4월', '5월', '6월', 
          '7월', '8월', '9월', '10월', '11월', '12월']

