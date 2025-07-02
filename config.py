import os
from datetime import timedelta

# .env 파일 로드 (python-dotenv 사용)
try:
    from dotenv import load_dotenv
    # .env 파일 경로 설정
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if os.path.exists(env_path):
        load_dotenv(env_path)
        print(f"✅ .env 파일 로드 완료: {env_path}")
    else:
        print(f"⚠️  .env 파일 없음: {env_path}")
except ImportError:
    print("⚠️  python-dotenv 패키지가 설치되지 않음. pip install python-dotenv")

# 기본 설정
SECRET_KEY = os.getenv('SECRET_KEY', 'your-secret-key-here')
DEBUG = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'

# 세션 설정
SESSION_TYPE = 'filesystem'
PERMANENT_SESSION_LIFETIME = timedelta(days=7)

# 로깅 설정
LOGGING_ENABLED = True

# 데이터베이스 설정 - PostgreSQL 중심
if os.getenv('USE_SQLITE'):
    # 로컬 개발용 SQLite (USE_SQLITE=true 환경변수 설정 시에만 사용)
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DB_PATH = os.path.join(BASE_DIR, 'instance', 'app.db')
    SQLALCHEMY_DATABASE_URI = f'sqlite:///{DB_PATH}'
    print("⚠️  SQLite 모드로 실행 중 (로컬 개발용)")
elif os.getenv('DATABASE_URL'):
    # 프로덕션용 PostgreSQL (환경변수에서 가져오기)
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL').replace('postgres://', 'postgresql://')
else:
    # 기본값: 로컬 PostgreSQL
    SQLALCHEMY_DATABASE_URI = 'postgresql://newsletter:NewsLetter2025!@localhost/newsletter_db'
    print("📘 기본 PostgreSQL 설정 사용")

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
USE_DATE_FOLDERS = True  # 날짜별 폴더 사용 여부
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