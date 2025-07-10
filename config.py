import os
from datetime import timedelta
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# 기본 설정
SECRET_KEY = os.getenv('SECRET_KEY', 'your-secret-key-here')
DEBUG = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'

# 세션 설정
SESSION_TYPE = 'filesystem'
PERMANENT_SESSION_LIFETIME = timedelta(days=7)

# 로깅 설정
LOGGING_ENABLED = True

# 데이터베이스 설정
if os.getenv('DATABASE_URL'):
    # Render.com 배포용 (PostgreSQL)
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL').replace('postgres://', 'postgresql://')
else:
    # 로컬 개발용 (SQLite)
    SQLALCHEMY_DATABASE_URI = os.getenv('SQLALCHEMY_DATABASE_URI', 'sqlite:///app.db')

SQLALCHEMY_TRACK_MODIFICATIONS = False

# 디렉토리 설정
STOCK_LISTS_DIR = "stock_lists"
CHART_DIR = "static/charts"
ANALYSIS_DIR = "static/analysis"
SUMMARY_DIR = "static/summaries"
DEBUG_DIR = "static/debug"
MEMO_DIR = "static/memos"
MULTI_SUMMARY_DIR = "static/multi_summaries"

# 날짜별 폴더 구조 설정
USE_DATE_FOLDERS = False  # 날짜별 폴더 사용 여부 (False: 한 폴더에 모든 파일 저장)
DAYS_TO_KEEP = 365  # 보관할 일수 (365일 이전 파일은 자동 삭제)

# API 설정
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Gemini 모델 설정
GEMINI_MODEL_VERSION = os.getenv("GEMINI_MODEL_VERSION", "gemini-2.5-flash")  # 기본값: gemini-2.0-flash
GEMINI_TEXT_MODEL_VERSION = os.getenv("GEMINI_TEXT_MODEL_VERSION", "gemini-2.5-flash")  # 텍스트 전용 모델

# 차트 생성 타임아웃 설정 (초)
CHART_GENERATION_TIMEOUT = 60
AI_ANALYSIS_TIMEOUT = 180  # 3분으로 증가 (Gemini API 응답 시간 고려)

# 메모리 관리 설정
ENABLE_MEMORY_CLEANUP = True

# 이메일 설정 (환경별 구분)
TESTING = os.getenv('FLASK_TESTING', 'False').lower() == 'true'

# DEBUG 값이 True이면 항상 Mailtrap 설정을 사용하도록 수정
if DEBUG:
    # 로컬 테스트용 Mailtrap 설정 (스크린샷 정보 반영)
    MAIL_SERVER = 'sandbox.smtp.mailtrap.io'
    MAIL_PORT = 2525
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.getenv('MAILTRAP_USERNAME', 'b8663e4255b8b0')  # 환경변수에서 가져오기
    MAIL_PASSWORD = os.getenv('MAILTRAP_PASSWORD', '7a2c344e39c940')  # 환경변수에서 가져오기
    MAIL_DEFAULT_SENDER = 'test-from-flask@example.com'
else:
    # 프로덕션용 SendGrid 설정
    MAIL_SERVER = 'smtp.sendgrid.net'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = 'apikey'  # SendGrid는 항상 'apikey'
    MAIL_PASSWORD = os.getenv('SENDGRID_API_KEY')
    MAIL_DEFAULT_SENDER = os.getenv('SENDGRID_FROM_EMAIL', 'noreply@yourdomain.com')

# SendGrid 설정 (프로덕션용)
SENDGRID_API_KEY = os.getenv('SENDGRID_API_KEY')
SENDGRID_FROM_EMAIL = os.getenv('SENDGRID_FROM_EMAIL', 'noreply@yourdomain.com')
SENDGRID_FROM_NAME = os.getenv('SENDGRID_FROM_NAME', '주식 분석 뉴스레터')

# Celery 설정
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')

# 디렉토리 생성 (배포 환경에서 안전하게)
try:
    for directory in ['logs', 'static/analysis', 'static/charts', 'static/debug', 'static/summaries', 'static/memos', 'static/multi_summaries', 'stock_lists']:
        os.makedirs(directory, exist_ok=True)
except Exception as e:
    # 디렉토리 생성 실패시 로그만 남기고 계속 진행
    print(f"디렉토리 생성 실패: {e}")

# Yahoo Finance API 설정
YAHOO_FINANCE_CONFIG = {
    'MAX_RETRIES': 5,                    # 최대 재시도 횟수
    'INITIAL_DELAY': 3,                  # 초기 지연 시간 (초)
    'MAX_DELAY': 120,                    # 최대 지연 시간 (초)
    'RATE_LIMIT_DELAY': 10,              # Rate limit 감지 시 기본 지연 시간
    'SESSION_TIMEOUT': 30,               # 세션 타임아웃 (초)
    'CONCURRENT_REQUESTS': 1,            # 동시 요청 수 (1로 제한)
    'DAILY_REQUEST_LIMIT': 100,          # 일일 요청 제한 (안전을 위한 자체 제한)
    'REQUEST_INTERVAL': 5,               # 요청 간격 (초)
}

# 대안 API 설정 (향후 사용을 위한 준비)
ALTERNATIVE_APIS = {
    'ALPHA_VANTAGE': {
        'API_KEY': os.getenv('ALPHA_VANTAGE_API_KEY', ''),
        'BASE_URL': 'https://www.alphavantage.co/query',
        'DAILY_LIMIT': 500,
    },
    'FINNHUB': {
        'API_KEY': os.getenv('FINNHUB_API_KEY', ''),
        'BASE_URL': 'https://finnhub.io/api/v1',
        'DAILY_LIMIT': 60,
    },
    'IEX_CLOUD': {
        'API_KEY': os.getenv('IEX_CLOUD_API_KEY', ''),
        'BASE_URL': 'https://cloud.iexapis.com/stable',
        'DAILY_LIMIT': 100000,
    }
} 