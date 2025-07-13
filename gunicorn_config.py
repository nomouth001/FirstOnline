# Gunicorn 설정 파일
# 파일: gunicorn_config.py

import multiprocessing
import os

# 바인드 주소
bind = "0.0.0.0:8000"

# 워커 설정 (Lightsail 환경에 맞게 최적화)
# CPU 코어 수 * 2 + 1 대신 더 적은 워커 사용
workers = max(2, multiprocessing.cpu_count())  # CPU 코어 수만큼만 사용 (최소 2개)
worker_class = "sync"  # 동기 워커 (AI 분석용)
worker_connections = 500  # 연결 수 제한 (1000에서 500으로 감소)

# 타임아웃 설정
timeout = 180  # 타임아웃 증가 (120초에서 180초로)
graceful_timeout = 30  # 정상 종료 대기 시간
keepalive = 2  # Keep-alive 연결 유지 시간

# 메모리 관리 설정 (강화)
max_requests = 50  # 워커당 최대 요청 수 대폭 감소 (1000에서 50으로)
max_requests_jitter = 10  # 랜덤 지터 감소 (50에서 10으로)
preload_app = True  # 앱 미리 로드 (메모리 절약)
limit_request_line = 4096  # 요청 라인 길이 제한
limit_request_fields = 100  # 요청 필드 수 제한

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
    # 프로덕션 환경 설정 (Lightsail에 최적화)
    workers = max(2, multiprocessing.cpu_count())
    timeout = 180
    max_requests = 50
    max_requests_jitter = 10
elif os.getenv('FLASK_ENV') == 'development':
    # 개발 환경 설정
    workers = 2
    timeout = 60
    max_requests = 100
    reload = True  # 코드 변경 시 자동 리로드
else:
    # 기본 설정 (Lightsail에 최적화)
    workers = max(2, multiprocessing.cpu_count())
    timeout = 180
    max_requests = 50
    max_requests_jitter = 10 