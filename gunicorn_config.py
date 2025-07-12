# Gunicorn 설정 파일
# 파일: gunicorn_config.py

import multiprocessing
import os

# 바인드 주소
bind = "0.0.0.0:8000"

# 워커 설정
workers = multiprocessing.cpu_count() * 2 + 1  # CPU 코어 수 기반 워커 개수
worker_class = "sync"  # 동기 워커 (AI 분석용)
worker_connections = 1000

# 타임아웃 설정 (중요!)
timeout = 120  # 120초 워커 타임아웃 (기존 30초에서 증가)
keepalive = 2  # Keep-alive 연결 유지 시간

# 메모리 관리 설정
max_requests = 1000  # 워커당 최대 요청 수 (메모리 누수 방지)
max_requests_jitter = 50  # 랜덤 지터 (모든 워커가 동시에 재시작되는 것 방지)
preload_app = True  # 앱 미리 로드 (메모리 절약)

# 로깅 설정
accesslog = "logs/gunicorn_access.log"
errorlog = "logs/gunicorn_error.log"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# 프로세스 관리
pidfile = "logs/gunicorn.pid"
daemon = False  # 포그라운드 실행 (컨테이너 환경에서는 False)

# 보안 설정
user = None  # 실행 사용자 (필요시 설정)
group = None  # 실행 그룹 (필요시 설정)
umask = 0  # 파일 생성 마스크

# 성능 튜닝
worker_tmp_dir = "/dev/shm"  # 워커 임시 디렉토리 (메모리 기반)

# 워커 재시작 조건 (메모리 누수 방지)
def when_ready(server):
    """서버 준비 완료 시 호출"""
    server.log.info("서버가 준비되었습니다.")

def worker_int(worker):
    """워커 인터럽트 시 호출"""
    worker.log.info(f"워커 {worker.pid} 인터럽트 받음")

def pre_fork(server, worker):
    """워커 포크 전 호출"""
    server.log.info(f"워커 {worker.pid} 포크 시작")

def post_fork(server, worker):
    """워커 포크 후 호출"""
    server.log.info(f"워커 {worker.pid} 포크 완료")

def worker_abort(worker):
    """워커 중단 시 호출"""
    worker.log.info(f"워커 {worker.pid} 중단됨")

# 메모리 모니터링 설정
def on_starting(server):
    """서버 시작 시 메모리 모니터링 초기화"""
    server.log.info("Gunicorn 서버 시작 - 메모리 모니터링 활성화")
    
def on_reload(server):
    """서버 리로드 시 호출"""
    server.log.info("Gunicorn 서버 리로드됨")

# 환경별 설정
if os.getenv('FLASK_ENV') == 'production':
    # 프로덕션 환경 설정
    workers = multiprocessing.cpu_count() * 2 + 1
    timeout = 120
    max_requests = 1000
elif os.getenv('FLASK_ENV') == 'development':
    # 개발 환경 설정
    workers = 2
    timeout = 60
    max_requests = 100
    reload = True  # 코드 변경 시 자동 리로드
else:
    # 기본 설정
    workers = 2
    timeout = 120
    max_requests = 1000 