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

# Google API 인증 정보
# 환경 변수 GOOGLE_CREDENTIALS가 있으면 사용, 없으면 파일에서 읽기
GOOGLE_CREDENTIALS_JSON = os.environ.get('GOOGLE_CREDENTIALS')
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

