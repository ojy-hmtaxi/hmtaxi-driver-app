# 근무 관리 시스템

Google Sheets를 데이터베이스로 사용하는 Python 웹 애플리케이션입니다. 택시 운전기사들이 모바일로 접속하여 근무일정을 확인하고 근무시작을 기록할 수 있습니다.

## 주요 기능

1. **로그인 시스템**
   - 사번(4자리 숫자)과 비밀번호(4자리 숫자)로 로그인
   - 첫 로그인 시 비밀번호 변경 필수
   - 비밀번호는 사번과 같을 수 없음

2. **캘린더 뷰**
   - 이번달 근무일정을 캘린더 형태로 확인
   - 근무일(O), 결근일(X) 표시
   - 근무일수, 결근일수 통계 표시

3. **근무시작**
   - 근무준비 사항 입력
   - 차량 상태, 날씨 선택
   - 근무시작 버튼으로 Google Sheets에 기록

4. **근무이력**
   - 월별 근무이력 시각화
   - 근무일수, 결근일수 통계 확인

## 설치 방법

### 1. 의존성 설치

```bash
pip install -r requirements.txt
```

### 2. Google Sheets API 설정

1. Google Cloud Console에서 프로젝트 생성
2. Google Sheets API 및 Google Drive API 활성화
3. 서비스 계정 생성 및 키 다운로드
4. `credentials.json` 파일을 프로젝트 루트에 배치
5. Google Sheets에서 서비스 계정 이메일을 편집자로 공유

### 3. Google Sheets 구조

**스프레드시트 이름**: `work_DB_2026`

**월별 시트 (1월~12월)**:
- 차량번호
- 차종
- 근무유형
- 사번
- 운전기사
- 근무일수
- 결근일수
- 1~31 (날짜 컬럼)

**accounts 시트**:
- employee_id
- name
- password_hash (bcrypt 해시)

### 4. 애플리케이션 실행

```bash
python app.py
```

애플리케이션은 `http://0.0.0.0:5000`에서 실행됩니다.

## 사용 방법

1. 모바일 브라우저로 접속
2. 사번과 비밀번호로 로그인
3. 첫 로그인 시 비밀번호 변경
4. 캘린더에서 근무일정 확인
5. "근무시작" 버튼 클릭
6. 근무준비 사항 입력 후 제출
7. Google Sheets에 자동으로 기록됨

## 비밀번호 정책

- 모든 유저의 첫 로그인 비밀번호는 `1234` (bcrypt 해시: )
- 첫 로그인 후 비밀번호 변경 필수
- 비밀번호는 4자리 숫자
- 비밀번호는 사번과 같을 수 없음
- 관리자가 Google Sheets에서 비밀번호를 `1234`로 변경하면 다음 로그인 시 재설정 필요

## 프로젝트 구조

```
.
├── app.py                 # Flask 메인 애플리케이션
├── config.py             # 설정 파일
├── credentials.json      # Google API 인증 정보
├── requirements.txt      # Python 의존성
├── utils/
│   ├── auth.py          # 인증 관련 유틸리티
│   └── google_sheets.py # Google Sheets API 연동
├── templates/           # HTML 템플릿
│   ├── base.html
│   ├── login.html
│   ├── change_password.html
│   ├── calendar.html
│   ├── work_start.html
│   └── work_history.html
└── static/              # 정적 파일
    ├── css/
    │   └── style.css
    └── js/
        └── main.js
```

## 환경 변수

프로덕션 환경에서는 다음 환경 변수를 설정하세요:

```bash
export SECRET_KEY='your-secret-key-here'
export GOOGLE_CREDENTIALS='{"type":"service_account",...}'  # credentials.json의 전체 내용
```

## Cloudtype.io 배포

### 1. 환경 변수 설정

Cloudtype.io 대시보드에서 다음 환경 변수를 설정하세요:

1. **SECRET_KEY**: Flask 세션 암호화 키 (임의의 긴 문자열)
2. **GOOGLE_CREDENTIALS**: `credentials.json` 파일의 전체 내용을 JSON 문자열로 설정

#### GOOGLE_CREDENTIALS 설정 방법:

1. 로컬의 `credentials.json` 파일을 열기
2. 파일의 모든 내용을 복사 (한 줄로 되어 있어도 됨)
3. Cloudtype.io 환경 변수 설정에서:
   - 변수명: `GOOGLE_CREDENTIALS`
   - 변수값: 복사한 JSON 내용 전체를 붙여넣기
   - 주의: 따옴표나 특수문자가 포함되어 있어도 그대로 붙여넣기

예시:
```
GOOGLE_CREDENTIALS={"type":"service_account","project_id":"your-project",...}
```

### 2. 배포 설정

- **빌드 명령**: `pip install -r requirements.txt`
- **실행 명령**: `python app.py` 또는 `gunicorn app:app`
- **포트**: Cloudtype.io가 자동으로 `PORT` 환경 변수를 제공하므로, `app.py`에서 `os.environ.get('PORT', 5000)` 사용 권장

### 3. 주의사항

1. `credentials.json` 파일은 절대 공개 저장소에 업로드하지 마세요.
2. Cloudtype.io 환경 변수에 `GOOGLE_CREDENTIALS`를 설정하면 파일이 필요 없습니다.
3. 프로덕션 환경에서는 `SECRET_KEY`를 안전하게 관리하세요.
4. Google Sheets의 서비스 계정 권한을 적절히 설정하세요.

## 라이선스

이 프로젝트는 개인 사용 목적으로 작성되었습니다.

