# Gunicorn (Cloudtype 등)
# 시작 예: gunicorn -c gunicorn.conf.py app:app
# 기본 timeout(30초)이면 Sheets 429 재시도 중 워커가 막혀 WORKER TIMEOUT → SIGKILL 이 납니다.

bind = "0.0.0.0:5000"
workers = 1
worker_class = "sync"
timeout = 120
graceful_timeout = 30
keepalive = 5
max_requests = 500
max_requests_jitter = 50
