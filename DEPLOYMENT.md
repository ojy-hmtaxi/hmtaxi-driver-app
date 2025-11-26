# Cloudtype.io 배포 가이드

이 문서는 한미택시 근무 관리 시스템을 Cloudtype.io에 배포하는 방법을 상세히 설명합니다.

## 사전 준비

### 1. GitHub 저장소 확인
- 프로젝트가 GitHub에 업로드되어 있어야 합니다
- 저장소 URL: https://github.com/ojy-hmtaxi/hmtaxi-driver-app

### 2. 필요한 정보 준비
- Google Cloud 서비스 계정 키 파일 (`credentials.json`)의 전체 내용
- Flask 세션 암호화를 위한 SECRET_KEY (임의의 긴 문자열)

---

## Cloudtype.io 배포 단계

### 1단계: Cloudtype.io 로그인 및 프로젝트 생성

1. **Cloudtype.io 접속**
   - https://cloudtype.io 접속
   - 로그인 (GitHub 계정으로 로그인 가능)

2. **새 프로젝트 생성**
   - 대시보드에서 **"새 프로젝트"** 또는 **"New Project"** 버튼 클릭
   - 프로젝트 이름 입력 (예: `hmtaxi-driver-app`)
   - 생성 완료

### 2단계: 서비스 생성 및 GitHub 연동

1. **서비스 생성**
   - 프로젝트 내에서 **"새 서비스"** 또는 **"New Service"** 버튼 클릭
   - 서비스 이름 입력 (예: `hmtaxi-driver`)

2. **배포 소스 선택**
   - **"GitHub"** 선택
   - GitHub 계정 연동 (처음이면 권한 승인 필요)
   - 저장소 선택: `ojy-hmtaxi/hmtaxi-driver-app`
   - 브랜치 선택: `deploy`

### 3단계: 빌드 및 실행 설정

1. **빌드 설정**
   - **빌드 명령** (Build Command):
     ```
     pip install -r requirements.txt
     ```
   
2. **실행 설정**
   - **실행 명령** (Start Command):
     ```
     python app.py
     ```
   - 또는:
     ```
     gunicorn app:app --bind 0.0.0.0:$PORT
     ```
     (gunicorn을 사용하려면 `requirements.txt`에 추가 필요)

3. **Python 버전**
   - Python 버전: **3.11** 선택 (또는 3.10 이상)

4. **포트 설정**
   - Cloudtype.io는 자동으로 `PORT` 환경 변수를 제공합니다
   - `app.py`에서 이미 `os.environ.get('PORT', 5000)`로 처리되어 있음

### 4단계: 환경 변수 설정

1. **환경 변수 메뉴 찾기**
   - 서비스 설정 페이지에서 좌측 메뉴 또는 상단 탭에서 **"환경 변수"** 또는 **"Environment Variables"** 찾기
   - 또는 **"Settings"** → **"Environment Variables"** 경로

2. **SECRET_KEY 추가**
   - **"변수 추가"** 또는 **"Add Variable"** 버튼 클릭
   - **변수명 (Key)**: `SECRET_KEY`
   - **변수값 (Value)**: 임의의 긴 문자열 입력
     ```
     예시: your-very-long-secret-key-change-this-in-production-2025
           driver-application-hanmitaxi-ojy-dev-0922-secret-key-2025
     ```
   - **저장** 클릭

3. **GOOGLE_CREDENTIALS 추가**
   - **"변수 추가"** 또는 **"Add Variable"** 버튼 클릭
   - **변수명 (Key)**: `GOOGLE_CREDENTIALS`
   - **변수값 (Value)**: `credentials.json` 파일의 전체 내용 복사하여 붙여넣기
   
   **주의사항:**
   - 로컬의 `credentials.json` 파일을 텍스트 에디터로 열기
   - 파일 내용 전체를 복사 (한 줄이어도 됨)
   - JSON 형식 그대로 붙여넣기
   - 따옴표나 특수문자도 그대로 포함
   - 예시:
     ```json
     {"type":"service_account","project_id":"your-project-id","private_key_id":"...","private_key":"-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n",...}
     ```

### 5단계: 배포 실행

1. **배포 시작**
   - 모든 설정 완료 후 **"배포"** 또는 **"Deploy"** 버튼 클릭
   - 또는 GitHub에 푸시하면 자동 배포 (자동 배포 설정 시)

2. **배포 로그 확인**
   - 배포 진행 상황을 실시간으로 확인 가능
   - 빌드 로그와 실행 로그를 확인하여 오류 체크

3. **배포 완료 확인**
   - 배포가 완료되면 서비스 URL이 생성됨
   - 예: `https://your-service-name.cloudtype.app`
   - 해당 URL로 접속하여 정상 작동 확인

---

## 배포 후 확인 사항

### 1. 서비스 접속 테스트
- 배포된 URL로 접속
- 로그인 페이지가 정상적으로 표시되는지 확인

### 2. 로그 확인
- Cloudtype.io 대시보드에서 **"로그"** 또는 **"Logs"** 메뉴 클릭
- 서버 로그에서 오류 메시지 확인
- 디버깅 로그 확인 (DEBUG 메시지)

### 3. 환경 변수 확인
- 환경 변수가 제대로 설정되었는지 확인
- `GOOGLE_CREDENTIALS`가 올바르게 파싱되는지 확인

---

## 문제 해결

### 배포 실패 시

1. **빌드 오류**
   - `requirements.txt`의 패키지 버전 확인
   - Python 버전 확인 (3.11 권장)

2. **실행 오류**
   - 환경 변수 설정 확인
   - `GOOGLE_CREDENTIALS` JSON 형식 확인
   - 로그에서 구체적인 오류 메시지 확인

3. **Google Sheets 접근 오류**
   - `GOOGLE_CREDENTIALS` 환경 변수 값 확인
   - 서비스 계정이 Google Sheets에 공유되었는지 확인

### 환경 변수 찾기 어려운 경우

Cloudtype.io의 UI가 업데이트되어 메뉴 위치가 다를 수 있습니다. 다음 경로를 시도해보세요:

1. **서비스 설정 페이지** → 좌측 사이드바 → **"환경 변수"**
2. **서비스 설정 페이지** → 상단 탭 → **"Settings"** → **"Environment Variables"**
3. **서비스 설정 페이지** → **"고급 설정"** 또는 **"Advanced Settings"** → **"환경 변수"**
4. **서비스 상세 페이지** → **"설정"** 아이콘 → **"환경 변수"**

---

## 추가 설정 (선택사항)

### 자동 배포 설정
- GitHub에 푸시할 때마다 자동으로 재배포되도록 설정 가능
- 서비스 설정에서 **"자동 배포"** 옵션 활성화

### 도메인 설정
- Cloudtype.io에서 제공하는 기본 도메인 외에 커스텀 도메인 설정 가능
- 서비스 설정에서 **"도메인"** 메뉴에서 설정

---

## 참고사항

- `credentials.json` 파일은 절대 GitHub에 업로드하지 마세요 (`.gitignore`에 포함됨)
- 프로덕션 환경에서는 `SECRET_KEY`를 안전하게 관리하세요
- Google Sheets의 서비스 계정 이메일이 스프레드시트에 편집자 권한으로 공유되어 있어야 합니다

